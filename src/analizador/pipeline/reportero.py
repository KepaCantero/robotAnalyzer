"""Render determinista del informe final — regla 155 (formato estándar).

El informe se genera desde los datos estructurados (no lo escribe el LLM), para
que lo que se publica sea exactamente lo que calculó el motor.
"""
from __future__ import annotations

from typing import Dict, List

from analizador.domain.models import AnalisisCompleto, AnalisisProducto, etiqueta_score


def _metricas_riesgo_linea(m: Dict[str, Dict]) -> str:
    partes = []
    if m.get("volatilidad_anual", {}).get("valor") is not None:
        partes.append("volatilidad %.1f%% anual" % (m["volatilidad_anual"]["valor"] * 100))
    if m.get("max_drawdown", {}).get("valor") is not None:
        partes.append("máx. drawdown %.1f%%" % (m["max_drawdown"]["valor"] * 100))
    if m.get("sharpe", {}).get("valor") is not None:
        partes.append("Sharpe %+.2f" % m["sharpe"]["valor"])
    if m.get("sortino", {}).get("valor") is not None:
        partes.append("Sortino %+.2f" % m["sortino"]["valor"])
    return " · ".join(partes)


def _fila_top5(i: int, a: AnalisisProducto) -> str:
    s = a.scores
    global_ = s.personalizado if s.personalizado is not None else s.rentabilidad_riesgo
    entrada = ("%.2f" % a.niveles.precio_actual if a.niveles.precio_actual
               else a.buyability)
    return ("| %d | %s | %s | %s | %s | %s | %s | %s |" % (
        i, a.producto.nombre, a.producto.categoria,
        s.potencial if s.potencial is not None else "—",
        s.rentabilidad_riesgo if s.rentabilidad_riesgo is not None else "—",
        global_, s.confianza, entrada))


def render(analisis: AnalisisCompleto, dict_final: Dict) -> str:
    d: List[str] = []
    d.append("# Análisis: %s" % analisis.tema)
    d.append("")
    d.append("**Fecha de análisis: %s** (regla 122: fecha de corte obligatoria)" % analisis.fecha)
    d.append("")

    # 1. CONCLUSIÓN (regla 123)
    d.append("## 1. Conclusión")
    d.append("")
    d.append(analisis.conclusion)
    d.append("")

    # 2. TESIS
    d.append("## 2. Tesis")
    d.append("")
    if analisis.top5:
        t = analisis.top5[0].tesis
        d.append("**Positiva:** %s" % (t.positiva or "no disponible"))
        d.append("")
        d.append("**Negativa:** %s" % (t.negativa or "no disponible"))
    d.append("")

    # 3. TOP 5 (reglas 124, 148)
    d.append("## 3. TOP 5 %s" % ("(orden por score personalizado, regla 83)"
                                if analisis.top5 and analisis.top5[0].scores.personalizado is not None
                                else "(orden por R/R, regla 82)"))
    d.append("")
    d.append("| # | Producto | Tipo | Potencial | R/R | Global | Confianza | Entrada |")
    d.append("|---|----------|------|-----------|-----|--------|-----------|---------|")
    for i, a in enumerate(analisis.top5, 1):
        d.append(_fila_top5(i, a))
    d.append("")
    if analisis.advertencia_sin_perfil:
        d.append("> %s" % analisis.advertencia_sin_perfil)
        d.append("")

    # 4. ANÁLISIS DE LOS CINCO (regla 125)
    d.append("## 4. Análisis de los cinco")
    for i, a in enumerate(analisis.top5, 1):
        d.append("")
        d.append("### 4.%d %s" % (i, a.producto.nombre))
        p = a.producto
        d.append("")
        d.append("- **Qué es:** %s" % (a.explicacion_sencilla or "pendiente"))
        d.append("- **Naturaleza:** %s · réplica %s · %s · ISIN: %s" % (
            p.naturaleza, p.replica, "UCITS" if p.ucits else "no UCITS",
            p.isin or "no verificado (regla 101)"))
        d.append("- **Scores:** potencial %s (%s) · R/R %s · vehículo %s · "
                 "confianza %s" % (
                     a.scores.potencial,
                     etiqueta_score(a.scores.potencial) if a.scores.potencial is not None else "—",
                     a.scores.rentabilidad_riesgo, a.scores.vehiculo, a.scores.confianza))
        if a.scores.personalizado is not None:
            d.append("- **Score personalizado:** %s (regla 61)" % a.scores.personalizado)
        if a.metricas_riesgo:
            d.append("- **Métricas de riesgo (CALCULADO, regla 75):** %s"
                     % _metricas_riesgo_linea(a.metricas_riesgo))
        if a.tesis.escenarios:
            ev = a.tesis.valor_esperado()
            esc = ", ".join("%s %s" % (e.nombre,
                                       ("%+.0f%%" % (e.retorno_estimado * 100))
                                       if e.retorno_estimado is not None else "?")
                            for e in a.tesis.escenarios)
            d.append("- **Escenarios (regla 41):** %s%s" % (
                esc, " · EV %+.0f%% (regla 42, bajo supuestos)" % (ev * 100)
                if ev is not None else ""))
        ms = a.niveles.margen_seguridad()
        if ms is not None:
            d.append("- **Margen de seguridad (regla 34):** %+.1f%% (%s)" % (
                ms * 100, a.niveles.etiqueta_fair_value))
        d.append("- **Buyability (regla 86):** %s" % a.buyability)
        d.append("- **Costes (regla 23):** %s" % (a.coste_total_nota or "no disponible"))
        d.append("- **Accesibilidad (regla 71):** %s" % a.accesibilidad)
        if a.fiscalidad_nota:
            d.append("- **Fiscalidad ES (regla 29):** %s" % a.fiscalidad_nota)
        if a.riesgos:
            d.append("- **Riesgos:** %s" % "; ".join(a.riesgos[:5]))
        if a.red_team:
            d.append("- **Red team (regla 118):** %s" % a.red_team[0])
        if a.tesis.invalidadores:
            d.append("- **Qué invalidaría la tesis:** %s" % "; ".join(a.tesis.invalidadores[:3]))

    # 5. MEJORES POR CATEGORÍA (reglas 66, 148)
    por_cat: Dict[str, AnalisisProducto] = {}
    for a in analisis.top5:
        por_cat.setdefault(a.producto.categoria, a)
    if len(por_cat) > 1:
        d.append("")
        d.append("## 5. Mejores por categoría (regla 148: nunca equivalentes)")
        for cat, a in por_cat.items():
            d.append("- **%s:** %s" % (cat, a.producto.nombre))

    # 6. DESCARTES (reglas 91, 126)
    if analisis.descartados:
        d.append("")
        d.append("## 6. Principales descartes (regla 91)")
        d.append("")
        d.append("| Producto | Motivo de exclusión |")
        d.append("|----------|---------------------|")
        for x in analisis.descartados:
            d.append("| %s | %s |" % (x.producto, x.motivo))

    # 7. RIESGOS
    d.append("")
    d.append("## 7. Riesgos de la tesis")
    riesgos = [r for a in analisis.top5 for r in a.riesgos][:8] or [
        "sin análisis de riesgos (modo determinista)"]
    for r in riesgos:
        d.append("- %s" % r)

    # 8. VALORACIÓN Y ENTRADA (regla 86)
    d.append("")
    d.append("## 8. Valoración y entrada")
    d.append("Robustez del ranking (regla 116): **%s**." % (analisis.robustez or "sin evaluar"))
    if analisis.robustez == "SENSIBLE":
        d.append("La diferencia entre posiciones próximas es pequeña y el ranking es "
                 "sensible a determinados supuestos (regla 152).")

    # 9. RECOMENDACIÓN (regla 128)
    d.append("")
    d.append("## 9. Recomendación")
    d.append("")
    d.append(analisis.recomendacion)

    # 10. CONFIANZA (regla 129) + ganadores (regla 127)
    d.append("")
    d.append("## 10. Confianza y ganadores")
    d.append("")
    d.append("- Nivel de confianza del análisis: **%s** (regla 129)" % analisis.confianza_analisis)
    for k, v in analisis.ganadores.items():
        d.append("- %s: **%s**" % (k, v))

    # Extras: control del TOP 5 + seguimiento + avisos
    if dict_final.get("_control"):
        d.append("")
        d.append("---")
        d.append("")
        d.append("```")
        d.append(dict_final["_control"])
        d.append("```")
    if dict_final.get("seguimiento"):
        d.append("")
        d.append("### Seguimiento (regla 105)")
        for s in dict_final["seguimiento"][:8]:
            d.append("- %s" % s)
    if dict_final.get("avisos"):
        d.append("")
        d.append("### Avisos del sistema")
        for s in dict_final["avisos"][:8]:
            d.append("- %s" % s)

    return "\n".join(d)
