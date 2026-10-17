"""Orquestador — el proceso completo de la regla 2:

INPUT → INTERPRETACIÓN → TESIS → UNIVERSO → VALIDACIÓN → FILTRADO → ANÁLISIS →
VALORACIÓN → RIESGO → COSTES → ACCESIBILIDAD → PUNTUACIÓN → RANKING → TOP 5 →
RECOMENDACIÓN → CONDICIONES DE ENTRADA → SEGUIMIENTO

El LLM aporta juicios (factores, tesis, contraanálisis); el CÓDIGO determinista
aplica pesos, penalizaciones, confianza y construye/valida el TOP 5. Así la
metodología es auditable y reproducible (regla 144: control final).
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from analizador.agents.analistas import Analista, Descubridor, Interpretador, RedTeam
from analizador.agents.base import ProveedorEco, ProveedorLLM, proveedor_por_defecto
from analizador.data.sources import mercado
from analizador.domain.models import (
    AnalisisCompleto, AnalisisProducto, Buyability, Catalizador, Cartera,
    DataLabel, Dato, Descartado, Escenario, NivelesEntrada, PerfilInversor,
    Producto, Scores, Tesis,
)
from analizador.scoring.engine import ScoringEngine, factores_desde_dict
from analizador.scoring.metricas import factor_desde_metricas, metricas_desde_dato
from analizador.scoring.top5 import construir_top5
from analizador.storage.analyses import AlmacenAnalisis

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
FICHERO_SEMILLA = os.path.join(RAIZ, ".semantic-graph", "curated", "seed-productos.json")


def cargar_semilla(ruta: str = FICHERO_SEMILLA) -> List[Producto]:
    with open(ruta, encoding="utf-8") as f:
        data = json.load(f)
    return [Producto.from_dict(p) for p in data["productos"]]


class OrquestadorAnalisis:
    def __init__(self, proveedor: Optional[ProveedorLLM] = None,
                 motor: Optional[ScoringEngine] = None,
                 almacen: Optional[AlmacenAnalisis] = None,
                 semilla: Optional[List[Producto]] = None,
                 con_red: bool = True):
        self.proveedor = proveedor or proveedor_por_defecto()
        self.motor = motor or ScoringEngine()
        self.almacen = almacen or AlmacenAnalisis(os.path.join(RAIZ, "datos", "analisis"))
        self.semilla = semilla if semilla is not None else cargar_semilla()
        # Con eco + red: los juicios siguen neutros, pero los DATOS duros
        # (cotización, métricas CALCULADO) sí se traen — degradan a
        # NO_DISPONIBLE sin red (regla 101), nunca se bloquean.
        self.con_red = con_red
        self.avisos: List[str] = []

    # ── Pipeline completo ────────────────────────────────────────────────

    def analizar_tematica(self, tema: str,
                          perfil: Optional[PerfilInversor] = None,
                          cartera: Optional[Cartera] = None) -> AnalisisCompleto:
        modo_determinista = isinstance(self.proveedor, ProveedorEco)

        # 1-2) INTERPRETACIÓN → TESIS (reglas 2-4, 19)
        interpretador = Interpretador(self.proveedor)
        tesis = interpretador.interpretar(
            tema, perfil.to_dict() if perfil else None)

        # 3) UNIVERSO (reglas 8-11): ≥10 candidatos, varias categorías
        descubridor = Descubridor(self.proveedor, self.semilla)
        universo = descubridor.descubrir(tesis)

        # 4-6) VALIDACIÓN → FILTRADO (regla 69): sin datos mínimos se marca, no se elimina
        analista = Analista(self.proveedor)
        redteam = RedTeam(self.proveedor)
        candidatos: List[AnalisisProducto] = []

        for producto in universo:
            ap = self._analizar_producto(
                analista, redteam, producto, tesis, perfil, cartera)
            candidatos.append(ap)

        # 7-13) PUNTUACIÓN → RANKING → TOP 5 (reglas 79-80, 147)
        top5, resto, reporte = construir_top5(
            candidatos, universo_explorado=len(universo),
            categorias_relevantes=tesis.get("categorias_relevantes", []))

        # Regla 91: por qué los demás no entran
        descartados = [Descartado(producto=r.producto.nombre,
                                  motivo=(r.red_team[0] if r.red_team else
                                          "score inferior (%s R/R)"
                                          % r.scores.rentabilidad_riesgo))
                       for r in resto[:5]]

        resultado = AnalisisCompleto(
            tema=tema,
            fecha=date.today().isoformat(),
            conclusion=self._conclusion(top5, tesis, modo_determinista),
            top5=top5,
            descartados=descartados,
            ganadores=self._ganadores(top5),
            recomendacion=self._recomendacion(top5),
            confianza_analisis="baja" if modo_determinista else self._confianza_media(top5),
            advertencia_sin_perfil=(
                "" if perfil else
                "El ranking es objetivo/temático y todavía no está personalizado "
                "al perfil del inversor. (regla 12)"),
            robustez=reporte.robustez,
            control_top5=reporte.resumen(),
        )
        if modo_determinista:
            self.avisos.append(
                "MODO DETERMINISTA (sin LLM): los factores son neutros de proceso, "
                "no juicios de mercado — salvo volatilidad_drawdown si hay serie de "
                "cierres (métrica CALCULADO, regla 75). Configura ANALIZADOR_LLM_* "
                "para análisis reales.")

        # 17) SEGUIMIENTO (regla 105) + persistencia versionada (regla 137)
        dict_final = resultado.to_dict()
        dict_final["avisos"] = list(self.avisos)
        seguimiento = self.almacen.seguimiento(dict_final)
        resultado.seguimiento = seguimiento
        dict_final["seguimiento"] = seguimiento
        self.almacen.guardar(dict_final, tema)
        return resultado

    # ── Análisis individual (reglas 17-54 → motor 58-64) ────────────────

    def _analizar_producto(self, analista: Analista, redteam: RedTeam,
                           producto: Producto, tesis: Dict[str, Any],
                           perfil: Optional[PerfilInversor],
                           cartera: Optional[Cartera]) -> AnalisisProducto:
        # Regla 72: datos de mercado con fecha; regla 101: fallo → NO_DISPONIBLE
        datos_mercado: Dict[str, Any] = {}
        metricas_riesgo: Dict[str, Dato] = {}
        if self.con_red and producto.ticker:
            cot = mercado.cotizacion(producto.ticker)
            datos_mercado["cotizacion"] = cot.to_dict()
            metricas_riesgo = metricas_desde_dato(mercado.historico(producto.ticker))
            if metricas_riesgo:
                # También para el LLM: que cite estos ids en sus metricas[]
                # y el control de doble conteo (regla 63) los reconcilie.
                datos_mercado["metricas_riesgo"] = {
                    k: d.to_dict() for k, d in metricas_riesgo.items()}

        salida = analista.analizar(producto, tesis, datos_mercado)

        # Motor determinista (reglas 58-60)
        fp = factores_desde_dict(salida.get("factores_potencial", {}))
        frr = factores_desde_dict(salida.get("factores_rr", {}))

        # Factor volatilidad_drawdown con datos duros: si el agente no declaró
        # ya las métricas brutas, el código inyecta el factor calculado —
        # auditable e independiente del proveedor (ADR-006, reglas 59/63/75).
        if metricas_riesgo and not any(
                m in ("volatilidad_anual", "max_drawdown")
                for f in frr for m in f.metricas):
            f_duro = factor_desde_metricas(metricas_riesgo)
            if f_duro is not None:
                frr = [f for f in frr if f.nombre != f_duro.nombre] + [f_duro]
                self.avisos.append(
                    "[%s] factor volatilidad_drawdown calculado desde serie de "
                    "cierres (%d métricas CALCULADO)" % (
                        producto.nombre, len(metricas_riesgo)))

        fv = factores_desde_dict(salida.get("factores_vehiculo", {}))
        score_pot, avisos_p = self.motor.score_potencial(fp, producto.naturaleza)
        score_rr, avisos_rr = self.motor.score_rr(frr, producto.naturaleza)
        score_veh, avisos_v = self.motor.score_vehiculo(fv)
        self.avisos.extend("[%s] %s" % (producto.nombre, a)
                           for a in (avisos_p + avisos_rr + avisos_v))

        # Penalizaciones (reglas 77, 92, 102) — declaradas por el analista/red team
        penalizaciones = list(salida.get("penalizaciones", []))
        rt = redteam.auditar(producto, {"potencial": score_pot, "rr": score_rr,
                                        "vehiculo": score_veh},
                             salida.get("tesis", {}))
        penalizaciones += rt.get("penalizaciones_adicionales", [])
        penalizaciones = list(dict.fromkeys(penalizaciones))  # sin duplicados
        score_rr = self.motor.aplicar_penalizaciones(score_rr, penalizaciones)
        score_pot = self.motor.aplicar_penalizaciones(score_pot, penalizaciones)

        # Confianza (reglas 75-76): calidad de los datos del producto; las
        # métricas CALCULADO sobre cierres VERIFICADO también computan.
        datos_calidad = [producto.ter, producto.aum, producto.spread,
                         producto.concentracion_top10, *metricas_riesgo.values()]
        if producto.isin is None:
            datos_calidad.append(Dato(etiqueta=DataLabel.INFERIDO,
                                      nota="isin no verificado (regla 101)"))
        confianza = self.motor.confidence(datos_calidad)

        # Score personalizado (regla 61): solo con perfil
        score_pers = None
        if perfil is not None:
            fiscal_fit = 50.0  # regla 71: sin broker conocido, accesibilidad pendiente
            score_pers = self.motor.score_personalizado(
                score_rr, horizonte=perfil.horizonte_anios,
                tolerancia=perfil.tolerancia_riesgo, fiscal_broker=fiscal_fit)

        tesis_prod = self._tesis_desde_dict(salida.get("tesis", {}))
        niveles_d = salida.get("niveles", {}) or {}
        niveles = NivelesEntrada(
            precio_actual=(datos_mercado.get("cotizacion", {}) or {}).get("valor"),
            fair_value=_float_o_none(niveles_d.get("fair_value")),
            precio_atractivo=_float_o_none(niveles_d.get("precio_atractivo")),
            nivel_invalidacion=_float_o_none(niveles_d.get("nivel_invalidacion")),
            etiqueta_fair_value=niveles_d.get("etiqueta_fair_value", DataLabel.ESTIMADO),
        )

        buyability = rt.get("veredicto_buyability", Buyability.MANTENER_ESPERAR)
        if buyability not in Buyability.TODOS:
            buyability = Buyability.MANTENER_ESPERAR

        return AnalisisProducto(
            producto=producto,
            explicacion_sencilla=salida.get("explicacion_sencilla", ""),
            calidad_subyacente=salida.get("calidad_subyacente", ""),
            tesis=tesis_prod,
            scores=Scores(potencial=score_pot, rentabilidad_riesgo=score_rr,
                          personalizado=score_pers, vehiculo=score_veh,
                          confianza=confianza),
            niveles=niveles,
            buyability=buyability,
            riesgos=salida.get("riesgos", []),
            coste_total_nota=salida.get("coste_total_nota", ""),
            accesibilidad=("pendiente de conocer el broker (regla 71)"
                           if not (perfil and perfil.broker) else
                           "verificar disponibilidad en %s" % perfil.broker),
            fiscalidad_nota=salida.get("fiscalidad_es_nota", ""),
            red_team=rt.get("contraargumentos", []),
            vigilar=salida.get("vigilar", []),
            metricas_riesgo={k: d.to_dict() for k, d in metricas_riesgo.items()},
        )

    # ── Reglas 84, 123, 128: ganadores, conclusión y recomendación ───────

    @staticmethod
    def _tesis_desde_dict(d: Dict[str, Any]) -> Tesis:
        return Tesis(
            positiva=d.get("positiva", ""), negativa=d.get("negativa", ""),
            catalizadores=[Catalizador(**c) for c in d.get("catalizadores", [])
                           if isinstance(c, dict) and "evento" in c],
            invalidadores=list(d.get("invalidadores", [])),
            escenarios=[Escenario(nombre=e.get("nombre", "BASE"),
                                  retorno_estimado=_float_o_none(e.get("retorno_estimado")),
                                  probabilidad=_float_o_none(e.get("probabilidad")),
                                  supuestos=e.get("supuestos", ""))
                        for e in d.get("escenarios", []) if isinstance(e, dict)],
        )

    def _conclusion(self, top5: List[AnalisisProducto], tesis: Dict[str, Any],
                    determinista: bool) -> str:
        if not top5:
            return ("No considero que exista actualmente una oportunidad "
                    "suficientemente atractiva dentro del universo analizado. (regla 109)")
        mejor = top5[0]
        base = ("Mejor opción encontrada para '%s': %s (R/R %s, confianza %s). %s"
                % (tesis.get("interpretacion", ""), mejor.producto.nombre,
                   mejor.scores.rentabilidad_riesgo, mejor.scores.confianza,
                   mejor.explicacion_sencilla))
        if determinista:
            base += " [MODO DETERMINISTA: juicio de proceso, no de mercado.]"
        return base

    def _ganadores(self, top5: List[AnalisisProducto]) -> Dict[str, str]:
        if not top5:
            return {}
        por_rr = max(top5, key=lambda a: a.scores.rentabilidad_riesgo or 0)
        por_pot = max(top5, key=lambda a: a.scores.potencial or 0)
        por_veh = max(top5, key=lambda a: a.scores.vehiculo or 0)
        por_conf = max(top5, key=lambda a: a.scores.confianza)
        return {
            "Mayor potencial": por_pot.producto.nombre,
            "Mejor rentabilidad/riesgo": por_rr.producto.nombre,
            "Mejor vehículo": por_veh.producto.nombre,
            "Mayor convicción (confianza)": por_conf.producto.nombre,
            "Mejor compra actual": "ver buyability en el análisis individual (regla 149)",
        }

    def _recomendacion(self, top5: List[AnalisisProducto]) -> str:
        comprables = [a for a in top5 if a.buyability in
                      (Buyability.COMPRA_ATRACTIVA, Buyability.COMPRA_SELECTIVA)]
        if not comprables:
            return ("Estos son los cinco mejores vehículos que he encontrado, pero "
                    "actualmente no considero que ninguno tenga un margen de seguridad "
                    "suficiente para comprar. TOP 5 ≠ recomendación de compra. "
                    "(reglas 85, 149)")
        mejor = comprables[0]
        return ("Mi elección principal sería %s porque %s. Compraría alrededor de %s "
                "con horizonte de %s; me haría cambiar de opinión: %s." % (
                    mejor.producto.nombre,
                    (mejor.tesis.positiva or "tesis pendiente de LLM")[:200],
                    ("€%s (nivel atractivo)" % mejor.niveles.precio_atractivo
                     if mejor.niveles.precio_atractivo else "precio a definir (regla 87)"),
                    "1-2 años (regla 16)",
                    (mejor.red_team[0] if mejor.red_team else "invalidadores declarados")))

    @staticmethod
    def _confianza_media(top5: List[AnalisisProducto]) -> str:
        if not top5:
            return "baja"
        media = sum(a.scores.confianza for a in top5) / len(top5)
        if media >= 75: return "alta"
        if media >= 55: return "media"
        return "baja"


def _float_o_none(x: Any) -> Optional[float]:
    if x is None or x == "no_disponible":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
