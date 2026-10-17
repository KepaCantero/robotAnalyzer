"""Tests del motor de scoring — reglas 58-64, 76-78."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from analizador.domain.models import DataLabel, Dato
from analizador.scoring.engine import (Factor, ScoringEngine,
                                       factores_desde_dict)

FACTORES_BASE = [
    Factor("valoracion", 80, ["pe_forward"]),
    Factor("crecimiento_fundamental", 60, ["revision_beneficios"]),
    Factor("catalizadores", 70, []),
    Factor("momentum", 55, ["rs_6m"]),
    Factor("calidad_estructural", 65, ["roic"]),
    Factor("asimetria", 60, []),
]


class TestScorePotencial(unittest.TestCase):
    def setUp(self):
        self.motor = ScoringEngine()

    def test_score_ponderado_regla58(self):
        score, avisos = self.motor.score_potencial(FACTORES_BASE, "ETF_ACCIONES")
        esperado = (80 * .25 + 60 * .25 + 70 * .15 + 55 * .10 + 65 * .15 + 60 * .10)
        self.assertAlmostEqual(score, round(esperado, 1), places=1)
        self.assertEqual(avisos, [])

    def test_pesos_adaptativos_regla62(self):
        """ETC_FUTUROS redefine pesos: mismo input, score distinto."""
        s1, _ = self.motor.score_potencial(FACTORES_BASE, "ETF_ACCIONES")
        s2, _ = self.motor.score_potencial(FACTORES_BASE, "ETC_FUTUROS")
        self.assertNotEqual(s1, s2)

    def test_factor_fuera_de_rango_se_acota(self):
        factores = [Factor("valoracion", 150, []), Factor("asimetria", -20, [])]
        score, _ = self.motor.score_potencial(factores + FACTORES_BASE[1:2], "ETF_ACCIONES")
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_control_doble_conteo_regla63(self):
        """La misma métrica en dos factores no cuenta dos veces (regla 63)."""
        con_doble = [Factor("valoracion", 90, ["pe_forward"]),
                     Factor("crecimiento_fundamental", 90, ["pe_forward"]),
                     Factor("catalizadores", 50), Factor("momentum", 50),
                     Factor("calidad_estructural", 50), Factor("asimetria", 50)]
        sin_doble = [Factor("valoracion", 90, ["pe_forward"]),
                     Factor("crecimiento_fundamental", 50, ["otra"]),
                     Factor("catalizadores", 50), Factor("momentum", 50),
                     Factor("calidad_estructural", 50), Factor("asimetria", 50)]
        s1, avisos1 = self.motor.score_potencial(con_doble, "ETF_ACCIONES")
        s2, _ = self.motor.score_potencial(sin_doble, "ETF_ACCIONES")
        self.assertGreater(s1, s2)   # el doble conteo INFLARÍA el score…
        # …pero el motor lo detecta y avisa
        self.assertTrue(any("Doble conteo" in a for a in avisos1))


class TestPenalizaciones(unittest.TestCase):
    def test_penalizacion_aplicada(self):
        motor = ScoringEngine()
        s = motor.aplicar_penalizaciones(80, ["datos_insuficientes_criticos"])
        self.assertEqual(s, 70)

    def test_penalizacion_desconocida_falla(self):
        motor = ScoringEngine()
        with self.assertRaises(KeyError):
            motor.aplicar_penalizaciones(80, ["penalizacion_inexistente"])

    def test_piso_y_techo(self):
        motor = ScoringEngine()
        self.assertEqual(motor.aplicar_penalizaciones(5, ["valoracion_extrema_sin_fundamentos"]), 0)
        self.assertEqual(motor.aplicar_penalizaciones(99, []), 99)


class TestConfianza(unittest.TestCase):
    def test_regla76_etiquetas(self):
        motor = ScoringEngine()
        datos = [Dato(valor=1, etiqueta=DataLabel.VERIFICADO, fuente="emisor"),
                 Dato(valor=1, etiqueta=DataLabel.ESTIMADO, fuente="agente")]
        c = motor.confidence(datos)
        self.assertAlmostEqual(c, (1.0 + 0.55) / 2 * 100, places=1)

    def test_sin_datos_confianza_cero(self):
        self.assertEqual(ScoringEngine().confidence([]), 0.0)

    def test_metabolismo_ttl_regla72(self):
        """Un dato 'precio' de hace 10 días degrada su etiqueta (TTL 1d)."""
        motor = ScoringEngine()
        viejo = Dato(valor=100, etiqueta=DataLabel.VERIFICADO, fuente="fuente_financiera",
                     fecha=date.today() - timedelta(days=10), nota="precio (yahoo)")
        fresco = Dato(valor=100, etiqueta=DataLabel.VERIFICADO, fuente="fuente_financiera",
                     fecha=date.today(), nota="precio (yahoo)")
        self.assertLess(motor.confidence([viejo]), motor.confidence([fresco]))


class TestPersonalizadoYNormalizacion(unittest.TestCase):
    def test_regla61_score_personalizado(self):
        motor = ScoringEngine()
        s = motor.score_personalizado(score_rr=70, horizonte=3, tolerancia=4,
                                      fiscal_broker=80, horizonte_requerido=2)
        self.assertGreater(s, 70)  # perfil holgado sube el score
        s2 = motor.score_personalizado(score_rr=70, horizonte=0.5, tolerancia=1,
                                       fiscal_broker=30, horizonte_requerido=2)
        self.assertLess(s2, 70)

    def test_regla64_normalizacion_grupo(self):
        self.assertEqual(ScoringEngine().normalizar_grupo([10, 50, 90]), [0.0, 50.0, 100.0])
        self.assertEqual(ScoringEngine().normalizar_grupo([5, 5, 5]), [50.0, 50.0, 50.0])

    def test_factores_desde_dict(self):
        fs = factores_desde_dict({"valoracion": {"valor": 70, "metricas": ["pe"]}, "momentum": 40})
        self.assertEqual(fs[0].nombre, "valoracion")
        self.assertEqual(fs[0].metricas, ["pe"])
        self.assertEqual(fs[1].valor, 40.0)


if __name__ == "__main__":
    unittest.main()
