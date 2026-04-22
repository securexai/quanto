"""Match internal transfers across bank products: mark TC payments from ahorros
and Nequi fundings (BRE-B) from Davivienda ahorros so they don't double-count as
expense/income."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def dump(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def to_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def match_tc_davivienda(ahorros: dict, tc_davi: dict) -> list[dict]:
    """Davivienda ahorros shows debits like 'Pago Tarj. Credito N4410804554026329'.
    Davivienda TC shows a matching payment in 'pagos' list."""
    matches = []
    ahorros_pagos_tc = [
        m
        for m in ahorros["movimientos"]
        if "Pago Tarj. Credito" in m["descripcion"] and m["valor"] < 0
    ]
    tc_pagos = list(tc_davi.get("pagos", []))
    used_tc_idx = set()
    for mov in ahorros_pagos_tc:
        monto = abs(mov["valor"])
        fecha_ah = to_date(mov["fecha"])
        best_idx = None
        for i, p in enumerate(tc_pagos):
            if i in used_tc_idx:
                continue
            fecha_tc = to_date(p["fecha"])
            if abs(p["total_pagado"] - monto) <= 1 and abs((fecha_tc - fecha_ah).days) <= 3:
                best_idx = i
                break
        if best_idx is not None:
            used_tc_idx.add(best_idx)
            matches.append(
                {
                    "tipo": "pago_tc_davivienda",
                    "ahorros_doc": mov["doc"],
                    "ahorros_fecha": mov["fecha"],
                    "tc_fecha": tc_pagos[best_idx]["fecha"],
                    "monto": monto,
                }
            )
            mov["transferencia_interna"] = True
            mov["match_tipo"] = "pago_tc_davivienda"
    return matches


def match_tc_davibank(ahorros: dict, tc_davibank: dict) -> list[dict]:
    """Davibank TC payments ('GRACIAS POR SU PAGO') are funded from the Davivienda
    ahorros account as 'Compra PAGOS ELECTRONICOS SCOT' (PSE) debits."""
    matches = []
    pse_debits = [
        m
        for m in ahorros["movimientos"]
        if "PAGOS ELECTRONICOS SCOT" in m["descripcion"].upper() and m["valor"] < 0
    ]
    tc_pagos = list(tc_davibank.get("pagos", []))
    used = set()
    for mov in pse_debits:
        monto = abs(mov["valor"])
        fecha_ah = to_date(mov["fecha"])
        best_idx = None
        for i, p in enumerate(tc_pagos):
            if i in used:
                continue
            fecha_tc = to_date(p["fecha"])
            if abs(p["total_pago"] - monto) <= 2 and abs((fecha_tc - fecha_ah).days) <= 3:
                best_idx = i
                break
        if best_idx is not None:
            used.add(best_idx)
            matches.append(
                {
                    "tipo": "pago_tc_davibank",
                    "ahorros_doc": mov["doc"],
                    "ahorros_fecha": mov["fecha"],
                    "tc_fecha": tc_pagos[best_idx]["fecha"],
                    "monto": monto,
                }
            )
            mov["transferencia_interna"] = True
            mov["match_tipo"] = "pago_tc_davibank"
    return matches


def match_nequi_fondeo(ahorros: dict, nequi: dict) -> list[dict]:
    """Nequi fondeo: ahorros debit 'Transferencia A Llave Otra Entidad' (Redeban BreB)
    matches Nequi credit 'RECIBI POR BRE-B DE: SERGIO'."""
    matches = []
    breb_out = [
        m
        for m in ahorros["movimientos"]
        if "Llave Otra Entidad" in m["descripcion"]
        and "Transferencia A" in m["descripcion"]
        and m["valor"] < 0
    ]
    nequi_breb_in = [
        m
        for m in nequi["movimientos"]
        if "RECIBI POR BRE-B" in m["descripcion"].upper() and m["valor"] > 0
    ]
    used_ah = set()
    used_ne = set()
    for i, ni in enumerate(nequi_breb_in):
        monto = ni["valor"]
        fecha_ne = to_date(ni["fecha"])
        best_idx = None
        for j, mv in enumerate(breb_out):
            if j in used_ah:
                continue
            if abs(abs(mv["valor"]) - monto) <= 0.01:
                fecha_ah = to_date(mv["fecha"])
                if abs((fecha_ne - fecha_ah).days) <= 2:
                    best_idx = j
                    break
        if best_idx is not None:
            used_ah.add(best_idx)
            used_ne.add(i)
            matches.append(
                {
                    "tipo": "fondeo_nequi",
                    "ahorros_doc": breb_out[best_idx]["doc"],
                    "ahorros_fecha": breb_out[best_idx]["fecha"],
                    "nequi_fecha": ni["fecha"],
                    "monto": monto,
                }
            )
            breb_out[best_idx]["transferencia_interna"] = True
            breb_out[best_idx]["match_tipo"] = "fondeo_nequi"
            ni["transferencia_interna"] = True
            ni["match_tipo"] = "fondeo_nequi"
    return matches


def match_daviplata(ahorros: dict) -> list[dict]:
    """Davivienda ahorros → Daviplata: both products of same user. Marked as internal."""
    matches = []
    for m in ahorros["movimientos"]:
        if re.search(r"Daviplata", m["descripcion"], re.I) and m["valor"] < 0:
            m["transferencia_interna"] = True
            m["match_tipo"] = "envio_daviplata"
            matches.append(
                {
                    "tipo": "envio_daviplata",
                    "fecha": m["fecha"],
                    "doc": m["doc"],
                    "monto": abs(m["valor"]),
                }
            )
    return matches


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ahorros", required=True)
    ap.add_argument("--tc-davivienda", required=True)
    ap.add_argument("--tc-davibank", required=True)
    ap.add_argument("--nequi", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    ahorros = load(args.ahorros)
    tc_davi = load(args.tc_davivienda)
    tc_davibank = load(args.tc_davibank)
    nequi = load(args.nequi)

    result = {
        "matches_tc_davivienda": match_tc_davivienda(ahorros, tc_davi),
        "matches_tc_davibank": match_tc_davibank(ahorros, tc_davibank),
        "matches_nequi_fondeo": match_nequi_fondeo(ahorros, nequi),
        "matches_daviplata": match_daviplata(ahorros),
    }
    result["resumen"] = {
        "tc_davivienda_pagos": len(result["matches_tc_davivienda"]),
        "tc_davibank_pagos": len(result["matches_tc_davibank"]),
        "nequi_fondeos": len(result["matches_nequi_fondeo"]),
        "envios_daviplata": len(result["matches_daviplata"]),
        "monto_total_internos": sum(
            m["monto"]
            for lst in (
                result["matches_tc_davivienda"],
                result["matches_tc_davibank"],
                result["matches_nequi_fondeo"],
                result["matches_daviplata"],
            )
            for m in lst
        ),
    }

    dump(args.ahorros, ahorros)
    dump(args.nequi, nequi)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    dump(args.output, result)

    print("[cross-match]")
    print(f"  pagos TC Davivienda: {result['resumen']['tc_davivienda_pagos']}")
    print(f"  pagos TC Davibank:   {result['resumen']['tc_davibank_pagos']}")
    print(f"  fondeos Nequi:       {result['resumen']['nequi_fondeos']}")
    print(f"  envios Daviplata:    {result['resumen']['envios_daviplata']}")
    print(f"  total transferencias internas: ${result['resumen']['monto_total_internos']:,.2f}")


if __name__ == "__main__":
    main()
