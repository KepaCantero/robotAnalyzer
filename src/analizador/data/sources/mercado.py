"""Cadena de fuentes de mercado — ningún dato depende de un solo proveedor.

Yahoo (v8 JSON) y Stooq (CSV sin clave) son fuente_financiera (regla 73); se
consultan en orden configurable con ANALIZADOR_FUENTES_MERCADO (por defecto
"yahoo,stooq") y la primera que responde datos gana. Si todas fallan, el
resultado es NO_DISPONIBLE con la traza de qué se intentó en la nota
(reglas 101/144: auditable, nunca inventado).

El resto del sistema (orquestador, MCP, métricas) habla SOLO con esta fachada:
añadir una fuente nueva es añadir su módulo aquí, sin tocar el pipeline.
"""
from __future__ import annotations

import os
from typing import Any, Callable, List, Tuple

from analizador.data.sources import stooq, yahoo
from analizador.domain.models import DataLabel, Dato

_ORDEN_DEFECTO = "yahoo,stooq"


def _fuentes() -> List[Tuple[str, Any]]:
    orden = os.environ.get("ANALIZADOR_FUENTES_MERCADO", _ORDEN_DEFECTO)
    tabla = {"yahoo": yahoo, "stooq": stooq}
    out = [(n.strip().lower(), tabla[n.strip().lower()])
           for n in orden.split(",") if n.strip().lower() in tabla]
    return out or [("yahoo", yahoo)]


def _primera_con_datos(fn_por_fuente: Callable[[Any], Dato],
                       ticker: str, contexto: str) -> Dato:
    errores = []
    for nombre, mod in _fuentes():
        try:
            d = fn_por_fuente(mod)
        except Exception:
            continue
        if d.etiqueta != DataLabel.NO_DISPONIBLE:
            return d
        errores.append("%s: %s" % (nombre, d.nota))
    return Dato.no_disponible(
        "Todas las fuentes fallaron para %s%s → %s (regla 101)"
        % (ticker, contexto, "; ".join(errores) or "sin fuentes configuradas"))


def cotizacion(ticker: str) -> Dato:
    """Último precio/cierre disponible según la primera fuente que responda."""
    return _primera_con_datos(lambda m: m.cotizacion(ticker), ticker, "")


def historico(ticker: str, rango: str = "2y") -> Dato:
    """Serie de cierres: primera fuente con datos (contrato de yahoo.historico)."""
    return _primera_con_datos(lambda m: m.historico(ticker, rango),
                              ticker, " (rango %s)" % rango)
