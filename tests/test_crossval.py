"""Tests de validación cruzada — reglas 73-74.

Los tests redirigen el registro de contradicciones a un tmp (no tocan curated).
"""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from analizador.data.sources.registry import resolver
from analizador.domain.models import DataLabel, Dato


class TestJerarquiaFuentes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = os.path.join(self.tmp.name, "contradictions.json")
        self.addCleanup(self.tmp.cleanup)

    def test_regla73_gana_el_emisor(self):
        d_emisor = Dato(valor=0.20, etiqueta=DataLabel.VERIFICADO, fuente="emisor", fecha=date.today())
        d_yahoo = Dato(valor=0.25, etiqueta=DataLabel.VERIFICADO, fuente="fuente_financiera", fecha=date.today())
        r = resolver(d_emisor, d_yahoo, "ter", "ProductoX", ruta_contras=self.ruta)
        self.assertEqual(r.valor, 0.20)
        self.assertEqual(r.fuente, "emisor")
        # la discrepancia (25% > 10% de tolerancia) registró contradicción en tmp
        with open(self.ruta, encoding="utf-8") as f:
            entradas = __import__("json").load(f)["entradas"]
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["ganador"], "emisor")

    def test_dentro_de_tolerancia_sin_degradar(self):
        d1 = Dato(valor=100.0, etiqueta=DataLabel.VERIFICADO, fuente="emisor", fecha=date.today())
        d2 = Dato(valor=101.0, etiqueta=DataLabel.VERIFICADO, fuente="fuente_financiera", fecha=date.today())
        r = resolver(d1, d2, "precio", "ProductoY", ruta_contras=self.ruta)
        self.assertEqual(r.etiqueta, DataLabel.VERIFICADO)

    def test_discrepancia_grave_degrada_a_estimado(self):
        d1 = Dato(valor=100.0, etiqueta=DataLabel.VERIFICADO, fuente="emisor", fecha=date.today())
        d2 = Dato(valor=140.0, etiqueta=DataLabel.VERIFICADO, fuente="secundaria", fecha=date.today())
        r = resolver(d1, d2, "precio", "ProductoZ", ruta_contras=self.ruta)
        self.assertEqual(r.valor, 100.0)
        self.assertEqual(r.etiqueta, DataLabel.ESTIMADO)  # regla 77

    def test_una_sola_fuente_se_devuelve_tal_cual(self):
        d = Dato(valor=5, etiqueta=DataLabel.CALCULADO, fuente="proveedor_indice", fecha=date.today())
        r = resolver(d, None, "posiciones", "P", ruta_contras=self.ruta)
        self.assertEqual(r.valor, 5)
        r2 = resolver(None, None, "posiciones", "P", ruta_contras=self.ruta)
        self.assertEqual(r2.etiqueta, DataLabel.NO_DISPONIBLE)


if __name__ == "__main__":
    unittest.main()
