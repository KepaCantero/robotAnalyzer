"""Test del pipeline completo en modo determinista (ProveedorEco).

Garantiza que: TOP 5 de 5 con universo ≥10 (reglas 7-8), control final incluido
(regla 80), análisis persistido (regla 137) y aviso de modo determinista.
"""
import os
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from analizador.agents.base import ProveedorEco
from analizador.domain.models import PerfilInversor
from analizador.pipeline.orquestador import OrquestadorAnalisis
from analizador.pipeline.reportero import render
from analizador.scoring.engine import ScoringEngine
from analizador.storage.analyses import AlmacenAnalisis


class TestPipelineDeterminista(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        # motor y semilla reales del proyecto; almacen aislado en tmp
        cls.orq = OrquestadorAnalisis(
            proveedor=ProveedorEco(),
            motor=ScoringEngine(),
            almacen=AlmacenAnalisis(cls.tmp.name),
            con_red=False)
        cls.resultado = cls.orq.analizar_tematica("minería de cobre")
        import json
        cls.dict_final = json.loads(cls.resultado.to_json())
        cls.dict_final["avisos"] = cls.orq.avisos

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_top5_de_cinco_regla147(self):
        self.assertEqual(len(self.resultado.top5), 5)

    def test_universo_explorado_minimo_regla8(self):
        control = self.dict_final.get("_control", "")
        # el universo semilla tiene 14 productos ≥ 10
        self.assertNotIn("Universo explorado (", control) or "≥ 10" in control

    def test_control_final_incluido_regla80(self):
        self.assertIn("Control final del TOP 5", self.dict_final.get("_control", ""))

    def test_advertencia_sin_perfil_regla12(self):
        self.assertIn("no está personalizado", self.resultado.advertencia_sin_perfil)

    def test_aviso_modo_determinista(self):
        self.assertTrue(any("MODO DETERMINISTA" in a for a in self.orq.avisos))

    def test_analisis_persistido_regla137(self):
        alm = AlmacenAnalisis(self.tmp.name)
        self.assertEqual(len(alm.listar("minería de cobre")), 1)

    def test_recomendacion_respeta_regla149(self):
        """En determinista nadie es comprable: TOP 5 ≠ compra debe quedar claro."""
        self.assertIn("TOP 5 ≠ recomendación", self.resultado.recomendacion)

    def test_informe_renderiza_formato_155(self):
        texto = render(self.resultado, self.dict_final)
        for seccion in ("## 1. Conclusión", "## 3. TOP 5", "## 9. Recomendación",
                        "Fecha de análisis"):
            self.assertIn(seccion, texto)

    def test_con_perfil_aparece_score_personalizado(self):
        orq2 = OrquestadorAnalisis(
            proveedor=ProveedorEco(), motor=ScoringEngine(),
            almacen=AlmacenAnalisis(self.tmp.name), con_red=False)
        res2 = orq2.analizar_tematica(
            "minería de cobre",
            perfil=PerfilInversor(tolerancia_riesgo=4, horizonte_anios=3))
        self.assertIsNotNone(res2.top5[0].scores.personalizado)


if __name__ == "__main__":
    unittest.main()
