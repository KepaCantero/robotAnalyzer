"""Construcción y control del TOP 5 — reglas 7-8, 79-80, 116, 147.

El TOP 5 es una obligación dura del sistema: si existen ≥5 candidatos válidos,
el resultado DEBE contener exactamente 5. Este módulo lo hace exigible en código,
no solo en el prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from analizador.domain.models import AnalisisProducto


@dataclass
class ReporteControl:
    """Regla 80: control final antes de responder. Si hay un 'no', se repite."""
    hay_exactamente_5: bool = False
    candidatos_validos: int = 0
    universo_explorado: int = 0
    categorias_cubiertas: List[str] = field(default_factory=list)
    faltan_categorias: bool = False
    datos_actuales: bool = True
    comparables_correctos: bool = True
    ranking_justificable: bool = True
    robustez: str = ""                  # ROBUSTO | SENSIBLE (regla 116)
    notas: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        base = (self.hay_exactamente_5 or self.candidatos_validos < 5) and self.universo_explorado >= 10
        return base and not self.faltan_categorias and self.datos_actuales

    def resumen(self) -> str:
        líneas = [
            "Control final del TOP 5 (regla 80):",
            "- ¿Hay exactamente 5? %s" % ("SÍ" if self.hay_exactamente_5 else "NO"),
            "- Universo explorado: %d (mínimo 10, regla 8)" % self.universo_explorado,
            "- Candidatos válidos: %d" % self.candidatos_validos,
            "- Categorías cubiertas: %s" % (", ".join(self.categorias_cubiertas) or "—"),
            "- Robustez (regla 116): %s" % (self.robustez or "sin evaluar"),
        ]
        líneas += ["- %s" % n for n in self.notas]
        if self.candidatos_validos < 5:
            líneas.append(
                "- AVISO (regla 7): no existen cinco candidatos suficientemente "
                "válidos; se declara expresamente y NO se rellena artificialmente.")
        return "\n".join(líneas)


def _clave_orden(a: AnalisisProducto) -> Tuple:
    # Regla 83: con perfil ordena el personalizado; sin perfil, R/R primero y
    # potencial como secundario (regla 12/82).
    if a.scores.personalizado is not None:
        return (a.scores.personalizado, a.scores.rentabilidad_riesgo or 0,
                a.scores.potencial or 0, a.scores.confianza)
    return (a.scores.rentabilidad_riesgo or 0, a.scores.potencial or 0,
            a.scores.confianza, 0)


def construir_top5(candidatos: List[AnalisisProducto],
                   universo_explorado: int,
                   categorias_relevantes: Optional[List[str]] = None
                   ) -> Tuple[List[AnalisisProducto], List[AnalisisProducto], ReporteControl]:
    """Reglas 79 (10 pasos) y 147.

    Devuelve (top5, resto_ordenado, reporte). Si hay menos de 5 válidos devuelve
    los que haya y el reporte lo declara — nunca rellena con mala calidad.
    """
    validos = [c for c in candidatos
               if (c.scores.rentabilidad_riesgo or 0) > 0
               and c.producto.nombre]
    ordenados = sorted(validos, key=_clave_orden, reverse=True)
    top5 = ordenados[:5]
    resto = ordenados[5:]

    categorias = sorted({c.producto.categoria for c in top5})
    reporte = ReporteControl(
        hay_exactamente_5=len(top5) == 5,
        candidatos_validos=len(validos),
        universo_explorado=universo_explorado,
        categorias_cubiertas=categorias,
    )
    if categorias_relevantes:
        faltan = [c for c in categorias_relevantes if c not in categorias]
        # Solo cuentan las relevantes con candidatos válidos disponibles
        disponibles = {c.producto.categoria for c in validos}
        faltan = [c for c in faltan if c in disponibles]
        reporte.faltan_categorias = bool(faltan)
        if faltan:
            reporte.notas.append(
                "Categorías relevantes sin representación en el TOP 5: %s "
                "(regla 80 paso 4)" % ", ".join(faltan))
    if universo_explorado < 10:
        reporte.notas.append(
            "Universo explorado (%d) < 10: riesgo de omisión (regla 8).")

    reporte.robustez = _robustez(top5)
    if reporte.robustez == "SENSIBLE" and len(top5) >= 2:
        reporte.notas.append(
            "Ranking SENSIBLE: diferencias pequeñas; explicarlo como exige la "
            "regla 152 y analizar sensibilidad (regla 153).")
    return top5, resto, reporte


def _robustez(top5: List[AnalisisProducto], perturbacion: float = 3.0) -> str:
    """Regla 116: ¿pequeños cambios alteran el ranking? Perturba ±3 puntos."""
    if len(top5) < 2:
        return "ROBUSTO"
    base = list(range(len(top5)))

    def orden_con_delta(delta: float):
        return sorted(
            range(len(top5)),
            key=lambda i: _clave_orden(top5[i])[0] + delta * (1 if i % 2 == 0 else -1),
            reverse=True)

    estable = orden_con_delta(perturbacion) == base and orden_con_delta(-perturbacion) == base
    return "ROBUSTO" if estable else "SENSIBLE"


def diferencia_rankings(anterior: List[str], actual: List[str]) -> List[str]:
    """Regla 105: seguimiento — qué sube, baja, entra y sale."""
    notas = []
    set_ant, set_act = set(anterior), set(actual)
    for nombre in [n for n in actual if n not in set_ant]:
        notas.append("NUEVO: %s entra en el TOP 5 (regla 104: el ranking no protege al anterior)" % nombre)
    for nombre in [n for n in anterior if n not in set_act]:
        notas.append("SALE: %s abandona el TOP 5" % nombre)
    for nombre in actual:
        if nombre in set_ant:
            mov = anterior.index(nombre) - actual.index(nombre)
            if mov > 0:
                notas.append("SUBE: %s (%d posición/es)" % (nombre, mov))
            elif mov < 0:
                notas.append("BAJA: %s (%d posición/es)" % (nombre, -mov))
    if not notas and anterior and actual:
        notas.append("Sin cambios en el TOP 5 respecto al análisis anterior (regla 105).")
    return notas
