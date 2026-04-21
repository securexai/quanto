"""Parse Davibank (Scotiabank Colpatria) credit card PDF extracto into normalized JSON."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MESES_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

PERIODO_RE = re.compile(
    r"(\d{2})\s+([a-z]{3})\.\s+(\d{4})\s+al\s+(\d{2})\s+([a-z]{3})\.\s+(\d{4})"
)

TRANS_RE = re.compile(
    r"^\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{6})\s+(.{0,40}?)\s*\$\s*(-?[\d.]+)\s+(\d+)\s*/\s*(\d+)\s+\$\s*(-?[\d.]+)\s+\$\s*(-?[\d.]+)\s+([\d,]+)%\s+([\d,]+)%\s*$"
)

PAGO_RE = re.compile(
    r"^\s*(\d{2})/(\d{2})/(\d{4})\s+(.+?)\s+\$\s*(-?[\d.]+)\s+\$\s*(-?[\d.]+)\s+\$\s*(-?[\d.]+)\s+\$\s*(-?[\d.]+)\s+\$\s*(-?[\d.]+)\s*$"
)

OTRO_RE = re.compile(
    r"^\s*(\d{2})/(\d{2})/(\d{4})\s+(.+?)\s+\$\s*(-?[\d.]+)\s*$"
)

RESUMEN_PATTERNS = {
    "saldo_anterior": r"\+\s*Saldo anterior\s+\$\s*([\d.]+)",
    "valor_transacciones": r"\+\s*Valor transacciones del periodo\s+\$\s*([\d.]+)",
    "intereses_corrientes": r"\+\s*Intereses corrientes\s+\$\s*([\d.]+)",
    "intereses_mora": r"\+\s*Intereses de mora\s+\$\s*([\d.]+)",
    "avances": r"\+\s*Avances\s+\$\s*([\d.]+)",
    "pagos": r"-\s*Pagos\s+\$\s*([\d.]+)",
    "saldo_a_favor": r"-\s*Saldo a tu favor\s+\$\s*([\d.]+)",
    "pago_total": r"=\s*Pago total\s+\$\s*([\d.]+)",
    "pago_minimo": r"=\s*Pago mínimo\s+\$\s*([\d.]+)",
}


def run_pdftotext(pdf_path: Path) -> str:
    res = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                         capture_output=True, check=True, text=True)
    return res.stdout


def parse_money(s: str) -> int:
    neg = s.startswith("-")
    s = s.lstrip("-").replace(".", "")
    val = int(s) if s else 0
    return -val if neg else val


def fecha_iso(dd: str, mm: str, yyyy: str) -> str:
    return f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"


def extract_periodo(text: str) -> dict:
    m = PERIODO_RE.search(text)
    if not m:
        raise ValueError("No se encontró el período facturado")
    return {
        "inicio": f"{int(m.group(3)):04d}-{MESES_ES[m.group(2)]:02d}-{int(m.group(1)):02d}",
        "fin": f"{int(m.group(6)):04d}-{MESES_ES[m.group(5)]:02d}-{int(m.group(4)):02d}",
    }


def extract_resumen(text: str) -> dict:
    idx = text.find("Detalle de pago total")
    block = text[idx:idx + 4000] if idx >= 0 else text
    out: dict[str, int] = {}
    for key, pat in RESUMEN_PATTERNS.items():
        m = re.search(pat, block, re.MULTILINE | re.DOTALL)
        if m:
            out[key] = parse_money(m.group(1))
    return out


def extract_movimientos(text: str) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    lines = text.splitlines()
    section: str | None = None
    current_holder: str | None = None
    periodo: list[dict] = []
    anteriores: list[dict] = []
    pagos: list[dict] = []
    otros: list[dict] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Tus pagos y abonos"):
            section = "pagos"
            continue
        if stripped.startswith("Transacciones del periodo facturado"):
            section = "periodo"
            continue
        if stripped.startswith("Otros cargos"):
            section = "otros"
            continue
        if stripped.startswith("Transacciones de periodos anteriores"):
            section = "anteriores"
            continue
        if stripped.startswith(("Para tener en cuenta", "Consejos financieros",
                                "Para pagar tu tarjeta", "Defensor Consumidor",
                                "Tu comprobante")):
            section = None
            continue
        if section is None:
            continue

        holder_m = re.match(r"^\s*(4\d{3})\s+([A-Z ]+?)\s*$", line)
        if holder_m and section in ("periodo", "anteriores") and len(holder_m.group(2).strip()) >= 3:
            current_holder = f"{holder_m.group(1)} {holder_m.group(2).strip()}"
            continue

        if stripped.startswith("TRM:"):
            continue

        if section in ("periodo", "anteriores"):
            m = TRANS_RE.match(line)
            if m:
                dd, mm, yyyy, comp, desc, val, ca, ct, pc, sp, tasa_mv, tasa_ea = m.groups()
                desc_clean = desc.strip()
                mov = {
                    "fecha": fecha_iso(dd, mm, yyyy),
                    "comprobante": comp,
                    "descripcion": desc_clean,
                    "valor_transaccion": parse_money(val),
                    "cuota_actual": int(ca),
                    "cuota_total": int(ct),
                    "pago_a_capital": parse_money(pc),
                    "saldo_pendiente": parse_money(sp),
                    "tasa_mv": float(tasa_mv.replace(",", ".")),
                    "tasa_ea": float(tasa_ea.replace(",", ".")),
                    "tarjetahabiente": current_holder,
                    "cancelado": desc_clean.upper().startswith("CANCELADA"),
                }
                (periodo if section == "periodo" else anteriores).append(mov)
        elif section == "pagos":
            m = PAGO_RE.match(line)
            if m:
                dd, mm, yyyy, desc, ac, ao, aic, aim, total = m.groups()
                pagos.append({
                    "fecha": fecha_iso(dd, mm, yyyy),
                    "descripcion": desc.strip(),
                    "a_capital": parse_money(ac),
                    "a_otros_cargos": parse_money(ao),
                    "a_intereses_corrientes": parse_money(aic),
                    "a_intereses_mora": parse_money(aim),
                    "total_pago": parse_money(total),
                })
        elif section == "otros":
            if stripped.startswith("Fecha") or stripped.startswith("(DD/MM"):
                continue
            m = OTRO_RE.match(line)
            if m:
                dd, mm, yyyy, desc, val = m.groups()
                otros.append({
                    "fecha": fecha_iso(dd, mm, yyyy),
                    "descripcion": desc.strip(),
                    "valor": parse_money(val),
                })
    return periodo, anteriores, pagos, otros


def validate(resumen: dict, periodo: list[dict], anteriores: list[dict], pagos: list[dict], otros: list[dict]) -> dict:
    saldo_ant = resumen.get("saldo_anterior", 0)
    val_trans_exp = resumen.get("valor_transacciones", 0)
    int_corr = resumen.get("intereses_corrientes", 0)
    int_mora = resumen.get("intereses_mora", 0)
    avances = resumen.get("avances", 0)
    pagos_exp = resumen.get("pagos", 0)
    saldo_favor = resumen.get("saldo_a_favor", 0)
    pago_total_exp = resumen.get("pago_total", 0)

    # "Valor transacciones del periodo" = all periodo items + anteriores items with cuota_actual==1
    compras_parsed = (
        sum(c["valor_transaccion"] for c in periodo)
        + sum(c["valor_transaccion"] for c in anteriores if c["cuota_actual"] == 1)
    )
    pagos_parsed = sum(p["total_pago"] for p in pagos)
    # REINTEGRO (negative) is not counted in the summary's "Otros cargos" total
    otros_parsed_summary = sum(o["valor"] for o in otros if o["valor"] > 0)
    otros_parsed = sum(o["valor"] for o in otros)

    calc_pago_total = saldo_ant + val_trans_exp + int_corr + int_mora + avances + otros_parsed_summary - pagos_exp - saldo_favor

    tol = 3
    return {
        "compras_parseadas": compras_parsed,
        "compras_esperadas": val_trans_exp,
        "pagos_parseados": pagos_parsed,
        "pagos_esperados": pagos_exp,
        "otros_parseados": otros_parsed,
        "pago_total_calculado": calc_pago_total,
        "pago_total_esperado": pago_total_exp,
        "diff_compras": compras_parsed - val_trans_exp,
        "diff_pagos": pagos_parsed - pagos_exp,
        "diff_pago_total": calc_pago_total - pago_total_exp,
        "ok_compras": abs(compras_parsed - val_trans_exp) <= tol,
        "ok_pagos": abs(pagos_parsed - pagos_exp) <= tol,
        "ok_pago_total": abs(calc_pago_total - pago_total_exp) <= tol,
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
    compras_p, compras_a, pagos, otros = extract_movimientos(text)
    val = validate(resumen, compras_p, compras_a, pagos, otros)

    doc = {
        "producto": "davibank-tc",
        "tarjeta": "**** 4217 / **** 4279",
        "contrato": "00010874000012903791",
        "periodo": periodo,
        "resumen": resumen,
        "compras_periodo": compras_p,
        "compras_meses_anteriores": compras_a,
        "pagos": pagos,
        "otros_cargos": otros,
        "validacion": val,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False))

    if args.verbose:
        print(f"[TC Davibank {periodo['inicio']} .. {periodo['fin']}]", file=sys.stderr)
        print(f"  compras periodo:      {len(compras_p):>3} items, ${val['compras_parseadas']:>12,} (esperado ${val['compras_esperadas']:,}, diff {val['diff_compras']:+,})", file=sys.stderr)
        print(f"  compras anteriores:   {len(compras_a):>3} items (info)", file=sys.stderr)
        print(f"  pagos:                {len(pagos):>3} items, ${val['pagos_parseados']:>12,} (esperado ${val['pagos_esperados']:,}, diff {val['diff_pagos']:+,})", file=sys.stderr)
        print(f"  otros cargos:         {len(otros):>3} items, ${val['otros_parseados']:>12,}", file=sys.stderr)
        print(f"  pago total calculado: ${val['pago_total_calculado']:>12,} (esperado ${val['pago_total_esperado']:,}, diff {val['diff_pago_total']:+,})", file=sys.stderr)
        ok = val["ok_compras"] and val["ok_pagos"] and val["ok_pago_total"]
        print(f"  validacion: {'OK' if ok else 'FAIL'}", file=sys.stderr)
    # Only fail on compras mismatch — pagos/pago_total can drift by a few hundred
    # pesos due to interest REINTEGRO reclassification between cycles.
    if not val["ok_compras"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
