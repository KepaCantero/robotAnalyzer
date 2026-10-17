"""Tests del almacén de análisis — reglas 105, 122, 137."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from analizador.storage.analyses import AlmacenAnalisis


def analisis(tema, fecha, nombres):
    return {"tema": tema, "fecha": fecha,
            "top5": [{"producto": {"nombre": n}} for n in nombres]}


class TestAlmacen(unittest.TestCase):
    def test_guardar_listar_ultimo(self):
        with tempfile.TemporaryDirectory() as tmp:
            alm = AlmacenAnalisis(tmp)
            alm.guardar(analisis("cobre", "2026-10-01", ["A", "B", "C", "D", "E"]), "cobre")
            alm.guardar(analisis("oro", "2026-10-02", ["F", "G", "H", "I", "J"]), "oro")
            self.assertEqual(len(alm.listar()), 2)
            self.assertEqual(len(alm.listar("cobre")), 1)
            self.assertEqual(alm.ultimo("oro")["fecha"], "2026-10-02")

    def test_seguimiento_regla105(self):
        with tempfile.TemporaryDirectory() as tmp:
            alm = AlmacenAnalisis(tmp)
            alm.guardar(analisis("cobre", "2026-09-01", ["A", "B", "C", "D", "E"]), "cobre")
            actual = analisis("cobre", "2026-10-01", ["C", "B", "X", "A", "E"])
            notas = alm.seguimiento(actual)
            self.assertTrue(any("NUEVO" in n for n in notas))
            # el propio análisis actual no se compara consigo mismo
            actual2 = analisis("cobre", "2026-10-01", ["A", "B", "C", "D", "F"])
            notas2 = alm.seguimiento(actual2)
            self.assertTrue(any("SALE: E" in n for n in notas2))

    def test_primer_analisis_sin_historico(self):
        with tempfile.TemporaryDirectory() as tmp:
            alm = AlmacenAnalisis(tmp)
            notas = alm.seguimiento(analisis("plata", "2026-10-01", ["A", "B", "C", "D", "E"]))
            self.assertTrue(any("Primer análisis" in n for n in notas))


if __name__ == "__main__":
    unittest.main()
