"""Web → API: cualquier página web como fuente de datos (stdlib puro).

Motivación: la API pública de Yahoo es frágil (crumbs, rate limits) y las
fuentes de máxima jerarquía (regla 73: EMISOR, documento oficial) no tienen
API. Este adaptador convierte webs en markdown/JSON mediante:

  1. Firecrawl (github.com/mendableai/firecrawl — AGPL, self-host gratis)
     - Self-host: FIRECRAWL_BASE_URL=http://localhost:3002 (sin clave)
     - Cloud:    FIRECRAWL_API_KEY=... (freemium, 500 créditos iniciales)
  2. Jina Reader (fallback automático, gratuito y SIN clave):
     GET https://r.jina.ai/<url> → markdown

Ventaja metodológica (regla 73): al leer la página del EMISOR, el dato extraído
es prioridad 1 — por encima de cualquier API financiera. Scraping de
justETF/Morningstar = fuente_financiera (prioridad 6); blogs = secundaria.

Regla 101: sin servicio disponible → NO_DISPONIBLE, nunca invención.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import date
from typing import Any, Dict, Optional

from analizador.domain.models import DataLabel, Dato

TIMEOUT_S = 30


def firecrawl_disponible() -> bool:
    return bool(os.environ.get("FIRECRAWL_BASE_URL") or os.environ.get("FIRECRAWL_API_KEY"))


def _firecrawl_scrape(url: str, formato: str = "markdown") -> Optional[Dict[str, Any]]:
    base = os.environ.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev").rstrip("/")
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    body = json.dumps({"url": url, "formats": [formato]}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key
    req = urllib.request.Request(base + "/v1/scrape", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("success"):
            return data.get("data", {})
    except Exception:
        return None
    return None


def _jina_reader(url: str) -> Optional[str]:
    """Fallback gratuito sin clave: r.jina.ai devuelve markdown del URL."""
    try:
        req = urllib.request.Request(
            "https://r.jina.ai/%s" % url,
            headers={"User-Agent": "analizador-fondos",
                     "x-return-format": "markdown"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def leer_web(url: str, etiqueta_fuente: str = "fuente_financiera",
             nota: str = "") -> Dato:
    """Lee una web y devuelve su contenido como markdown en un Dato.

    etiqueta_fuente según quién es el dueño de la página (regla 73):
    'emisor' si es la web del emisor, 'fuente_financiera' para
    justETF/Morningstar, 'secundaria' para blogs/prensa.
    """
    contenido: Optional[str] = None
    via = ""
    if firecrawl_disponible():
        data = _firecrawl_scrape(url, "markdown")
        if data and data.get("markdown"):
            contenido, via = data["markdown"], "firecrawl"
    if contenido is None:
        contenido = _jina_reader(url)
        if contenido:
            via = "jina-reader"
    if contenido is None:
        return Dato.no_disponible(
            "Sin Firecrawl configurado y Jina Reader no respondió para %s "
            "(regla 101: no se inventa el contenido)" % url)
    return Dato(valor=contenido[:20000], etiqueta=DataLabel.VERIFICADO,
                fuente=etiqueta_fuente, fecha=date.today(),
                nota="%s [vía %s]" % (nota or "web→markdown", via))


def _extraer_isin(texto: str) -> Optional[str]:
    """ISIN de una página (regla 75: CALCULADO, extraído del contenido)."""
    m = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b", texto)
    return m.group(1) if m else None


def ficha_justetf(isin_o_slug: str) -> Dato:
    """Ficha de un ETF desde justETF (fuente_financiera, prioridad 6).

    Con Firecrawl configurado admite además extracción estructurada
    (schema TER/AUM/replica) — el markdown ya permite al agente leerla.
    """
    url = "https://www.justetf.com/es/etf-profile.html?isin=%s" % isin_o_slug
    return leer_web(url, etiqueta_fuente="fuente_financiera", nota="justETF")


def ficha_emisor(url_producto: str) -> Dato:
    """Página de producto del EMISOR: prioridad 1 de la jerarquía (regla 73)."""
    return leer_web(url_producto, etiqueta_fuente="emisor", nota="emisor")


def cotizacion_yfinance(ticker: str) -> Dato:
    """Cotización vía yfinance (github.com/ranaroussi/yfinance) si está
    instalado — maneja crumbs/sesiones que el endpoint crudo de Yahoo no.
    pip install yfinance  (dependencia opcional)."""
    try:
        import yfinance as yf  # noqa: PLC0415 — opcional
    except ImportError:
        return Dato.no_disponible(
            "yfinance no instalado (pip install yfinance) — regla 101")
    try:
        t = yf.Ticker(ticker)
        precio = t.fast_info.get("last_price") or t.history(period="1d")["Close"].iloc[-1]
        return Dato(valor=float(precio), etiqueta=DataLabel.VERIFICADO,
                    fuente="fuente_financiera", fecha=date.today(),
                    nota="precio (yfinance)")
    except Exception:
        return Dato.no_disponible("yfinance sin respuesta para %s" % ticker)


def historico_yfinance(ticker: str, periodo: str = "2y") -> Dato:
    """Serie de cierres ajustados vía yfinance (dependencia opcional).
    Mismo contrato que yahoo.historico: pares [fecha ISO, cierre]."""
    try:
        import yfinance as yf  # noqa: PLC0415 — opcional
    except ImportError:
        return Dato.no_disponible(
            "yfinance no instalado (pip install yfinance) — regla 101")
    try:
        h = yf.Ticker(ticker).history(period=periodo, auto_adjust=True)
        if h is None or h.empty:
            return Dato.no_disponible("yfinance sin serie para %s" % ticker)
        pares = [[idx.date().isoformat(), float(c)]
                 for idx, c in h["Close"].items() if c == c]   # c == c: filtra NaN
        if not pares:
            return Dato.no_disponible("yfinance sin cierres para %s" % ticker)
        return Dato(valor=pares, etiqueta=DataLabel.VERIFICADO,
                    fuente="fuente_financiera", fecha=h.index[-1].date(),
                    nota="histórico precio (yfinance)")
    except Exception:
        return Dato.no_disponible("yfinance sin serie para %s" % ticker)
