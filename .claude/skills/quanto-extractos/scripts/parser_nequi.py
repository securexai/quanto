"""Parse Nequi PDF extracto into normalized JSON."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PERIODO_RE = re.compile(
    r"período de:\s*(\d{4})/(\d{2})/(\d{2})\s*a\s*(\d{4})/(\d{2})/(\d{2})"
)
RESUMEN_PATTERNS = {
    "saldo_anterior": r"Saldo anterior\s+\$([\d,]+\.\d{2})",
    "saldo_promedio": r"Saldo promedio\s+\$([\d,]+\.\d{2})",
    "total_abonos": r"Total abonos\s+\$([\d,]+\.\d{2})",
    "cuentas_por_cobrar": r"Cuentas por cobrar\s+\$([\d,]+\.\d{2})",
    "total_cargos": r"Total cargos\s+\$([\d,]+\.\d{2})",
    "intereses_pagados": r"Valor de intereses pagados\s+\$([\d,]+\.\d{2})",
    "saldo_actual": r"Saldo actual\s+\$([\d,]+\.\d{2})",
    "retefuente": r"Retefuente\s+\$([\d,]+\.\d{2})",
}

MOV_RE = re.compile(
    r"^\s*(\d{2})/(\d{2})/(\d{4})\s+(.+?)\s+\$(-?[\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$"
)


def run_pdftotext(pdf_path: Path) -> str:
    res = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                         capture_output=True, check=True, text=True)
    return res.stdout


def parse_money(s: str) -> float:
    return float(s.replace(",", ""))


def extract_periodo(text: str) -> dict:
    m = PERIODO_RE.search(text)
    if not m:
        raise ValueError("No se encontró el periodo")
    return {
        "inicio": f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
        "fin": f"{m.group(4)}-{m.group(5)}-{m.group(6)}",
    }


def extract_resumen(text: str) -> dict:
    out: dict[str, float] = {}
    for key, pat in RESUMEN_PATTERNS.items():
        m = re.search(pat, text)
        if m:
            out[key] = parse_money(m.group(1))
    return out


def extract_movimientos(text: str) -> list[dict]:
    movs = []
    for line in text.splitlines():
        m = MOV_RE.match(line)
        if m:
            dd, mm, yyyy, desc, valor, saldo = m.groups()
            movs.append({
                "fecha": f"{yyyy}-{mm}-{dd}",
                "descripcion": desc.strip(),
                "valor": parse_money(valor),
                "saldo": parse_money(saldo),
                "tipo": "credito" if not valor.startswith("-") else "debito",
            })
    return movs


def validate(resumen: dict, movs: list[dict]) -> dict:
    creditos = sum(m["valor"] for m in movs if m["valor"] > 0)
    debitos = -sum(m["valor"] for m in movs if m["valor"] < 0)
    saldo_ant = resumen.get("saldo_anterior", 0.0)
    saldo_final_calc = saldo_ant + creditos - debitos
    saldo_final_exp = resumen.get("saldo_actual", 0.0)
    exp_abonos = resumen.get("total_abonos", 0.0)
    exp_cargos = resumen.get("total_cargos", 0.0)
    tol = 0.5
    return {
        "creditos_parseados": round(creditos, 2),
        "debitos_parseados": round(debitos, 2),
        "abonos_esperados": exp_abonos,
        "cargos_esperados": exp_cargos,
        "saldo_calculado": round(saldo_final_calc, 2),
        "saldo_esperado": saldo_final_exp,
        "diff_saldo": round(saldo_final_calc - saldo_final_exp, 2),
        "diff_creditos": round(creditos - exp_abonos, 2),
        "diff_debitos": round(debitos - exp_cargos, 2),
        "ok_saldo": abs(saldo_final_calc - saldo_final_exp) < tol,
        "ok_creditos": abs(creditos - exp_abonos) < tol,
        "ok_debitos": abs(debitos - exp_cargos) < tol,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    text = run_pdftotext(Path(args.pdf))
    periodo = extract_periodo(text)
    resumen = extract_resumen(text)
    movs = extract_movimientos(text)
    val = validate(resumen, movs)

    doc = {
        "producto": "nequi",
        "deposito": "3153716395",
        "periodo": periodo,
        "resumen": resumen,
        "movimientos": movs,
        "validacion": val,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False))

    if args.verbose:
        print(f"[Nequi {periodo['inicio']} .. {periodo['fin']}]", file=sys.stderr)
        print(f"  movimientos: {len(movs)}", file=sys.stderr)
        print(f"  saldo anterior:   ${resumen.get('saldo_anterior', 0):>12,.2f}", file=sys.stderr)
        print(f"  creditos:         ${val['creditos_parseados']:>12,.2f} (esperado ${val['abonos_esperados']:,.2f}, diff {val['diff_creditos']:+,.2f})", file=sys.stderr)
        print(f"  debitos:          ${val['debitos_parseados']:>12,.2f} (esperado ${val['cargos_esperados']:,.2f}, diff {val['diff_debitos']:+,.2f})", file=sys.stderr)
        print(f"  saldo calculado:  ${val['saldo_calculado']:>12,.2f} (esperado ${val['saldo_esperado']:,.2f}, diff {val['diff_saldo']:+,.2f})", file=sys.stderr)
        ok = val["ok_saldo"] and val["ok_creditos"] and val["ok_debitos"]
        print(f"  validacion: {'OK' if ok else 'FAIL'}", file=sys.stderr)
    if not (val["ok_saldo"] and val["ok_creditos"] and val["ok_debitos"]):
        sys.exit(2)


if __name__ == "__main__":
    main()
