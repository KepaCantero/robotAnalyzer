"""Métricas cuantitativas de riesgo sobre series de cierres — stdlib puro.

El factor volatilidad_drawdown del bloque R/R (regla 59) deja de depender solo
del juicio del agente: se alimenta con métricas duras derivadas de cierres
VERIFICADO. Todo lo que sale de aquí viaja con etiqueta CALCULADO (regla 75) y
con id de métrica bruta, para que el control de doble conteo (regla 63) lo
detecte si un agente también la declara.

Las escalas métrica→factor 0-100 son CONVENCIONES de calibración declaradas
como constantes (regla 41: sin falsa precisión), no verdades de mercado.
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional

from analizador.domain.models import DataLabel, Dato
from analizador.scoring.engine import Factor

PERIODOS_ANIO = 252        # sesiones de bolsa por año
MIN_CIERRES = 30           # menos de ~6 semanas: ni volatilidad ni ratios
TASA_LIBRE_RIESGO = 0.0    # supuesto declarado; no se inventa un tipo real

# Regla 41 — convención de calibración: volatilidad anualizada de
# ESCALA_VOL_TOPE y drawdown de -ESCALA_DD_TOPE puntúan 0; en 0 puntúan 100.
ESCALA_VOL_TOPE = 0.40     # 40% anual ≈ temático concentrado o apalancado
ESCALA_DD_TOPE = 0.60      # -60% ≈ drawdown histórico de sectoriales duros


def retornos_diarios(cierres: List[float]) -> List[float]:
    return [b / a - 1.0 for a, b in zip(cierres, cierres[1:]) if a > 0]


def volatilidad_anualizada(retornos: List[float]) -> Optional[float]:
    if len(retornos) < 2:
        return None
    return statistics.stdev(retornos) * (PERIODOS_ANIO ** 0.5)


def max_drawdown(cierres: List[float]) -> Optional[float]:
    """Peor caída desde el máximo anterior, en fracción (≤ 0)."""
    if len(cierres) < 2:
        return None
    pico, dd = cierres[0], 0.0
    for c in cierres:
        if c > pico:
            pico = c
        if pico > 0:
            dd = min(dd, c / pico - 1.0)
    return dd


def sharpe(retornos: List[float], rf_anual: float = TASA_LIBRE_RIESGO) -> Optional[float]:
    """Sharpe anualizado. Sin dispersión el ratio es indefinido → None
    (regla 41: no se disfraza de 0 lo que no se puede calcular)."""
    if len(retornos) < 2:
        return None
    desv = statistics.stdev(retornos)
    if desv == 0:
        return None
    exceso = statistics.fmean(retornos) - rf_anual / PERIODOS_ANIO
    return exceso / desv * (PERIODOS_ANIO ** 0.5)


def sortino(retornos: List[float], rf_anual: float = TASA_LIBRE_RIESGO) -> Optional[float]:
    """Sortino anualizado (downside deviation sobre la muestra completa)."""
    if len(retornos) < 2:
        return None
    rf_diario = rf_anual / PERIODOS_ANIO
    bajos = [(r - rf_diario) if r < rf_diario else 0.0 for r in retornos]
    if not any(b < 0 for b in bajos):
        return None
    desv_bajo = (sum(b * b for b in bajos) / len(bajos)) ** 0.5
    return (statistics.fmean(retornos) - rf_diario) / desv_bajo * (PERIODOS_ANIO ** 0.5)


def _lineal(valor: float, mejor: float, peor: float) -> float:
    """Proyección lineal de valor desde [peor, mejor] a [0, 100], acotada."""
    t = (valor - peor) / (mejor - peor) if mejor != peor else 0.5
    return max(0.0, min(100.0, 100.0 * t))


def metricas_desde_dato(hist: Dato) -> Dict[str, Dato]:
    """{id → Dato CALCULADO} desde un Dato.valor de pares [fecha ISO, cierre].

    La frescura es la de la serie (regla 72): cada métrica lleva la fecha del
    último cierre. Serie corta o NO_DISPONIBLE → dict vacío, sin falsa precisión.
    """
    if hist is None or hist.etiqueta == DataLabel.NO_DISPONIBLE or not hist.valor:
        return {}
    cierres = [float(par[1]) for par in hist.valor
               if isinstance(par, (list, tuple)) and len(par) == 2
               and isinstance(par[1], (int, float))]
    if len(cierres) < MIN_CIERRES:
        return {}
    ret = retornos_diarios(cierres)
    out: Dict[str, Dato] = {}

    def _dato(id_m: str, valor: Optional[float], nota: str) -> None:
        if valor is not None:
            out[id_m] = Dato(valor=round(valor, 4), etiqueta=DataLabel.CALCULADO,
                             fuente="calculada", fecha=hist.fecha, nota=nota)

    _dato("volatilidad_anual", volatilidad_anualizada(ret),
          "volatilidad anualizada sobre %d cierres" % len(cierres))
    _dato("max_drawdown", max_drawdown(cierres),
          "max drawdown sobre %d cierres" % len(cierres))
    _dato("sharpe", sharpe(ret),
          "sharpe (rentabilidad por unidad de volatilidad; rf 0%% declarado)")
    _dato("sortino", sortino(ret),
          "sortino (rentabilidad por riesgo a la baja; rf 0%% declarado)")
    return out


def factor_desde_metricas(metricas: Dict[str, Dato]) -> Optional[Factor]:
    """Factor volatilidad_drawdown (regla 59) desde métricas duras: media de
    las escalas convencionales de volatilidad y drawdown. Declara sus ids
    brutos (regla 63) para el control de doble conteo del motor."""
    vol = metricas.get("volatilidad_anual")
    dd = metricas.get("max_drawdown")
    partes, ids = [], []
    if vol is not None and vol.valor is not None:
        partes.append(_lineal(float(vol.valor), mejor=0.0, peor=ESCALA_VOL_TOPE))
        ids.append("volatilidad_anual")
    if dd is not None and dd.valor is not None:
        partes.append(_lineal(float(dd.valor), mejor=0.0, peor=-ESCALA_DD_TOPE))
        ids.append("max_drawdown")
    if not partes:
        return None
    return Factor(
        nombre="volatilidad_drawdown",
        valor=round(sum(partes) / len(partes), 1),
        metricas=ids,
        justificacion=("calculado desde serie de cierres (escala convencional: "
                       "vol %d%%=0, dd -%d%%=0; reglas 41/63)" % (
                           round(ESCALA_VOL_TOPE * 100), round(ESCALA_DD_TOPE * 100))))
