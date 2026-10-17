"""Tests de métricas cuantitativas (scoring/metricas.py), del adaptador de
histórico (yahoo.historico) y de la inyección del factor duro en el pipeline
(reglas 59, 63, 72, 75, 101).
"""
import os
import statistics
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from analizador.data.sources import yahoo
from analizador.domain.models import DataLabel, Dato
from analizador.scoring.metricas import (
    factor_desde_metricas, max_drawdown, metricas_desde_dato,
    retornos_diarios, sharpe, sortino, volatilidad_anualizada,
)

HOY = date.today()


def _serie_v8(cierres):
    """Payload sintético del endpoint v8 chart: un cierre por día hasta HOY."""
    base = HOY - timedelta(days=len(cierres) - 1)
    ts = [int(datetime.combine(base + timedelta(days=i), datetime.min.time()).timestamp())
          for i in range(len(cierres))]
    return {"chart": {"result": [{
        "timestamp": ts,
        "indicators": {"quote": [{"close": list(cierres)}],
                       "adjclose": [{"adjclose": list(cierres)}]}}]}}


class TestAdaptadorHistorico(unittest.TestCase):
    def test_parsea_pares_con_fecha_del_ultimo_cierre(self):
        cierres = [100.0 + i for i in range(40)]
        with mock.patch.object(yahoo, "_get_json", return_value=_serie_v8(cierres)):
            d = yahoo.historico("TEST.L")
        self.assertEqual(d.etiqueta, DataLabel.VERIFICADO)
        self.assertEqual(len(d.valor), 40)
        self.assertEqual(d.valor[0][0], (HOY - timedelta(days=39)).isoformat())
        self.assertEqual(d.fecha, HOY)          # regla 72: fecha del último cierre
        self.assertIn("histórico", d.nota)

    def test_salta_cierres_nulos(self):
        cierres = [100.0] * 5 + [None] + [101.0] * 40
        with mock.patch.object(yahoo, "_get_json", return_value=_serie_v8(cierres)):
            d = yahoo.historico("TEST.L")
        self.assertEqual(len(d.valor), 45)

    def test_sin_red_no_disponible_regla101(self):
        with mock.patch.object(yahoo, "red_permitida", return_value=False):
            d = yahoo.historico("TEST.L")
        self.assertEqual(d.etiqueta, DataLabel.NO_DISPONIBLE)
        self.assertIsNone(d.valor)

    def test_respuesta_ininterpretable_no_disponible(self):
        with mock.patch.object(yahoo, "_get_json", return_value={"chart": {}}):
            d = yahoo.historico("TEST.L")
        self.assertEqual(d.etiqueta, DataLabel.NO_DISPONIBLE)


class TestMetricas(unittest.TestCase):
    def test_volatilidad_anualizada_muestra(self):
        ret = [0.01, -0.02, 0.015, 0.005, -0.01, 0.02]
        esperado = statistics.stdev(ret) * (252 ** 0.5)
        self.assertAlmostEqual(volatilidad_anualizada(ret), esperado)

    def test_serie_mas_volatil_mayor_volatilidad(self):
        calmado = retornos_diarios([100 * (1.001 ** i) for i in range(60)])
        brusco = calmado + [0.08, -0.08, 0.09, -0.09]
        self.assertLess(volatilidad_anualizada(calmado),
                        volatilidad_anualizada(brusco))

    def test_max_drawdown_serie_conocida(self):
        self.assertAlmostEqual(max_drawdown([100, 120, 60, 90]), -0.5)
        self.assertEqual(max_drawdown([100, 110, 120]), 0.0)
        self.assertIsNone(max_drawdown([100]))

    def test_constante_sin_falsa_precisionion(self):
        """Sin dispersión los ratios son indefinidos → None (regla 41)."""
        self.assertEqual(volatilidad_anualizada([0.0] * 5), 0.0)
        self.assertIsNone(sharpe([0.0] * 5))
        self.assertIsNone(sortino([0.0, 0.0]))

    def test_sharpe_positivo_en_alcista(self):
        cierres = [100 * (1.01 ** i) for i in range(60)]
        self.assertGreater(sharpe(retornos_diarios(cierres)), 0)

    def test_sortino_none_sin_perdidas(self):
        self.assertIsNone(sortino([0.01] * 10))

    def test_metricas_desde_dato_etiquetas_calculado(self):
        cierres = [100.0 * (1 + 0.004 * ((-1) ** i)) for i in range(50)]
        d = Dato(valor=[[(HOY - timedelta(days=49 - i)).isoformat(), c]
                        for i, c in enumerate(cierres)],
                 etiqueta=DataLabel.VERIFICADO, fuente="fuente_financiera",
                 fecha=HOY, nota="histórico precio (yahoo)")
        m = metricas_desde_dato(d)
        self.assertEqual(set(m), {"volatilidad_anual", "max_drawdown", "sharpe", "sortino"})
        for x in m.values():
            self.assertEqual(x.etiqueta, DataLabel.CALCULADO)   # regla 75
            self.assertEqual(x.fecha, HOY)                       # regla 72

    def test_serie_corta_o_mal_dato_sin_metricas(self):
        corta = Dato(valor=[["2026-01-01", 100.0], ["2026-01-02", 101.0]],
                     etiqueta=DataLabel.VERIFICADO)
        self.assertEqual(metricas_desde_dato(corta), {})
        self.assertEqual(metricas_desde_dato(Dato.no_disponible()), {})


class TestFactorDesdeMetricas(unittest.TestCase):
    @staticmethod
    def _m(vol, dd):
        return {"volatilidad_anual": Dato(valor=vol, etiqueta=DataLabel.CALCULADO),
                "max_drawdown": Dato(valor=dd, etiqueta=DataLabel.CALCULADO)}

    def test_escala_convencional_punto_medio(self):
        f = factor_desde_metricas(self._m(0.20, -0.30))
        self.assertEqual(f.nombre, "volatilidad_drawdown")
        self.assertEqual(f.valor, 50.0)     # 0.2/0.40 y 0.3/0.60 → ambos al 50%

    def test_tope_y_exceso_acotados(self):
        self.assertEqual(factor_desde_metricas(self._m(0.55, -0.80)).valor, 0.0)
        self.assertEqual(factor_desde_metricas(self._m(0.0, 0.0)).valor, 100.0)

    def test_declara_ids_brutos_regla63(self):
        f = factor_desde_metricas(self._m(0.2, -0.3))
        self.assertEqual(sorted(f.metricas), ["max_drawdown", "volatilidad_anual"])

    def test_sin_vol_ni_dd_none(self):
        self.assertIsNone(factor_desde_metricas({}))
        solo_sharpe = {"sharpe": Dato(valor=1.0, etiqueta=DataLabel.CALCULADO)}
        self.assertIsNone(factor_desde_metricas(solo_sharpe))


class TestInyeccionEnPipeline(unittest.TestCase):
    """Con red (mockeada) el pipeline determinista inyecta el factor duro:
    el score sigue siendo del motor (ADR-006) pero deja de ser 50 ciego."""

    def test_factor_duro_llega_al_analisis_y_al_aviso(self):
        from analizador.agents.base import ProveedorEco
        from analizador.pipeline.orquestador import OrquestadorAnalisis
        from analizador.scoring.engine import ScoringEngine
        from analizador.storage.analyses import AlmacenAnalisis

        cierres = [100.0 * (1.004 ** i) for i in range(60)]
        hist = Dato(valor=[[(HOY - timedelta(days=59 - i)).isoformat(), c]
                           for i, c in enumerate(cierres)],
                    etiqueta=DataLabel.VERIFICADO, fuente="fuente_financiera",
                    fecha=HOY, nota="histórico precio (yahoo)")
        cot = Dato(valor=cierres[-1], etiqueta=DataLabel.VERIFICADO,
                   fuente="fuente_financiera", fecha=HOY, nota="precio (yahoo)")
        tmp = tempfile.TemporaryDirectory()
        try:
            with mock.patch.object(yahoo, "cotizacion", return_value=cot), \
                 mock.patch.object(yahoo, "historico", return_value=hist):
                orq = OrquestadorAnalisis(
                    proveedor=ProveedorEco(), motor=ScoringEngine(),
                    almacen=AlmacenAnalisis(tmp.name), con_red=True)
                res = orq.analizar_tematica("minería de cobre")
        finally:
            tmp.cleanup()

        con_metricas = [a for a in res.top5 if a.metricas_riesgo]
        self.assertTrue(con_metricas)   # todo top5 con ticker tiene métricas
        self.assertIn("volatilidad_anual", con_metricas[0].metricas_riesgo)
        self.assertEqual(con_metricas[0].metricas_riesgo["volatilidad_anual"]["etiqueta"],
                         "CALCULADO")
        self.assertTrue(any("volatilidad_drawdown calculado" in a for a in orq.avisos))


if __name__ == "__main__":
    unittest.main()
