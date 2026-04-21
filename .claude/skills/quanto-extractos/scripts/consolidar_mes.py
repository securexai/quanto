"""Consolida métricas mensuales: patrimonio, deuda TC, intereses, ahorro neto."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def procesar(mes: str) -> None:
    dir_mes = Path(f"analisis/{mes}")
    ahorros = load(dir_mes / "davivienda-ahorros.json")
    tc_davi = load(dir_mes / "davivienda-tc.json")
    tc_davibank = load(dir_mes / "davibank-tc.json")
    nequi = load(dir_mes / "nequi.json")
    gastos = load(dir_mes / "gastos-por-categoria.json")

    # Patrimonio líquido al cierre: ahorros + nequi (TC es deuda, no activo)
    saldo_ahorros = ahorros["resumen"]["nuevo_saldo"]
    saldo_bolsillo = ahorros["resumen"].get("saldo_total_bolsillo", 0)
    saldo_nequi = nequi["resumen"]["saldo_actual"]
    liquidez_total = saldo_ahorros + saldo_nequi

    # Deuda TC al cierre: pago_total de cada extracto = lo que se debe pagar
    deuda_tc_davivienda = tc_davi["resumen"]["pago_total"]
    deuda_tc_davibank = tc_davibank["resumen"]["pago_total"]
    deuda_tc_total = deuda_tc_davivienda + deuda_tc_davibank

    # Intereses pagados en el periodo
    intereses_tc_davivienda = tc_davi["resumen"].get("intereses_corrientes", 0) + tc_davi["resumen"].get("intereses_mora", 0)
    intereses_tc_davibank = tc_davibank["resumen"].get("intereses_corrientes", 0) + tc_davibank["resumen"].get("intereses_mora", 0)
    intereses_total = intereses_tc_davivienda + intereses_tc_davibank
    comisiones_tc = (tc_davi["resumen"].get("otros_cargos", 0)
                     + sum(o["valor"] for o in tc_davibank["otros_cargos"] if o["valor"] > 0))

    # Compras del mes en TC (nuevas, no amortizaciones)
    compras_tc_davivienda = tc_davi["resumen"].get("compras_del_mes", 0)
    compras_tc_davibank = sum(
        c["valor_transaccion"]
        for c in tc_davibank["compras_periodo"] if not c.get("cancelado")
    )
    compras_tc_total = compras_tc_davivienda + compras_tc_davibank

    # Saldo pendiente (diferido) en TC
    diferido_davivienda = sum(
        c["saldo_pendiente"]
        for c in tc_davi["compras_periodo"] + tc_davi["compras_meses_anteriores"]
    )
    diferido_davibank = sum(
        c["saldo_pendiente"]
        for c in tc_davibank["compras_periodo"] + tc_davibank["compras_meses_anteriores"]
        if not c.get("cancelado")
    )
    diferido_total = diferido_davivienda + diferido_davibank

    # Rotación TC: cuánto del saldo se pagó
    pagos_tc_davivienda = tc_davi["resumen"].get("pagos_abonos", 0)
    pagos_tc_davibank = tc_davibank["resumen"].get("pagos", 0)
    pagos_tc_total = pagos_tc_davivienda + pagos_tc_davibank

    totales = gastos["totales"]

    resumen = {
        "mes": mes,
        "periodo": {
            "ahorros": ahorros["periodo"],
            "tc_davivienda": tc_davi["periodo"],
            "tc_davibank": tc_davibank["periodo"],
            "nequi": nequi["periodo"],
        },
        "patrimonio_liquido": {
            "davivienda_ahorros": saldo_ahorros,
            "davivienda_bolsillo": saldo_bolsillo,
            "nequi": saldo_nequi,
            "total": liquidez_total,
        },
        "deuda_tc": {
            "davivienda": deuda_tc_davivienda,
            "davibank": deuda_tc_davibank,
            "total": deuda_tc_total,
            "diferido_pendiente": diferido_total,
        },
        "flujos": {
            "ingresos": totales["ingresos"],
            "gastos": totales["gastos"],
            "ahorro_neto": totales["ahorro_neto"],
            "flujo_neto_inversion": totales.get("flujo_neto_inversion", 0),
        },
        "tarjetas_credito": {
            "compras_nuevas_mes": compras_tc_total,
            "compras_davivienda": compras_tc_davivienda,
            "compras_davibank": compras_tc_davibank,
            "pagos_realizados": pagos_tc_total,
            "intereses_pagados": intereses_total,
            "comisiones_y_seguros": comisiones_tc,
            "rotacion_pct": round(pagos_tc_total / max(compras_tc_total, 1) * 100, 1),
        },
        "patrimonio_neto_estimado": liquidez_total - deuda_tc_total,
    }

    out = dir_mes / "consolidado.json"
    out.write_text(json.dumps(resumen, indent=2, ensure_ascii=False))

    print(f"[{mes}] consolidado:")
    print(f"  liquidez total:         ${liquidez_total:>15,.0f}")
    print(f"  deuda TC total:         ${deuda_tc_total:>15,.0f}  (diferido: ${diferido_total:,.0f})")
    print(f"  patrimonio neto aprox:  ${liquidez_total - deuda_tc_total:>+15,.0f}")
    print(f"  ingresos:               ${totales['ingresos']:>15,.0f}")
    print(f"  gastos:                 ${totales['gastos']:>15,.0f}")
    print(f"  ahorro neto:            ${totales['ahorro_neto']:>+15,.0f}")
    print(f"  flujo inversion:        ${totales.get('flujo_neto_inversion', 0):>+15,.0f}")
    print(f"  compras TC nuevas:      ${compras_tc_total:>15,.0f}")
    print(f"  intereses TC pagados:   ${intereses_total:>15,.0f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", required=True)
    args = ap.parse_args()
    procesar(args.mes)


if __name__ == "__main__":
    main()
