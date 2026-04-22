"""Genera dashboard HTML editorial a partir del análisis trimestral."""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


MES_NOMBRES = {
    "01": "Enero",
    "02": "Febrero",
    "03": "Marzo",
    "04": "Abril",
    "05": "Mayo",
    "06": "Junio",
    "07": "Julio",
    "08": "Agosto",
    "09": "Septiembre",
    "10": "Octubre",
    "11": "Noviembre",
    "12": "Diciembre",
}


def fmt_money(v: float | int, plus: bool = False) -> str:
    sign = "+" if plus and v > 0 else ""
    return f"{sign}${abs(v):,.0f}" if v >= 0 else f"-${abs(v):,.0f}"


def pretty_mes(etiqueta: str) -> str:
    y, m = etiqueta.split("-")
    return f"{MES_NOMBRES[m]} {y}"


def bar_chart(items: list[tuple[str, int]], max_val: int, color: str = "#3b5bdb") -> str:
    if max_val == 0:
        return ""
    rows = []
    for label, val in items:
        pct = (val / max_val) * 100 if max_val else 0
        rows.append(
            f"""<div class="bar-row">
                 <div class="bar-label">{escape(label)}</div>
                 <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%; background:{color}"></div></div>
                 <div class="bar-value">{fmt_money(val)}</div>
               </div>"""
        )
    return "\n".join(rows)


def render(analisis: dict, output: Path) -> None:
    meses = analisis["periodo"]["meses"]
    titulo_periodo = f"{pretty_mes(meses[0])} – {pretty_mes(meses[-1])}"
    totales = analisis["totales"]
    patrim = analisis["patrimonio"]
    prog = analisis["progresion_mensual"]
    gastos_cat = analisis["gastos_por_categoria"]
    ingresos_cat = analisis["ingresos_por_categoria"]
    suscripciones = analisis["suscripciones_recurrentes"]
    anomalias = analisis["anomalias"]

    # Top 8 categorías de gasto (para barras)
    top_gastos = list(gastos_cat.items())[:8]
    max_gasto = max((v["total"] for _, v in top_gastos), default=1)

    # Progresión mensual: filas
    prog_rows = "\n".join(
        f"""<tr>
            <td>{pretty_mes(p["mes"])}</td>
            <td class="num pos">{fmt_money(p["ingresos"])}</td>
            <td class="num neg">{fmt_money(p["gastos"])}</td>
            <td class="num">{fmt_money(p["ahorro_neto"], plus=True)}</td>
            <td class="num">{fmt_money(p["compras_tc"])}</td>
            <td class="num">{fmt_money(p["intereses_tc"])}</td>
            <td class="num">{fmt_money(p["patrimonio_liquido"])}</td>
            <td class="num">{fmt_money(p["deuda_tc"])}</td>
            <td class="num strong">{fmt_money(p["patrimonio_neto"])}</td>
          </tr>"""
        for p in prog
    )

    # Gastos por categoría (tabla con subcategorías colapsables)
    cat_rows = []
    for cat, data in gastos_cat.items():
        subs_html = "".join(
            f'<div class="sub-row"><span>{escape(sub)}</span><span class="num">{fmt_money(val)}</span></div>'
            for sub, val in data["subcategorias"].items()
        )
        cat_rows.append(
            f"""<details class="cat-detail">
                 <summary>
                   <span class="cat-name">{escape(cat)}</span>
                   <span class="cat-total num">{fmt_money(data["total"])}</span>
                 </summary>
                 <div class="sub-list">{subs_html}</div>
               </details>"""
        )
    cat_html = "\n".join(cat_rows)

    # Ingresos
    ing_rows = []
    for cat, data in ingresos_cat.items():
        subs_html = "".join(
            f'<div class="sub-row"><span>{escape(sub)}</span><span class="num pos">{fmt_money(val)}</span></div>'
            for sub, val in data["subcategorias"].items()
        )
        ing_rows.append(
            f"""<details class="cat-detail">
                 <summary>
                   <span class="cat-name">{escape(cat)}</span>
                   <span class="cat-total num pos">{fmt_money(data["total"])}</span>
                 </summary>
                 <div class="sub-list">{subs_html}</div>
               </details>"""
        )
    ing_html = "\n".join(ing_rows)

    # Suscripciones
    susc_rows = "\n".join(
        f"""<tr>
             <td>{escape(s["merchant"][:40])}</td>
             <td>{escape(s["categoria"])}/{escape(s["subcategoria"])}</td>
             <td class="num">{fmt_money(s["monto_promedio"])}</td>
             <td class="num">{fmt_money(s["monto_min"])} – {fmt_money(s["monto_max"])}</td>
             <td>{"Estable" if s["estable"] else f"Variable (CV {s['coef_variacion']:.2f})"}</td>
           </tr>"""
        for s in suscripciones
    )

    # Anomalías
    anom_rows = "\n".join(
        f"""<tr>
             <td>{escape(a["fecha"])}</td>
             <td class="num neg">{fmt_money(abs(a["valor"]))}</td>
             <td>{escape(a["categoria"])}/{escape(a["subcategoria"])}</td>
             <td>{escape(a["descripcion"][:50])}</td>
             <td class="num">{a["z_score"]}σ</td>
           </tr>"""
        for a in anomalias
    )

    css = """
    :root {
      --bg: #faf8f3;
      --ink: #1a1a1a;
      --muted: #6b6b6b;
      --rule: #dcd7c8;
      --accent: #8b2a2a;
      --pos: #1d6e3a;
      --neg: #8b2a2a;
      --card: #fffdf7;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); }
    body {
      font-family: "Iowan Old Style", "Charter", "Georgia", serif;
      max-width: 1100px; margin: 0 auto; padding: 48px 32px;
      line-height: 1.55;
    }
    header { border-bottom: 3px double var(--rule); padding-bottom: 24px; margin-bottom: 40px; }
    .masthead { font-variant: small-caps; letter-spacing: 0.12em; color: var(--muted); font-size: 14px; }
    h1 { font-size: 48px; margin: 8px 0 8px; font-weight: 500; line-height: 1.1; letter-spacing: -0.02em; }
    .subtitle { font-style: italic; color: var(--muted); font-size: 18px; }
    h2 { font-size: 24px; margin: 48px 0 16px; font-weight: 500; border-bottom: 1px solid var(--rule); padding-bottom: 8px; letter-spacing: -0.01em; }
    h3 { font-size: 16px; margin: 20px 0 8px; font-variant: small-caps; letter-spacing: 0.08em; color: var(--muted); }
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
    .kpi { background: var(--card); padding: 20px; border: 1px solid var(--rule); }
    .kpi-label { font-size: 11px; font-variant: small-caps; letter-spacing: 0.1em; color: var(--muted); }
    .kpi-value { font-size: 28px; font-weight: 500; margin-top: 6px; font-feature-settings: "tnum"; }
    .kpi-delta { font-size: 12px; color: var(--muted); margin-top: 4px; }
    .pos { color: var(--pos); }
    .neg { color: var(--neg); }
    .strong { font-weight: 600; }
    .num { font-feature-settings: "tnum"; font-variant-numeric: tabular-nums; text-align: right; }
    table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }
    th, td { padding: 8px 10px; border-bottom: 1px solid var(--rule); }
    th { text-align: left; font-weight: 600; font-variant: small-caps; font-size: 12px; letter-spacing: 0.06em; color: var(--muted); }
    td.num { text-align: right; font-feature-settings: "tnum"; }
    .bar-row { display: grid; grid-template-columns: 200px 1fr 120px; gap: 16px; align-items: center; padding: 6px 0; }
    .bar-label { font-size: 14px; }
    .bar-track { height: 18px; background: #eee6d8; border-radius: 2px; overflow: hidden; }
    .bar-fill { height: 100%; }
    .bar-value { font-feature-settings: "tnum"; font-size: 14px; color: var(--muted); text-align: right; }
    .cat-detail { border-bottom: 1px solid var(--rule); padding: 10px 0; }
    .cat-detail summary { display: flex; justify-content: space-between; cursor: pointer; list-style: none; font-size: 16px; }
    .cat-detail summary::-webkit-details-marker { display: none; }
    .cat-name { font-weight: 500; }
    .cat-total { font-weight: 600; }
    .sub-list { padding: 8px 0 4px 16px; border-left: 2px solid var(--rule); margin-left: 8px; margin-top: 8px; }
    .sub-row { display: flex; justify-content: space-between; padding: 3px 0; font-size: 14px; color: var(--muted); }
    .twocol { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }
    footer { margin-top: 64px; padding-top: 24px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 12px; font-style: italic; }
    .lede { font-size: 18px; line-height: 1.7; margin-bottom: 32px; color: var(--ink); font-style: italic; }
    .lede strong { font-style: normal; }
    @media (max-width: 768px) {
      .kpi-grid { grid-template-columns: repeat(2, 1fr); }
      .twocol { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 100px 1fr 80px; }
    }
    """

    # Lede auto-generado
    ahorro_pct = totales["tasa_ahorro_pct"]
    if ahorro_pct >= 30:
        tono = "sobresaliente"
    elif ahorro_pct >= 20:
        tono = "sólido"
    elif ahorro_pct >= 10:
        tono = "moderado"
    else:
        tono = "estrecho"

    lede = (
        f"En el periodo {escape(titulo_periodo)}, se registraron "
        f"<strong>{fmt_money(totales['ingresos'])}</strong> en ingresos y "
        f"<strong>{fmt_money(totales['gastos'])}</strong> en gastos, "
        f"para un ahorro neto <strong>{fmt_money(totales['ahorro_neto'], plus=True)}</strong> "
        f"({totales['tasa_ahorro_pct']}%, un trimestre {tono}). "
        f"El patrimonio neto pasó de <strong>{fmt_money(patrim['patrimonio_neto_inicio'])}</strong> "
        f"a <strong>{fmt_money(patrim['patrimonio_neto_fin'])}</strong>, un delta de "
        f"<strong>{fmt_money(patrim['delta_patrimonio_neto'], plus=True)}</strong>. "
        f"Se detectaron {len(suscripciones)} suscripciones recurrentes y "
        f"{len(anomalias)} anomalías estadísticas en gasto individual."
    )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Informe trimestral — {escape(titulo_periodo)}</title>
<style>{css}</style>
</head>
<body>
<header>
  <div class="masthead">Quanto · Informe Financiero Trimestral</div>
  <h1>{escape(titulo_periodo)}</h1>
  <div class="subtitle">Análisis consolidado de ingresos, gastos, deuda de tarjetas y patrimonio</div>
</header>

<p class="lede">{lede}</p>

<h2>Resumen ejecutivo</h2>
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-label">Ingresos</div>
    <div class="kpi-value pos">{fmt_money(totales["ingresos"])}</div>
    <div class="kpi-delta">Promedio mensual {fmt_money(totales["ingresos"] // len(prog))}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Gastos</div>
    <div class="kpi-value neg">{fmt_money(totales["gastos"])}</div>
    <div class="kpi-delta">Promedio mensual {fmt_money(totales["gastos"] // len(prog))}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Ahorro neto</div>
    <div class="kpi-value pos">{fmt_money(totales["ahorro_neto"], plus=True)}</div>
    <div class="kpi-delta">Tasa {totales["tasa_ahorro_pct"]}%</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Δ Patrimonio neto</div>
    <div class="kpi-value">{fmt_money(patrim["delta_patrimonio_neto"], plus=True)}</div>
    <div class="kpi-delta">Fin: {fmt_money(patrim["patrimonio_neto_fin"])}</div>
  </div>
</div>

<h2>Progresión mensual</h2>
<table>
  <thead>
    <tr>
      <th>Mes</th>
      <th class="num">Ingresos</th>
      <th class="num">Gastos</th>
      <th class="num">Ahorro</th>
      <th class="num">Compras TC</th>
      <th class="num">Intereses TC</th>
      <th class="num">Liquidez</th>
      <th class="num">Deuda TC</th>
      <th class="num">P. neto</th>
    </tr>
  </thead>
  <tbody>{prog_rows}</tbody>
</table>

<h2>Top categorías de gasto</h2>
{bar_chart([(cat, data["total"]) for cat, data in top_gastos], max_gasto)}

<div class="twocol" style="margin-top:32px;">
  <div>
    <h3>Gastos (detalle completo)</h3>
    {cat_html}
  </div>
  <div>
    <h3>Ingresos</h3>
    {ing_html}
  </div>
</div>

<h2>Suscripciones recurrentes detectadas</h2>
<p style="color:var(--muted); font-style:italic;">Cobros con presencia en los {len(meses)} meses del periodo. El indicador "Estable" marca cobros con coeficiente de variación ≤ 0.2.</p>
<table>
  <thead>
    <tr>
      <th>Merchant</th>
      <th>Categoría</th>
      <th class="num">Promedio</th>
      <th class="num">Rango</th>
      <th>Estabilidad</th>
    </tr>
  </thead>
  <tbody>{susc_rows}</tbody>
</table>

<h2>Anomalías estadísticas de gasto</h2>
<p style="color:var(--muted); font-style:italic;">Transacciones individuales con z-score {"> 3" + "σ"} respecto a la media de su categoría (y valor &gt; $50k).</p>
<table>
  <thead>
    <tr>
      <th>Fecha</th>
      <th class="num">Monto</th>
      <th>Categoría</th>
      <th>Descripción</th>
      <th class="num">Z-score</th>
    </tr>
  </thead>
  <tbody>{anom_rows if anom_rows else '<tr><td colspan="5" style="color:var(--muted); font-style:italic;">Sin anomalías significativas.</td></tr>'}</tbody>
</table>

<h2>Tarjetas de crédito</h2>
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-label">Compras del trimestre</div>
    <div class="kpi-value">{fmt_money(totales["compras_tc_totales"])}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Intereses pagados</div>
    <div class="kpi-value neg">{fmt_money(totales["intereses_tc_pagados"])}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Comisiones y seguros</div>
    <div class="kpi-value neg">{fmt_money(totales["comisiones_y_seguros_tc"])}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Deuda TC al cierre</div>
    <div class="kpi-value">{fmt_money(patrim["deuda_tc_fin"])}</div>
    <div class="kpi-delta">Δ trimestre {fmt_money(patrim["delta_deuda_tc"], plus=True)}</div>
  </div>
</div>

<h2>Patrimonio</h2>
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-label">Liquidez inicio</div>
    <div class="kpi-value">{fmt_money(patrim["liquidez_inicio"])}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Liquidez cierre</div>
    <div class="kpi-value">{fmt_money(patrim["liquidez_fin"])}</div>
    <div class="kpi-delta pos">{fmt_money(patrim["delta_liquidez"], plus=True)}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Flujo neto de inversión</div>
    <div class="kpi-value">{fmt_money(totales["flujo_inversion"], plus=True)}</div>
    <div class="kpi-delta">Compra/retorno de títulos</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Patrimonio neto cierre</div>
    <div class="kpi-value strong">{fmt_money(patrim["patrimonio_neto_fin"])}</div>
  </div>
</div>

<footer>
  Generado por Quanto a partir de los extractos de Davivienda (cuenta + TC), Davibank (TC) y Nequi.
  Los datos provienen exclusivamente de los PDFs oficiales del usuario. Patrimonio neto = liquidez − deuda TC;
  no incluye inversiones en títulos, inmuebles u otros activos fuera de los extractos.
</footer>

</body>
</html>
"""
    output.write_text(html)
    print(f"Dashboard escrito en: {output}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meses", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--analisis", default="analisis/trimestre/analisis-trimestral-2026-q1.json")
    args = ap.parse_args()
    analisis = load(Path(args.analisis))
    render(analisis, Path(args.output))


if __name__ == "__main__":
    main()
