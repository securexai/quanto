#!/usr/bin/env python3
"""Parse Davivienda savings account PDF extracto into normalized JSON."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}

MONTH_HEADER_RE = re.compile(r"INFORME DEL MES:\s+([A-ZÑ]+)\s*/\s*(\d{4})")
AMOUNT_RE = re.compile(r"\$\s*([\d,]+\.\d{2})")
MOV_RE = re.compile(
    r"^\s*(\d{2})\s+(\d{2})\s+\$\s*([\d,]+\.\d{2})([+-])\s+(\d{4})\s+(.+?)\s{2,}(\S.*?)\s*$"
)
SUMMARY_LABELS = {
    "Saldo Anterior": "saldo_anterior",
    "Más Créditos": "mas_creditos",
    "Menos Débitos": "menos_debitos",
    "Nuevo Saldo": "nuevo_saldo",
    "Saldo Promedio": "saldo_promedio",
    "Saldo Total Bolsillo": "saldo_total_bolsillo",
}


def run_pdftotext(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, check=True, text=True,
    )
    return result.stdout


def parse_money(text: str) -> float:
    return float(text.replace(",", ""))


def extract_period(text: str) -> tuple[int, int]:
    m = MONTH_HEADER_RE.search(text)
    if not m:
        raise ValueError("No se encontró 'INFORME DEL MES' en el PDF")
    return MESES[m.group(1)], int(m.group(2))


def extract_summary(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for label, key in SUMMARY_LABELS.items():
        pat = re.compile(rf"{re.escape(label)}\s+\$([\d,]+\.\d{{2}})")
        m = pat.search(text)
        if m:
            out[key] = parse_money(m.group(1))
    return out


def extract_movements(text: str, year: int) -> tuple[list[dict], list[dict]]:
    cuenta: list[dict] = []
    bolsillo: list[dict] = []
    section: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("EXTRACTO CUENTA DE AHORROS"):
            section = "cuenta"
            continue
        if stripped.startswith("EXTRACTO BOLSILLO"):
            section = "bolsillo"
            continue
        if section is None:
            continue
        m = MOV_RE.match(line)
        if not m:
            continue
        dd, mm, amount_str, sign, doc, desc, oficina = m.groups()
        day = int(dd)
        month = int(mm)
        amount = parse_money(amount_str)
        signed = amount if sign == "+" else -amount
        fecha = f"{year:04d}-{month:02d}-{day:02d}"
        mov = {
            "fecha": fecha,
            "valor": signed,
            "doc": doc,
            "descripcion": desc.strip(),
            "oficina": oficina.strip(),
            "tipo": "credito" if sign == "+" else "debito",
        }
        (cuenta if section == "cuenta" else bolsillo).append(mov)
    return cuenta, bolsillo


def validate(summary: dict[str, float], cuenta: list[dict], bolsillo: list[dict]) -> dict:
    cuenta_net = sum(m["valor"] for m in cuenta)
    bolsillo_net = sum(m["valor"] for m in bolsillo)
    net_total = cuenta_net + bolsillo_net
    saldo_ant = summary.get("saldo_anterior", 0.0)
    nuevo_saldo_calc = saldo_ant + net_total
    nuevo_saldo_exp = summary.get("nuevo_saldo", 0.0)
    bolsillo_saldo_exp = summary.get("saldo_total_bolsillo", 0.0)
    tol = 1.0
    return {
        "cuenta_net": round(cuenta_net, 2),
        "bolsillo_net": round(bolsillo_net, 2),
        "net_total": round(net_total, 2),
        "saldo_calculado": round(nuevo_saldo_calc, 2),
        "saldo_esperado": nuevo_saldo_exp,
        "diff_saldo": round(nuevo_saldo_calc - nuevo_saldo_exp, 2),
        "bolsillo_saldo_esperado": bolsillo_saldo_exp,
        "ok_saldo": abs(nuevo_saldo_calc - nuevo_saldo_exp) < tol,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    text = run_pdftotext(Path(args.pdf))
    month, year = extract_period(text)
    summary = extract_summary(text)
    cuenta, bolsillo = extract_movements(text, year)
    val = validate(summary, cuenta, bolsillo)

    doc = {
        "producto": "davivienda-ahorros",
        "cuenta": "4884 1192 0561",
        "periodo": {"anio": year, "mes": month, "etiqueta": f"{year:04d}-{month:02d}"},
        "resumen": summary,
        "movimientos": cuenta,
        "bolsillo": bolsillo,
        "validacion": val,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False))

    if args.verbose:
        print(f"[{year:04d}-{month:02d}] movimientos cuenta: {len(cuenta)} bolsillo: {len(bolsillo)}", file=sys.stderr)
        print(f"  saldo anterior:  {summary.get('saldo_anterior'):>18,.2f}", file=sys.stderr)
        print(f"  cuenta net:      {val['cuenta_net']:>+18,.2f}", file=sys.stderr)
        print(f"  bolsillo net:    {val['bolsillo_net']:>+18,.2f}", file=sys.stderr)
        print(f"  saldo calculado: {val['saldo_calculado']:>18,.2f} (esperado {val['saldo_esperado']:,.2f}, diff {val['diff_saldo']:+,.2f})", file=sys.stderr)
        print(f"  validacion: {'OK' if val['ok_saldo'] else 'FAIL'}", file=sys.stderr)
    if not val["ok_saldo"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
