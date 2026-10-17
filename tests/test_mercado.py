"""Tests del adaptador Stooq (CSV sin clave) y de la cadena de fuentes
mercado.py — reglas 72, 75, 101: nada depende de un solo proveedor y todo
fallo degrada a NO_DISPONIBLE con traza auditable.
"""
import os
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from analizador.data.sources import mercado, stooq, yahoo
from analizador.domain.models import DataLabel, Dato

HOY = date.today()


def _csv_stooq(n=40, paso=1.0):
    filas = ["Date,Open,High,Low,Close,Volume"]
    base = HOY - timedelta(days=n - 1)
    for i in range(n):
        d = (base + timedelta(days=i)).isoformat()
        c = 100.0 + paso * i
        filas.append("%s,%0.2f,%0.2f,%0.2f,%0.2f,%d" % (d, c, c, c, c, 1000))
    return "\n".join(filas)


class TestStooq(unittest.TestCase):
    def test_parsea_csv_y_fecha_ultimo_cierre(self):
        with mock.patch.object(stooq, "_get_texto", return_value=_csv_stooq(40)):
            d = stooq.historico("COPM.L")
        self.assertEqual(d.etiqueta, DataLabel.VERIFICADO)
        self.assertEqual(len(d.valor), 40)
        self.assertEqual(d.fecha, HOY)                  # regla 72
        self.assertIn("stooq: copm.uk", d.nota)         # primera variante de .L
        self.assertAlmostEqual(d.valor[-1][1], 139.0)

    def test_html_anti_bot_es_no_disponible(self):
        html = "<!DOCTYPE html><html>... reto JavaScript ...</html>"
        with mock.patch.object(stooq, "_get_texto", return_value=html):
            d = stooq.historico("VWCE.DE")
        self.assertEqual(d.etiqueta, DataLabel.NO_DISPONIBLE)

    def test_salta_filas_nd(self):
        csv_txt = _csv_stooq(5) + "\n%s,N/D,N/D,N/D,N/D,0" % HOY.isoformat()
        with mock.patch.object(stooq, "_get_texto", return_value=csv_txt):
            d = stooq.historico("X.DE")
        self.assertEqual(len(d.valor), 5)               # la fila N/D se ignora

    def test_variante_de_sufijo_como_fallback(self):
        """Si la primera variante no tiene datos, prueba la siguiente."""
        def falso(url):
            return _csv_stooq(30) if "copm.l" in url else ""
        with mock.patch.object(stooq, "_get_texto", side_effect=falso):
            d = stooq.historico("COPM.L")
        self.assertEqual(d.etiqueta, DataLabel.VERIFICADO)
        self.assertIn("copm.l", d.nota)                 # ganó la 2ª variante

    def test_cotizacion_deriva_del_ultimo_cierre(self):
        with mock.patch.object(stooq, "_get_texto", return_value=_csv_stooq(10)):
            d = stooq.cotizacion("IWDA.AS")
        self.assertEqual(d.etiqueta, DataLabel.VERIFICADO)
        self.assertEqual(d.fecha, HOY)
        self.assertIn("stooq", d.nota)


class TestCadenaMercado(unittest.TestCase):
    def test_stooq_cubre_cuando_yahoo_falla(self):
        yahoo_caído = Dato.no_disponible("Sin red o ticker sin respuesta: X")
        with mock.patch.object(yahoo, "historico", return_value=yahoo_caído), \
             mock.patch.object(stooq, "_get_texto", return_value=_csv_stooq(50)):
            d = mercado.historico("VWCE.DE")
        self.assertEqual(d.etiqueta, DataLabel.VERIFICADO)
        self.assertIn("stooq", d.nota)                  # ganó la segunda fuente

    def test_orden_configurable_por_env(self):
        stooq_primero = Dato(valor=1.0, etiqueta=DataLabel.VERIFICADO,
                             fuente="fuente_financiera", fecha=HOY, nota="stooq")
        with mock.patch.dict(os.environ, {"ANALIZADOR_FUENTES_MERCADO": "stooq"}), \
             mock.patch.object(stooq, "cotizacion", return_value=stooq_primero), \
             mock.patch.object(yahoo, "cotizacion") as y_no_deberia:
            d = mercado.cotizacion("COPM.L")
        self.assertEqual(d.nota, "stooq")
        y_no_deberia.assert_not_called()

    def test_todas_fallan_no_disponible_con_traza(self):
        with mock.patch.object(yahoo, "historico",
                               return_value=Dato.no_disponible("429")), \
             mock.patch.object(stooq, "historico",
                               return_value=Dato.no_disponible("sin serie")):
            d = mercado.historico("NADA.X")
        self.assertEqual(d.etiqueta, DataLabel.NO_DISPONIBLE)
        self.assertIn("yahoo: 429", d.nota)             # traza auditable
        self.assertIn("stooq: sin serie", d.nota)

    def test_excepcion_de_una_fuente_no_tumba_la_cadena(self):
        with mock.patch.object(yahoo, "cotizacion", side_effect=RuntimeError("boom")), \
             mock.patch.object(stooq, "_get_texto", return_value=_csv_stooq(10)):
            d = mercado.cotizacion("COPM.L")
        self.assertEqual(d.etiqueta, DataLabel.VERIFICADO)


if __name__ == "__main__":
    unittest.main()
