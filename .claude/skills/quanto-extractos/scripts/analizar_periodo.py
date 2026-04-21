#!/usr/bin/env python3
"""Agrega métricas de varios meses, detecta suscripciones recurrentes y anomalías."""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def procesar(meses: list[str], output: str) -> None:
    consolidados = []
    movimientos_all = []
    gastos_all = []

    for mes in meses:
        dir_mes = Path(f"analisis/{mes}")
        consolidados.append(load(dir_mes / "consolidado.json"))
        movs = load(dir_mes / "movimientos-categorizados.json")["movimientos"]
        for m in movs:
            m["mes_extracto"] = mes
        movimientos_all.extend(movs)
        gastos_all.append(load(dir_mes / "gastos-por-categoria.json"))

    total_ingresos = sum(c["flujos"]["ingresos"] for c in consolidados)
    total_gastos = sum(c["flujos"]["gastos"] for c in consolidados)
    total_ahorro = total_ingresos - total_gastos
    total_inversion = sum(c["flujos"]["flujo_neto_inversion"] for c in consolidados)
    total_intereses_tc = sum(c["tarjetas_credito"]["intereses_pagados"] for c in consolidados)
    total_comisiones = sum(c["tarjetas_credito"]["comisiones_y_seguros"] for c in consolidados)
    total_compras_tc = sum(c["tarjetas_credito"]["compras_nuevas_mes"] for c in consolidados)

    gastos_agregados: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g in gastos_all:
        for cat, data in g["gastos"].items():
            for sub, val in data["subcategorias"].items():
                gastos_agregados[cat][sub] += val
    gastos_trim = {
        cat: {
            "total": sum(subs.values()),
            "subcategorias": dict(sorted(subs.items(), key=lambda x: -x[1])),
        }
        for cat, subs in gastos_agregados.items()
    }
    gastos_trim = dict(sorted(gastos_trim.items(), key=lambda x: -x[1]["total"]))

    ingresos_agregados: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g in gastos_all:
        for cat, data in g["ingresos"].items():
            for sub, val in data["subcategorias"].items():
                ingresos_agregados[cat][sub] += val
    ingresos_trim = {
        cat: {
            "total": sum(subs.values()),
            "subcategorias": dict(sorted(subs.items(), key=lambda x: -x[1])),
        }
        for cat, subs in ingresos_agregados.items()
    }
    ingresos_trim = dict(sorted(ingresos_trim.items(), key=lambda x: -x[1]["total"]))

    by_merchant: dict[str, list[dict]] = defaultdict(list)
    for m in movimientos_all:
        if (m["valor"] < 0
            and m["producto"] in ("davivienda-tc", "davibank-tc")
            and m["categoria"] not in ("transferencia_interna", "inversion")):
            merchant_key = m["descripcion"].upper().strip()
            by_merchant[merchant_key].append(m)

    suscripciones = []
    for merchant, items in by_merchant.items():
        meses_vistos = sorted(set(i["mes_extracto"] for i in items))
        if len(meses_vistos) == len(meses):
            montos = [abs(i["valor"]) for i in items]
            avg = statistics.mean(montos)
            if avg < 500:
                continue
            stdev = statistics.pstdev(montos) if len(montos) > 1 else 0
            cv = stdev / avg if avg else 0
            suscripciones.append({
                "merchant": merchant,
                "categoria": items[0]["categoria"],
                "subcategoria": items[0]["subcategoria"],
                "meses_vistos": meses_vistos,
                "cantidad_cobros": len(items),
                "monto_promedio": round(avg),
                "monto_min": min(montos),
                "monto_max": max(montos),
                "estable": cv <= 0.2,
                "coef_variacion": round(cv, 3),
            })
    suscripciones.sort(key=lambda x: -x["monto_promedio"])

    anomalias = []
    gastos_movs = [m for m in movimientos_all
                   if m["valor"] < 0 and m["categoria"] not in ("transferencia_interna", "inversion")]
    gastos_por_cat: dict[str, list[dict]] = defaultdict(list)
    for m in gastos_movs:
        gastos_por_cat[m["categoria"]].append(m)
    for cat, items in gastos_por_cat.items():
        if len(items) < 4:
            continue
        montos = [abs(m["valor"]) for m in items]
        media = statistics.mean(montos)
        sigma = statistics.pstdev(montos)
        if sigma == 0:
            continue
        umbral = media + 3 * sigma
        for m in items:
            if abs(m["valor"]) > umbral and abs(m["valor"]) > 50_000:
                anomalias.append({
                    "fecha": m["fecha"],
                    "producto": m["producto"],
                    "descripcion": m["descripcion"],
                    "valor": m["valor"],
                    "categoria": cat,
                    "subcategoria": m["subcategoria"],
                    "media_categoria": round(media),
                    "desviacion": round(sigma),
                    "z_score": round((abs(m["valor"]) - media) / sigma, 2),
                })
    anomalias.sort(key=lambda x: -x["z_score"])

    progresion = [
        {
            "mes": c["mes"],
            "ingresos": c["flujos"]["ingresos"],
            "gastos": c["flujos"]["gastos"],
            "ahorro_neto": c["flujos"]["ahorro_neto"],
            "patrimonio_liquido": c["patrimonio_liquido"]["total"],
            "deuda_tc": c["deuda_tc"]["total"],
            "patrimonio_neto": c["patrimonio_neto_estimado"],
            "compras_tc": c["tarjetas_credito"]["compras_nuevas_mes"],
            "intereses_tc": c["tarjetas_credito"]["intereses_pagados"],
        }
        for c in consolidados
    ]

    ultimo = consolidados[-1]
    inicio = consolidados[0]
    result = {
        "periodo": {"meses": meses, "inicio": meses[0], "fin": meses[-1]},
        "totales": {
            "ingresos": total_ingresos,
            "gastos": total_gastos,
            "ahorro_neto": total_ahorro,
            "tasa_ahorro_pct": round(total_ahorro / max(total_ingresos, 1) * 100, 1),
            "flujo_inversion": total_inversion,
            "intereses_tc_pagados": total_intereses_tc,
            "comisiones_y_seguros_tc": total_comisiones,
            "compras_tc_totales": total_compras_tc,
        },
        "patrimonio": {
            "liquidez_inicio": inicio["patrimonio_liquido"]["total"],
            "liquidez_fin": ultimo["patrimonio_liquido"]["total"],
            "delta_liquidez": ultimo["patrimonio_liquido"]["total"] - inicio["patrimonio_liquido"]["total"],
            "deuda_tc_inicio": inicio["deuda_tc"]["total"],
            "deuda_tc_fin": ultimo["deuda_tc"]["total"],
            "delta_deuda_tc": ultimo["deuda_tc"]["total"] - inicio["deuda_tc"]["total"],
            "patrimonio_neto_inicio": inicio["patrimonio_neto_estimado"],
            "patrimonio_neto_fin": ultimo["patrimonio_neto_estimado"],
            "delta_patrimonio_neto": ultimo["patrimonio_neto_estimado"] - inicio["patrimonio_neto_estimado"],
        },
        "progresion_mensual": progresion,
        "gastos_por_categoria": gastos_trim,
        "ingresos_por_categoria": ingresos_trim,
        "suscripciones_recurrentes": suscripciones,
        "anomalias": anomalias,
    }

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"Análisis {meses[0]} - {meses[-1]}:")
    print(f"  ingresos:               ${total_ingresos:>15,}")
    print(f"  gastos:                 ${total_gastos:>15,}")
    print(f"  ahorro neto:            ${total_ahorro:>+15,} ({result['totales']['tasa_ahorro_pct']}%)")
    print(f"  delta patrimonio neto:  ${result['patrimonio']['delta_patrimonio_neto']:>+15,}")
    print(f"  suscripciones detectadas: {len(suscripciones)}")
    print(f"  anomalías detectadas:     {len(anomalias)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meses", required=True, help="Comma-separated: 2026-01,2026-02,2026-03")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    meses = [m.strip() for m in args.meses.split(",")]
    procesar(meses, args.output)


if __name__ == "__main__":
    main()
