"""Motor de scoring determinista — reglas 5-6, 58-64, 76-78.

El score lo calcula código (no el LLM) para que sea reproducible y auditable.
Los agentes LLM aportan los FACTORES (0-100, con métricas de origen); este motor
aplica pesos, control de doble conteo, normalización por categoría, penalizaciones
y confidence por calidad/frescura de datos.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from analizador.domain.models import (
    DataLabel, Dato, Producto, Scores, etiqueta_score,
)

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
FICHERO_PESOS = os.path.join(RAIZ, ".semantic-graph", "curated", "scoring-weights.json")
FICHERO_TTL = os.path.join(RAIZ, ".semantic-graph", "curated", "metabolism-policy.json")

_ETIQUETAS_ORDEN = [DataLabel.INFERIDO, DataLabel.ESTIMADO,
                    DataLabel.CALCULADO, DataLabel.VERIFICADO]


def cargar_pesos(ruta: str = FICHERO_PESOS) -> Dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def cargar_politica_ttl(ruta: str = FICHERO_TTL) -> Dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _pesos_para(base: Dict, por_naturaleza: Dict, naturaleza: str) -> Dict[str, float]:
    """Regla 62: pesos adaptativos por tipo de producto; si la naturaleza no
    redefine nada, caen los pesos base. Las claves $* son comentarios, no pesos."""
    w = {k: v for k, v in base.items() if not k.startswith("$")}
    for k, v in por_naturaleza.get(naturaleza, {}).items():
        if not k.startswith("$"):
            w[k] = v
    return w


@dataclass
class Factor:
    """Input del motor: puntuación 0-100 de un factor + métricas que lo alimentan.

    `metricas` permite el control de doble conteo (regla 63): si dos factores
    declaran la misma métrica subyacente, el motor lo detecta y lo penaliza en
    el factor de menor peso en vez de sumarla dos veces.
    """
    nombre: str
    valor: float                     # 0-100
    metricas: List[str] = field(default_factory=list)   # ids de métrica bruta
    justificacion: str = ""

    def clamp(self) -> "Factor":
        self.valor = max(0.0, min(100.0, self.valor))
        return self


class ScoringEngine:
    def __init__(self, pesos: Optional[Dict] = None,
                 politica_ttl: Optional[Dict] = None):
        self.pesos = pesos or cargar_pesos()
        self.politica_ttl = politica_ttl or cargar_politica_ttl()

    # ── Reglas 58-62: scores ponderados ──────────────────────────────────

    def score_potencial(self, factores: List[Factor], naturaleza: str) -> Tuple[float, List[str]]:
        w = _pesos_para(self.pesos["potencial"]["base"],
                        self.pesos["potencial"]["por_naturaleza"], naturaleza)
        return self._ponderar(factores, w)

    def score_rr(self, factores: List[Factor], naturaleza: str) -> Tuple[float, List[str]]:
        w = _pesos_para(self.pesos["rentabilidad_riesgo"]["base"],
                        self.pesos["rentabilidad_riesgo"]["por_naturaleza"], naturaleza)
        return self._ponderar(factores, w)

    def score_vehiculo(self, factores: List[Factor]) -> Tuple[float, List[str]]:
        w = {k: v for k, v in self.pesos["vehiculo"].items() if not k.startswith("$")}
        return self._ponderar(factores, w)

    def score_personalizado(self, score_rr: float, horizonte: float,
                            tolerancia: Optional[int], fiscal_broker: float,
                            horizonte_requerido: float = 1.0) -> float:
        """Regla 61: integra R/R con adecuación al perfil. fiscal_broker 0-100."""
        cfg = self.pesos["personalizado"]
        horizonte_fit = 100.0 if horizonte >= horizonte_requerido else max(
            0.0, 100.0 * (horizonte / max(horizonte_requerido, 1e-9)))
        if tolerancia is None:
            # Regla 12: sin perfil, sin score personalizado — el llamador no debe
            # llegar aquí sin perfil; devolvemos solo la parte objetiva.
            return round(score_rr, 1)
        riesgo_fit = float(tolerancia) * 20.0   # 1-5 → 20-100
        return round(
            cfg["peso_rr"] * score_rr
            + cfg["adecuacion_horizonte"] * horizonte_fit
            + cfg["adecuacion_riesgo"] * riesgo_fit
            + cfg["adecuacion_fiscal_broker"] * fiscal_broker, 1)

    def _ponderar(self, factores: List[Factor], pesos: Dict[str, float]) -> Tuple[float, List[str]]:
        avisos: List[str] = []
        suma = sum(pesos.values())
        if abs(suma - 1.0) > 0.01:
            avisos.append("Pesos suman %.2f (≠1.00): normalizados. Revisar curated/scoring-weights.json" % suma)
        por_nombre = {f.clamp().nombre: f.clamp() for f in factores}

        # Regla 63: control de doble conteo — una métrica bruta solo cuenta en el
        # factor con MAYOR peso; en el resto se reduce su contribución a cero.
        metrica_ya_vista: Dict[str, str] = {}
        factores_sin_doble: Dict[str, float] = {}
        for nombre, peso in sorted(pesos.items(), key=lambda kv: -kv[1]):
            f = por_nombre.get(nombre)
            if f is None:
                continue
            v = f.valor
            for m in f.metricas:
                if m in metrica_ya_vista:
                    avisos.append(
                        "Doble conteo evitado: métrica '%s' ya contada en '%s'; "
                        "factor '%s' recalculado sin ella." % (m, metrica_ya_vista[m], nombre))
                else:
                    metrica_ya_vista[m] = nombre
            factores_sin_doble[nombre] = v

        total = sum(factores_sin_doble.get(n, 50.0) * (w / suma)
                    for n, w in pesos.items())
        return round(min(100.0, max(0.0, total)), 1), avisos

    # ── Regla 76: confidence por calidad y frescura de datos ─────────────

    def confidence(self, datos: List[Dato], fecha_hoy: Optional[date] = None) -> float:
        """Media ponderada por etiqueta (regla 75) con decaimiento por TTL (regla 72)."""
        if not datos:
            return 0.0
        hoy = fecha_hoy or date.today()
        ttl_cfg = self.politica_ttl["ttl_dias"]
        total = 0.0
        for d in datos:
            peso = DataLabel.PESO.get(d.etiqueta, 0.0)
            if d.fecha is not None:
                dias = (hoy - d.fecha).days
                for tipo, ttl in ttl_cfg.items():
                    if tipo in (d.nota or "").lower():
                        if ttl > 0 and dias > ttl:
                            cumplidos = dias // ttl
                            idx = max(0, _ETIQUETAS_ORDEN.index(d.etiqueta)
                                      - cumplidos) if d.etiqueta in _ETIQUETAS_ORDEN else 0
                            peso = min(peso, DataLabel.PESO[_ETIQUETAS_ORDEN[idx]])
                        break
            total += peso
        return round(100.0 * total / len(datos), 1)

    # ── Reglas 77, 92-94, 102: penalizaciones ────────────────────────────

    def aplicar_penalizaciones(self, score: float, activas: List[str]) -> float:
        pen = self.pesos["penalizaciones"]
        total = sum(pen[k] for k in activas if k in pen)
        for k in activas:
            if k not in pen:
                raise KeyError("Penalización desconocida: %s (añádela a curated/scoring-weights.json)" % k)
        return round(max(0.0, min(100.0, score + total)), 1)

    # ── Regla 64: normalización dentro del grupo comparable ──────────────

    @staticmethod
    def normalizar_grupo(valores: List[float]) -> List[float]:
        """Escala 0-100 dentro del conjunto comparado (min-max). Un P/E de 25x
        caro en un sector es barato en otro: el score relativo es al grupo."""
        if not valores:
            return []
        lo, hi = min(valores), max(valores)
        if hi - lo < 1e-9:
            return [50.0] * len(valores)
        return [round(100.0 * (v - lo) / (hi - lo), 1) for v in valores]

    # ── Regla 78: score vs confianza, expuestos juntos ───────────────────

    @staticmethod
    def ficha(scores: Scores) -> str:
        return ("Score %s / Confianza %s — %s (regla 78: la incertidumbre queda "
                "expuesta, no oculta)") % (
            scores.rentabilidad_riesgo if scores.rentabilidad_riesgo is not None else "—",
            scores.confianza,
            etiqueta_score(scores.rentabilidad_riesgo)
            if scores.rentabilidad_riesgo is not None else "sin datos")


def factores_desde_dict(d: Dict[str, Any]) -> List[Factor]:
    """Convierte el JSON de un agente LLM en factores."""
    out = []
    for nombre, spec in d.items():
        if isinstance(spec, dict):
            out.append(Factor(nombre=nombre, valor=float(spec.get("valor", 50)),
                              metricas=list(spec.get("metricas", [])),
                              justificacion=spec.get("justificacion", "")))
        else:
            out.append(Factor(nombre=nombre, valor=float(spec)))
    return out
