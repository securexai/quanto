"""Categoriza movimientos de los 4 productos aplicando categorias.json.
Emite analisis/{mes}/movimientos-categorizados.json y gastos-por-categoria.json."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CATEGORIAS_PATH = Path(__file__).resolve().parent.parent / "categorias.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def categorizar(descripcion: str, reglas: list[dict]) -> tuple[str, str]:
    up = descripcion.upper()
    for r in reglas:
        for kw in r["keywords"]:
            if kw.upper() in up:
                return r["categoria"], r["subcategoria"]
    return "sin_clasificar", "sin_clasificar"


def to_signed_int(value) -> int:
    """Return value as integer COP (cents truncated — amounts are always whole pesos in practice)."""
    return int(round(value))


def procesar_mes(mes: str) -> None:
    reglas = load(CATEGORIAS_PATH)["reglas"]
    dir_mes = Path(f"analisis/{mes}")
    ahorros = load(dir_mes / "davivienda-ahorros.json")
    tc_davi = load(dir_mes / "davivienda-tc.json")
    tc_davibank = load(dir_mes / "davibank-tc.json")
    nequi = load(dir_mes / "nequi.json")

    movimientos: list[dict] = []

    # Davivienda ahorros (cuenta + bolsillo)
    for m in ahorros["movimientos"]:
        cat, sub = categorizar(m["descripcion"], reglas)
        if m.get("transferencia_interna"):
            cat, sub = "transferencia_interna", m.get("match_tipo", "otro")
        movimientos.append({
            "producto": "davivienda-ahorros",
            "seccion": "cuenta",
            "fecha": m["fecha"],
            "descripcion": m["descripcion"],
            "valor": to_signed_int(m["valor"]),
            "tipo": m["tipo"],
            "categoria": cat,
            "subcategoria": sub,
            "transferencia_interna": m.get("transferencia_interna", False),
        })
    for m in ahorros.get("bolsillo", []):
        cat, sub = categorizar(m["descripcion"], reglas)
        # Bolsillo items are internal between cuenta ↔ bolsillo
        cat, sub = "transferencia_interna", "bolsillo"
        movimientos.append({
            "producto": "davivienda-ahorros",
            "seccion": "bolsillo",
            "fecha": m["fecha"],
            "descripcion": m["descripcion"],
            "valor": to_signed_int(m["valor"]),
            "tipo": m["tipo"],
            "categoria": cat,
            "subcategoria": sub,
            "transferencia_interna": True,
        })

    # Davivienda TC — compras del periodo (negativos = gasto). Intereses y otros cargos también.
    for c in tc_davi["compras_periodo"]:
        desc = c["descripcion"]
        cat, sub = categorizar(desc, reglas)
        movimientos.append({
            "producto": "davivienda-tc",
            "seccion": "compras_periodo",
            "fecha": c["fecha"],
            "descripcion": desc,
            "valor": -to_signed_int(c["valor_transaccion"]),  # gasto es negativo
            "tipo": "debito",
            "categoria": cat,
            "subcategoria": sub,
            "cuota_actual": c["cuota_actual"],
            "cuota_total": c["cuota_total"],
        })
    for o in tc_davi["otros_cargos"]:
        cat, sub = categorizar(o["descripcion"], reglas)
        movimientos.append({
            "producto": "davivienda-tc",
            "seccion": "otros_cargos",
            "fecha": o["fecha"],
            "descripcion": o["descripcion"],
            "valor": -to_signed_int(o["valor"]),
            "tipo": "debito",
            "categoria": cat,
            "subcategoria": sub,
        })

    # Davibank TC — compras periodo + anteriores con cuota==1 no canceladas
    for c in tc_davibank["compras_periodo"]:
        if c.get("cancelado"):
            continue
        desc = c["descripcion"]
        cat, sub = categorizar(desc, reglas)
        movimientos.append({
            "producto": "davibank-tc",
            "seccion": "compras_periodo",
            "fecha": c["fecha"],
            "descripcion": desc,
            "valor": -to_signed_int(c["valor_transaccion"]),
            "tipo": "debito",
            "categoria": cat,
            "subcategoria": sub,
            "cuota_actual": c["cuota_actual"],
            "cuota_total": c["cuota_total"],
            "tarjetahabiente": c.get("tarjetahabiente"),
        })
    for c in tc_davibank["compras_meses_anteriores"]:
        if c.get("cancelado") or c["cuota_actual"] != 1:
            continue
        desc = c["descripcion"]
        cat, sub = categorizar(desc, reglas)
        movimientos.append({
            "producto": "davibank-tc",
            "seccion": "compras_anteriores_nuevas",
            "fecha": c["fecha"],
            "descripcion": desc,
            "valor": -to_signed_int(c["valor_transaccion"]),
            "tipo": "debito",
            "categoria": cat,
            "subcategoria": sub,
            "cuota_actual": c["cuota_actual"],
            "cuota_total": c["cuota_total"],
            "tarjetahabiente": c.get("tarjetahabiente"),
        })
    for o in tc_davibank["otros_cargos"]:
        cat, sub = categorizar(o["descripcion"], reglas)
        movimientos.append({
            "producto": "davibank-tc",
            "seccion": "otros_cargos",
            "fecha": o["fecha"],
            "descripcion": o["descripcion"],
            "valor": -to_signed_int(o["valor"]),
            "tipo": "debito" if o["valor"] > 0 else "credito",
            "categoria": cat,
            "subcategoria": sub,
        })

    # Nequi
    for m in nequi["movimientos"]:
        desc = m["descripcion"]
        cat, sub = categorizar(desc, reglas)
        if m.get("transferencia_interna"):
            cat, sub = "transferencia_interna", m.get("match_tipo", "fondeo_nequi")
        movimientos.append({
            "producto": "nequi",
            "seccion": "movimientos",
            "fecha": m["fecha"],
            "descripcion": desc,
            "valor": to_signed_int(m["valor"]),
            "tipo": m["tipo"],
            "categoria": cat,
            "subcategoria": sub,
            "transferencia_interna": m.get("transferencia_interna", False),
        })

    # Ordenar por fecha
    movimientos.sort(key=lambda x: (x["fecha"], x["producto"]))

    # Categorías excluidas del P&L (no son gasto/ingreso operacional):
    # - transferencia_interna: movimientos entre productos propios
    # - inversion: reasignación de capital entre liquidez e inversiones
    EXCLUIR_PYL = {"transferencia_interna", "inversion"}

    gastos_cat: dict[tuple, int] = defaultdict(int)
    ingresos_cat: dict[tuple, int] = defaultdict(int)
    inversion_cat: dict[tuple, int] = defaultdict(int)
    for m in movimientos:
        key = (m["categoria"], m["subcategoria"])
        if m["categoria"] == "transferencia_interna":
            continue
        if m["categoria"] == "inversion":
            inversion_cat[key] += m["valor"]
            continue
        if m["valor"] < 0:
            gastos_cat[key] += -m["valor"]
        elif m["valor"] > 0:
            ingresos_cat[key] += m["valor"]

    def nested(d: dict[tuple, int]) -> dict:
        out: dict[str, dict[str, int]] = defaultdict(dict)
        for (cat, sub), val in d.items():
            out[cat][sub] = val
        return {k: {"total": sum(v.values()), "subcategorias": v} for k, v in out.items()}

    gastos_resumen = nested(gastos_cat)
    ingresos_resumen = nested(ingresos_cat)
    # Para inversion reportamos el flujo neto (positivo = retorno, negativo = compra)
    inversion_net = sum(inversion_cat.values())
    inversion_detalle = dict(inversion_cat)

    total_gastos = sum(v["total"] for v in gastos_resumen.values())
    total_ingresos = sum(v["total"] for v in ingresos_resumen.values())

    gastos_sorted = dict(sorted(gastos_resumen.items(), key=lambda x: -x[1]["total"]))
    ingresos_sorted = dict(sorted(ingresos_resumen.items(), key=lambda x: -x[1]["total"]))

    out_mov = dir_mes / "movimientos-categorizados.json"
    out_mov.write_text(json.dumps({
        "mes": mes,
        "total_movimientos": len(movimientos),
        "movimientos": movimientos,
    }, indent=2, ensure_ascii=False))

    out_gastos = dir_mes / "gastos-por-categoria.json"
    out_gastos.write_text(json.dumps({
        "mes": mes,
        "totales": {"gastos": total_gastos, "ingresos": total_ingresos,
                    "ahorro_neto": total_ingresos - total_gastos,
                    "flujo_neto_inversion": inversion_net},
        "gastos": gastos_sorted,
        "ingresos": ingresos_sorted,
        "inversion": {f"{k[0]}/{k[1]}": v for k, v in inversion_detalle.items()},
    }, indent=2, ensure_ascii=False))

    print(f"[{mes}] categorizar:")
    print(f"  movimientos: {len(movimientos)}")
    print(f"  total gastos:   ${total_gastos:>14,}")
    print(f"  total ingresos: ${total_ingresos:>14,}")
    print(f"  ahorro neto:    ${total_ingresos - total_gastos:>+14,}")
    sin_cat = [m for m in movimientos if m["categoria"] == "sin_clasificar"]
    if sin_cat:
        print(f"  sin_clasificar: {len(sin_cat)} items")
        for m in sin_cat[:10]:
            print(f"    {m['fecha']} {m['producto']:<20} ${m['valor']:>+12,}  {m['descripcion'][:50]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", required=True)
    args = ap.parse_args()
    procesar_mes(args.mes)


if __name__ == "__main__":
    main()
