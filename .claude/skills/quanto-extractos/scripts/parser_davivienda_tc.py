#!/usr/bin/env python3
"""Parse Davivienda credit card PDF extracto into normalized JSON."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MESES_ABREV = {
    "Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12,
}

PERIODO_RE = re.compile(
    r"Periodo de facturación:.*?(\d{2})/([A-Z][a-z]{2})/(\d{4})\s*-\s*(\d{2})/([A-Z][a-z]{2})/(\d{4})",
    re.DOTALL,
)

MOV_RE = re.compile(
    r"^\s*(\d{2})([A-Z][a-z]{2})(\d{4})\s+(.+?)\s{2,}\$([\d,]+)\s+(\d+)\s*de\s*(\d+)\s+\$([\d,]+)\s+\$([\d,]+)\s+\$([\d,]+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s*$"
)
PAGO_RE = re.compile(
    r"^\s*(\d{2})([A-Z][a-z]{2})(\d{4})\s+\$([\d,]+)\s+\$([\d,]+)\s+\$([\d,]+)\s+\$([\d,]+)\s+\$([\d,]+)\s+\$([\d,]+)\s+\$([\d,]+)\s+\$([\d,]+)\s*$"
)
OTRO_CARGO_RE = re.compile(
    r"^\s*(\d{2})([A-Z][a-z]{2})(\d{4})\s+(.+?)\s{2,}(\d{8})\s+\$([\d,]+)\s*$"
)

RESUMEN_PATTERNS = {
    "saldo_mes_anterior": r"Saldo mes anterior\s+\$([\d,]+)",
    "compras_del_mes": r"\+Compras del mes\s+\$([\d,]+)",
    "avances_del_mes": r"\+Avances del mes\s+\$([\d,]+)",
    "cuota_manejo": r"\+Cuota de manejo\s+\$([\d,]+)",
    "intereses_corrientes": r"\+Intereses corrientes\s+\$([\d,]+)",
    "intereses_mora": r"\+Intereses de mora\s+\$([\d,]+)",
    "otros_cargos": r"\+Otros cargos\s+\$([\d,]+)",
    "pagos_abonos": r"-Pagos y abonos\s+\$([\d,]+)",
    "pago_total": r"Pago total\s+\$([\d,]+)",
    "saldo_a_favor": r"Saldo a favor\s+\$([\d,]+)",
    "pago_minimo": r"Pago mínimo\s+\$([\d,]+)",
}


def run_pdftotext(pdf_path: Path) -> str:
    res = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, check=True, text=True,
    )
    return res.stdout


def parse_money(s: str) -> int:
    return int(s.replace(",", ""))


def fecha_iso(dd: str, mmm: str, yyyy: str) -> str:
    return f"{int(yyyy):04d}-{MESES_ABREV[mmm]:02d}-{int(dd):02d}"


def extract_periodo(text: str) -> dict:
    m = PERIODO_RE.search(text)
    if not m:
        raise ValueError("No se encontró el periodo de facturación")
    return {
        "inicio": fecha_iso(m.group(1), m.group(2), m.group(3)),
        "fin": fecha_iso(m.group(4), m.group(5), m.group(6)),
    }


def extract_resumen(text: str) -> dict:
    out: dict[str, int] = {}
    for key, pat in RESUMEN_PATTERNS.items():
        m = re.search(pat, text, re.MULTILINE)
        if m:
            out[key] = parse_money(m.group(1))
    return out


def extract_movimientos(text: str) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    lines = text.splitlines()
    section: str | None = None
    compras_periodo: list[dict] = []
    compras_anteriores: list[dict] = []
    pagos: list[dict] = []
    otros_cargos: list[dict] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Detalle aplicación de pagos y abonos"):
            section = "pagos"
            continue
        if stripped.startswith("Detalle de movimientos del mes"):
            section = "periodo"
            continue
        if stripped.startswith("Movimientos meses anteriores"):
            section = "anteriores"
            continue
        if stripped.startswith("Detalle otros cargos"):
            section = "otros"
            continue
        if stripped.startswith(("Para pagar tu tarjeta", "Para tener en cuenta",
                                 "Usted podrá conocer", "NUNCA ENTREGUE")):
            section = None
            continue
        if section is None:
            continue

        if section in ("periodo", "anteriores"):
            m = MOV_RE.match(line)
            if m:
                dd, mmm, yyyy, desc, val, ca, ct, intr, vp, sp, pts, tr, tasa = m.groups()
                mov = {
                    "fecha": fecha_iso(dd, mmm, yyyy),
                    "descripcion": desc.strip(),
                    "valor_transaccion": parse_money(val),
                    "cuota_actual": int(ca),
                    "cuota_total": int(ct),
                    "valor_intereses": parse_money(intr),
                    "valor_a_pagar": parse_money(vp),
                    "saldo_pendiente": parse_money(sp),
                    "puntos": int(pts),
                    "trans_num": tr,
                    "tasa_ea": float(tasa),
                }
                (compras_periodo if section == "periodo" else compras_anteriores).append(mov)
        elif section == "pagos":
            m = PAGO_RE.match(line)
            if m:
                g = m.groups()
                pagos.append({
                    "fecha": fecha_iso(g[0], g[1], g[2]),
                    "total_pagado": parse_money(g[3]),
                    "aplicado_compras": parse_money(g[4]),
                    "aplicado_avances": parse_money(g[5]),
                    "aplicado_intereses": parse_money(g[6]),
                    "aplicado_intereses_mora": parse_money(g[7]),
                    "aplicado_cuota_manejo": parse_money(g[8]),
                    "aplicado_otros_cargos": parse_money(g[9]),
                    "saldo_a_favor": parse_money(g[10]),
                })
        elif section == "otros":
            m = OTRO_CARGO_RE.match(line)
            if m:
                dd, mmm, yyyy, desc, num, val = m.groups()
                otros_cargos.append({
                    "fecha": fecha_iso(dd, mmm, yyyy),
                    "descripcion": desc.strip(),
                    "trans_num": num,
                    "valor": parse_money(val),
                })
    return compras_periodo, compras_anteriores, pagos, otros_cargos


def validate(resumen: dict, compras: list[dict], pagos: list[dict], otros: list[dict]) -> dict:
    saldo_ant = resumen.get("saldo_mes_anterior", 0)
    compras_exp = resumen.get("compras_del_mes", 0)
    avances_exp = resumen.get("avances_del_mes", 0)
    cuota_manejo = resumen.get("cuota_manejo", 0)
    intereses_corr = resumen.get("intereses_corrientes", 0)
    intereses_mora = resumen.get("intereses_mora", 0)
    otros_exp = resumen.get("otros_cargos", 0)
    pagos_exp = resumen.get("pagos_abonos", 0)
    pago_total_exp = resumen.get("pago_total", 0)

    compras_parsed = sum(
        c["valor_transaccion"] for c in compras
        if "INTERES CORRIEN" not in c["descripcion"].upper()
    )
    pagos_parsed = sum(p["total_pagado"] for p in pagos)
    otros_parsed = sum(o["valor"] for o in otros)

    calc_pago_total = (
        saldo_ant + compras_exp + avances_exp + cuota_manejo
        + intereses_corr + intereses_mora + otros_exp - pagos_exp
    )

    tol = 2
    return {
        "compras_parseadas": compras_parsed,
        "compras_esperadas": compras_exp,
        "pagos_parseados": pagos_parsed,
        "pagos_esperados": pagos_exp,
        "otros_parseados": otros_parsed,
        "otros_esperados": otros_exp,
        "pago_total_calculado": calc_pago_total,
        "pago_total_esperado": pago_total_exp,
        "diff_compras": compras_parsed - compras_exp,
        "diff_pagos": pagos_parsed - pagos_exp,
        "diff_otros": otros_parsed - otros_exp,
        "diff_pago_total": calc_pago_total - pago_total_exp,
        "ok_compras": abs(compras_parsed - compras_exp) <= tol,
        "ok_pagos": abs(pagos_parsed - pagos_exp) <= tol,
        "ok_otros": abs(otros_parsed - otros_exp) <= tol,
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
    compras_periodo, compras_anteriores, pagos, otros = extract_movimientos(text)
    val = validate(resumen, compras_periodo, pagos, otros)

    doc = {
        "producto": "davivienda-tc",
        "tarjeta": "4410 **** **** 6329",
        "periodo": periodo,
        "resumen": resumen,
        "compras_periodo": compras_periodo,
        "compras_meses_anteriores": compras_anteriores,
        "pagos": pagos,
        "otros_cargos": otros,
        "validacion": val,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False))

    if args.verbose:
        print(f"[TC Davivienda {periodo['inicio']} .. {periodo['fin']}]", file=sys.stderr)
        print(f"  compras periodo:      {len(compras_periodo):>3} items, ${val['compras_parseadas']:>12,} (esperado ${val['compras_esperadas']:,}, diff {val['diff_compras']:+,})", file=sys.stderr)
        print(f"  compras anteriores:   {len(compras_anteriores):>3} items (info)", file=sys.stderr)
        print(f"  pagos:                {len(pagos):>3} items, ${val['pagos_parseados']:>12,} (esperado ${val['pagos_esperados']:,}, diff {val['diff_pagos']:+,})", file=sys.stderr)
        print(f"  otros cargos:         {len(otros):>3} items, ${val['otros_parseados']:>12,} (esperado ${val['otros_esperados']:,}, diff {val['diff_otros']:+,})", file=sys.stderr)
        print(f"  pago total calculado: ${val['pago_total_calculado']:>12,} (esperado ${val['pago_total_esperado']:,}, diff {val['diff_pago_total']:+,})", file=sys.stderr)
        ok = val["ok_compras"] and val["ok_pagos"] and val["ok_otros"] and val["ok_pago_total"]
        print(f"  validacion: {'OK' if ok else 'FAIL'}", file=sys.stderr)
    if not (val["ok_compras"] and val["ok_pagos"] and val["ok_otros"] and val["ok_pago_total"]):
        sys.exit(2)


if __name__ == "__main__":
    main()
