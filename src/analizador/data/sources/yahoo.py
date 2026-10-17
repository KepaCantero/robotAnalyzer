"""Adaptador de mercado (Yahoo Finance público, sin clave).

Reglas que aplica:
- 72: cada dato vuelve con fecha del día (nada "antiguo como actual").
- 75: los datos llegan etiquetados (fuente financiera reconocida → VERIFICADO
  en lo que Yahoo es fuente directa: precio; CALCULADO para derivados).
- 73: 'yahoo' es fuente_financiera — nunca sustituye al emisor si existe.
- 101: si falla la red devuelve NO_DISPONIBLE; jamás inventa un valor.

Sin red (ANALIZADOR_ALLOW_NETWORK=0 o timeout) el sistema degrada con gracia.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date
from typing import Any, Dict, Optional

from analizador.domain.models import DataLabel, Dato

TIMEOUT_S = 8
UA = {"User-Agent": "Mozilla/5.0 (analizador-fondos; investigación personal)"}


def red_permitida() -> bool:
    return os.environ.get("ANALIZADOR_ALLOW_NETWORK", "1") not in ("0", "false", "no")


def _get_json(url: str) -> Optional[Dict[str, Any]]:
    if not red_permitida():
        return None
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def cotizacion(ticker: str) -> Dato:
    """Precio de cierre ajustado del último día disponible."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s"
           "?range=1mo&interval=1d" % urllib.parse.quote(ticker))
    data = _get_json(url)
    if not data:
        return Dato.no_disponible("Sin red o ticker sin respuesta: %s" % ticker)
    try:
        res = data["chart"]["result"][0]
        meta = res["meta"]
        precio = meta.get("regularMarketPrice")
        ts = meta.get("regularMarketTime")
        d = date.fromtimestamp(ts).isoformat() if ts else date.today().isoformat()
        return Dato(valor=precio, etiqueta=DataLabel.VERIFICADO, fuente="fuente_financiera",
                    fecha=date.fromisoformat(d), nota="precio (yahoo)")
    except (KeyError, IndexError, TypeError, ValueError):
        return Dato.no_disponible("Respuesta no interpretable para %s" % ticker)


def historico(ticker: str, rango: str = "2y") -> Dato:
    """Serie de cierres ajustados diarios (reglas 72/75/101).

    Dato.valor = pares [fecha ISO, cierre]; la fecha del Dato es la del último
    cierre disponible. Base de las métricas cuantitativas (scoring/metricas.py).
    """
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s"
           "?range=%s&interval=1d" % (urllib.parse.quote(ticker),
                                      urllib.parse.quote(rango)))
    data = _get_json(url)
    if not data:
        return Dato.no_disponible("Sin red o ticker sin respuesta: %s" % ticker)
    try:
        res = data["chart"]["result"][0]
        cierres = ((res.get("indicators", {}).get("adjclose") or [{}])[0]
                   .get("adjclose")
                   or res["indicators"]["quote"][0]["close"])
        pares = [[date.fromtimestamp(t).isoformat(), float(c)]
                 for t, c in zip(res["timestamp"], cierres) if c is not None]
        if not pares:
            return Dato.no_disponible("Serie sin cierres para %s" % ticker)
        return Dato(valor=pares, etiqueta=DataLabel.VERIFICADO,
                    fuente="fuente_financiera",
                    fecha=date.fromisoformat(pares[-1][0]),
                    nota="histórico precio (yahoo)")
    except (KeyError, IndexError, TypeError, ValueError):
        return Dato.no_disponible("Respuesta no interpretable para %s" % ticker)


def buscar(query: str, limite: int = 10) -> list:
    """Búsqueda de tickers (descubrimiento de universo, regla 8)."""
    url = ("https://query2.finance.yahoo.com/v1/finance/search?q=%s&quotesCount=%d"
           "&newsCount=0" % (urllib.parse.quote(query), limite))
    data = _get_json(url)
    if not data:
        return []
    out = []
    for q in data.get("quotes", [])[:limite]:
        out.append({
            "ticker": q.get("symbol", ""),
            "nombre": q.get("shortname") or q.get("longname") or "",
            "tipo": q.get("quoteType", ""),
            "exchange": q.get("exchDisp") or q.get("exchange", ""),
        })
    return out
