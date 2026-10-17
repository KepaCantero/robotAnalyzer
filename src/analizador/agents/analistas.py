"""Agentes del analizador: intérprete, descubridor, analista, red team.

Cada agente = prompt (destilado de las 156 reglas) + proveedor LLM + salida
JSON validada. Con ProveedorEco (offline) cada agente genera un borrador
determinista explícitamente marcado como tal — nada se inventa como dato real.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from analizador.agents.base import ProveedorEco, ProveedorLLM, extraer_json
from analizador.domain.models import CATEGORIAS, Producto

RUTA_PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


def _prompt(nombre: str) -> str:
    with open(os.path.join(RUTA_PROMPTS, nombre), encoding="utf-8") as f:
        return f.read()


class AgenteBase:
    nombre = "base"

    def __init__(self, proveedor: ProveedorLLM):
        self.proveedor = proveedor

    def _llamar_json(self, system: str, user: str) -> Dict[str, Any]:
        crudo = self.proveedor.completar(system, user)
        datos = extraer_json(crudo)
        if datos is None:
            raise ValueError("[%s] El proveedor no devolvió JSON válido: %.200s"
                             % (self.nombre, crudo))
        return datos


class Interpretador(AgenteBase):
    """Reglas 2-4, 19, 55-57: input → tesis + categorías relevantes."""

    nombre = "interpretador"

    def __init__(self, proveedor: ProveedorLLM):
        super().__init__(proveedor)
        self.system = _prompt("maestro.md") + "\n\n" + _prompt("interpretador.md")

    def interpretar(self, tema: str, perfil_dict: Optional[Dict] = None) -> Dict[str, Any]:
        user = "Input del usuario: %s\n\nPerfil (si existe): %s" % (
            tema, perfil_dict or "sin perfil (regla 12: seguir sin bloquear)")
        out = self._llamar_json(self.system, user)
        if "modo" in out:  # ProveedorEco
            out = self._determinista(tema)
        cats = [c for c in out.get("categorias_relevantes", []) if c in CATEGORIAS]
        out["categorias_relevantes"] = cats or ["ETF_SECTORIAL", "ETF_GLOBAL", "ETC"]
        return out

    @staticmethod
    def _determinista(tema: str) -> Dict[str, Any]:
        return {
            "interpretacion": ("Interpretación pendiente de LLM (modo determinista). "
                               "Tema recibido: '%s'. Se asume tesis sectorial genérica "
                               "para poder ejecutar el pipeline." % tema),
            "tesis_positiva": "Borrador determinista: demanda estructural del tema.",
            "tesis_negativa": "Borrador determinista: ciclo y valoración pueden descontar la tesis.",
            "catalizadores": [],
            "invalidadores": ["Sin análisis LLM real: todo veredicto es provisional."],
            "macro": [],
            "regimen_mercado": "no disponible",
            "categorias_relevantes": ["ETF_SECTORIAL", "ETF_GLOBAL", "ETC",
                                      "EXPOSICION_INDIRECTA", "FACTOR_VALUE"],
            "horizonte_recomendado_anios": 2.0,
        }


class Descubridor(AgenteBase):
    """Reglas 8-11, 68-70: universo ≥10 candidatos por categorías."""

    nombre = "descubridor"

    def __init__(self, proveedor: ProveedorLLM, semilla: List[Producto]):
        super().__init__(proveedor)
        self.system = _prompt("maestro.md") + "\n\n" + _prompt("descubridor.md")
        self.semilla = semilla

    def descubrir(self, tesis: Dict[str, Any]) -> List[Producto]:
        cats = tesis.get("categorias_relevantes", [])
        user = ("Tesis: %s\nCategorías relevantes: %s\nUniverso semilla disponible: %s"
                % (tesis.get("interpretacion", ""), ", ".join(cats),
                   ", ".join(p.nombre for p in self.semilla)))
        out = self._llamar_json(self.system, user)
        if "candidatos" not in out:  # ProveedorEco u omisión → semilla filtrada
            return self._desde_semilla(cats)
        productos = []
        for c in out["candidatos"]:
            if isinstance(c.get("nombre"), str) and c["nombre"]:
                productos.append(Producto(
                    nombre=c["nombre"], ticker=c.get("ticker", "") or "",
                    isin=c.get("isin") or None, emisor=c.get("emisor", ""),
                    categoria=c.get("categoria", "ETF_GLOBAL"),
                    naturaleza=c.get("naturaleza", "ETF_ACCIONES"),
                    notas=c.get("motivo_inclusion", "")))
        return productos or self._desde_semilla(cats)

    def _desde_semilla(self, cats: List[str]) -> List[Producto]:
        seleccion = [p for p in self.semilla if p.categoria in cats]
        # Regla 70: no descartar solo por categoría no listada si la semilla es corta
        if len(seleccion) < 10:
            resto = [p for p in self.semilla if p not in seleccion]
            seleccion += resto[:10 - len(seleccion)]
        return seleccion


class Analista(AgenteBase):
    """Reglas 17-54: análisis por producto → factores + tesis + niveles."""

    nombre = "analista"

    def __init__(self, proveedor: ProveedorLLM):
        super().__init__(proveedor)
        self.system = _prompt("maestro.md") + "\n\n" + _prompt("analista.md")

    def analizar(self, producto: Producto, tesis: Dict[str, Any],
                 datos_extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        user = ("Producto: %s\nCategoría: %s / %s\nISIN verificado: %s\n"
                "Ticker: %s\nNotas semilla: %s\nDatos de mercado: %s\nTesis de la "
                "temática: %s" % (
                    producto.nombre, producto.categoria, producto.naturaleza,
                    producto.isin or "NO (regla 101: no inventar)", producto.ticker,
                    producto.notas, datos_extra or {}, tesis.get("interpretacion", "")))
        out = self._llamar_json(self.system, user)
        if "factores_potencial" not in out:  # ProveedorEco
            out = self._determinista(producto)
        return out

    @staticmethod
    def _determinista(p: Producto) -> Dict[str, Any]:
        """Factores neutros (50) modulados SOLO por lo que la semilla declara.
        No simula conocimiento de mercado: simula disciplina de proceso."""
        ajuste_futuros = -8 if p.naturaleza == "ETC_FUTUROS" else 0   # roll yield (regla 50)
        return {
            "explicacion_sencilla": (
                "Modo determinista: análisis cualitativo pendiente. Producto de "
                "categoría %s." % p.categoria),
            "calidad_subyacente": "no disponible sin LLM",
            "calidad_vehiculo": "no disponible sin LLM",
            "tesis": {"positiva": "", "negativa": "",
                      "catalizadores": [], "invalidadores": [], "escenarios": []},
            "factores_potencial": {
                "valoracion": {"valor": 50, "metricas": [], "justificacion": "neutro determinista"},
                "crecimiento_fundamental": {"valor": 50, "metricas": []},
                "catalizadores": {"valor": 50, "metricas": []},
                "momentum": {"valor": 50, "metricas": []},
                "calidad_estructural": {"valor": 50, "metricas": []},
                "asimetria": {"valor": 50 + ajuste_futuros, "metricas": []},
            },
            "factores_rr": {
                "potencial": {"valor": 50, "metricas": ["score_potencial"]},
                "riesgo_perdida_permanente": {
                    "valor": 60 + ajuste_futuros, "metricas": [],
                    "justificacion": "futuros: decay estructural eleva el riesgo de "
                                     "pérdida permanente y reduce el factor (regla 50)"},
                "valoracion": {"valor": 50, "metricas": []},
                "calidad": {"valor": 50, "metricas": []},
                "volatilidad_drawdown": {"valor": 50, "metricas": []},
                "liquidez_estructura": {"valor": 50, "metricas": []},
                "diversificacion": {"valor": 40 if p.categoria == "ETF_SECTORIAL" else 60,
                                     "metricas": []},
            },
            "factores_vehiculo": {k: {"valor": 50, "metricas": []}
                                  for k in ("estructura", "costes", "liquidez", "tracking",
                                            "tamano", "transparencia", "fiscalidad",
                                            "accesibilidad", "riesgo_contraparte")},
            "niveles": {},
            "penalizaciones": ["datos_insuficientes_criticos"],
            "riesgos": ["modo determinista: riesgos específicos sin analizar"],
            "coste_total_nota": "TER sin verificar (regla 23): no disponible",
            "fiscalidad_es_nota": "",
            "vigilar": [],
        }


class RedTeam(AgenteBase):
    """Reglas 118-119, 150, 154: contraanálisis y buyability."""

    nombre = "red_team"

    def __init__(self, proveedor: ProveedorLLM):
        super().__init__(proveedor)
        self.system = _prompt("maestro.md") + "\n\n" + _prompt("redteam.md")

    def auditar(self, producto: Producto, scores_dict: Dict[str, Any],
                tesis_producto: Dict[str, Any]) -> Dict[str, Any]:
        user = ("Producto: %s\nScores del motor: %s\nTesis: %s\n"
                "Intenta destruir la tesis (regla 119)." % (
                    producto.nombre, scores_dict, tesis_producto))
        out = self._llamar_json(self.system, user)
        if "contraargumentos" not in out:
            out = {
                "contraargumentos": ["Modo determinista: red team pendiente de LLM; "
                                     "tratar todo veredicto como MANTENER / ESPERAR."],
                "supuestos_debiles": [], "riesgos_subestimados": [],
                "alternativas_superiores": [],
                "veredicto_buyability": "MANTENER / ESPERAR",
                "cambio_de_opinion": "completar con LLM",
                "penalizaciones_adicionales": [],
            }
        return out
