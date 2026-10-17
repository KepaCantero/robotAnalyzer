"""Adaptador de mercado alternativo (Stooq, CSV público sin clave).

Motivación: Yahoo rate-limitea con frecuencia (HTTP 429) y degrada su API
pública; Stooq publica CSVs diarios por URL directa sin clave ni registro
(https://stooq.com/db/h/). Cobertura global con sufijos de mercado, sin
garantía para ETFs UCITS pequeños — por eso vive en una CADENA de fuentes
(mercado.py), no como sustituto único.

Reglas que aplica: 72 (fecha del último cierre como fecha del dato), 75 (precio
= VERIFICADO en lo que Stooq es fuente directa), 101 (sin datos →
NO_DISPONIBLE, jamás inventar).

Aviso operativo: Stooq filtra IPs de datacenter con un reto JavaScript
(Proof-of-Work); desde IPs residenciales responde CSV. Si devuelve HTML en
vez de CSV se trata como fuente no disponible — nunca como error del pipeline.
"""
from __future__ import annotations

import csv
import io
import urllib.request
from datetime import date, timedelta
from typing import List, Optional

from analizador.data.sources.yahoo import red_permitida
from analizador.domain.models import DataLabel, Dato

TIMEOUT_S = 10
UA = {"User-Agent": "Mozilla/5.0 (analizador-fondos; investigación personal)"}

# Sufijo Yahoo → variantes Stooq a probar en orden (la cobertura varía por
# mercado; no hay catálogo oficial, se prueban y la primera con datos gana).
_SUFIJOS = {
    "L": ("uk", "l"),     # Londres
    "DE": ("de",),        # Xetra
    "AS": ("as", "nl"),   # Ámsterdam
    "PA": ("fr", "pa"),   # París
    "US": ("us",),
}


def _get_texto(url: str) -> Optional[str]:
    if not red_permitida():
        return None
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _variantes(ticker: str) -> List[str]:
    t = ticker.strip().lower()
    if "." not in t:
        return [t + ".us", t]
    base, suf = t.rsplit(".", 1)
    return [base + "." + v for v in _SUFIJOS.get(suf.upper(), (suf,))]


def _anios(rango: str) -> float:
    r = rango.strip().lower()
    if r.endswith("y") and r[:-1].isdigit():
        return float(r[:-1])
    if r.endswith("mo") and r[:-2].isdigit():
        return float(r[:-2]) / 12.0
    return 2.0


def _parsear_csv(texto: str) -> List[List]:
    """Filas [fecha ISO, cierre] del CSV diario de Stooq. HTML (reto anti-bot)
    o series vacías → lista vacía."""
    if not texto or not texto.lstrip().lower().startswith("date,"):
        return []
    pares: List[List] = []
    for f in csv.DictReader(io.StringIO(texto)):
        cierre = (f.get("Close") or "").strip()
        fecha = (f.get("Date") or "").strip()
        if not fecha or not cierre or cierre.lower() == "n/d":
            continue
        try:
            pares.append([fecha, float(cierre)])
        except ValueError:
            continue
    return pares


def historico(ticker: str, rango: str = "2y") -> Dato:
    """Serie de cierres diarios: mismo contrato que yahoo.historico."""
    hoy = date.today()
    d1 = (hoy - timedelta(days=int(_anios(rango) * 365) + 7)).strftime("%Y%m%d")
    d2 = hoy.strftime("%Y%m%d")
    for simbolo in _variantes(ticker):
        url = ("https://stooq.com/q/d/l/?s=%s&d1=%s&d2=%s&i=d"
               % (simbolo, d1, d2))
        pares = _parsear_csv(_get_texto(url) or "")
        if len(pares) >= 2:
            return Dato(valor=pares, etiqueta=DataLabel.VERIFICADO,
                        fuente="fuente_financiera",
                        fecha=date.fromisoformat(pares[-1][0]),
                        nota="histórico precio (stooq: %s)" % simbolo)
    return Dato.no_disponible("Stooq sin serie para %s (regla 101)" % ticker)


def cotizacion(ticker: str) -> Dato:
    """Último cierre disponible (Stooq es EOD: cierre, no precio intradía)."""
    h = historico(ticker, rango="1mo")
    if h.etiqueta == DataLabel.NO_DISPONIBLE or not h.valor:
        return Dato.no_disponible(h.nota)
    return Dato(valor=h.valor[-1][1], etiqueta=DataLabel.VERIFICADO,
                fuente="fuente_financiera",
                fecha=date.fromisoformat(h.valor[-1][0]),
                nota="precio cierre (stooq)")
