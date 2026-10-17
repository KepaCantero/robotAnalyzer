"""Registro de fuentes y validación cruzada — reglas 73-74.

Jerarquía de fuentes (regla 73): emisor > documento oficial > proveedor índice >
regulador > organismo estadístico > fuente financiera reconocida > secundarias.
Una fuente secundaria NUNCA sustituye un dato oficial disponible.

La validación cruzada (regla 74) resuelve conflictos por prioridad y, si la
discrepancia supera la tolerancia, registra una Contradicción que alimenta el
grafo (patrón fukura: contradictions.json curadas + grafo).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import date
from typing import Any, Dict, List, Optional

from analizador.domain.models import DataLabel, Dato

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
FICHERO_CONTRAS = os.path.join(RAIZ, ".semantic-graph", "curated", "contradictions.json")

# Regla 73: menor número = mayor prioridad.
JERARQUIA_FUENTES = [
    "emisor",                  # 1. Emisor (iShares, Amundi, Vanguard…)
    "documento_oficial",       # 2. Folleto/KID/prospecto
    "proveedor_indice",        # 3. MSCI, FTSE, S&P…
    "regulador",               # 4. CNMV, SEC…
    "organismo_estadistico",   # 5. BCE, FMI, INE…
    "fuente_financiera",       # 6. Morningstar, justETF, Bloomberg…
    "secundaria",              # 7. Prensa, blogs, foros
    "agente",                  # 8. Estimación declarada del agente LLM (regla 75)
]

PRIORIDAD = {f: i for i, f in enumerate(JERARQUIA_FUENTES)}

# Tolerancias de discrepancia por tipo de dato (fracción relativa).
TOLERANCIAS = {"ter": 0.10, "aum": 0.15, "precio": 0.02, "posiciones": 0.05,
               "rentabilidad": 0.05, "valoracion": 0.10, "default": 0.15}


@dataclass
class Contradiccion:
    campo: str
    producto: str
    valor_a: Any
    fuente_a: str
    valor_b: Any
    fuente_b: str
    ganador: str          # id de fuente que gana por jerarquía
    fecha: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def prioridad(fuente: str) -> int:
    return PRIORIDAD.get(fuente, len(JERARQUIA_FUENTES))


def resolver(dato_a: Optional[Dato], dato_b: Optional[Dato], campo: str,
             producto: str, hoy: Optional[date] = None,
             ruta_contras: Optional[str] = None) -> Dato:
    """Cruza dos observaciones del mismo campo (regla 74).

    Gana la fuente de mayor jerarquía; si la de menor prioridad difiere beyond
    tolerancia se registra contradicción (a curated/contradictions.json + logs).
    `ruta_contras` permite a los tests redirigir el registro.
    """
    hoy = hoy or date.today()
    if dato_a is None and dato_b is None:
        return Dato.no_disponible("Sin fuentes para '%s'" % campo)
    if dato_b is None:
        return dato_a
    if dato_a is None:
        return dato_b

    pa, pb = prioridad(dato_a.fuente), prioridad(dato_b.fuente)
    ganador, perdedor = (dato_a, dato_b) if pa <= pb else (dato_b, dato_a)
    resultado = Dato(valor=ganador.valor, etiqueta=ganador.etiqueta,
                     fuente=ganador.fuente, fecha=ganador.fecha or hoy,
                     nota=ganador.nota)

    try:
        va, vb = float(dato_a.valor), float(dato_b.valor)
        tol = TOLERANCIAS.get(campo, TOLERANCIAS["default"])
        if abs(va - vb) > tol * max(abs(va), abs(vb), 1e-9):
            _registrar_contradiccion(Contradiccion(
                campo=campo, producto=producto,
                valor_a=dato_a.valor, fuente_a=dato_a.fuente,
                valor_b=dato_b.valor, fuente_b=dato_b.fuente,
                ganador=ganador.fuente, fecha=hoy.isoformat()),
                ruta=ruta_contras or FICHERO_CONTRAS)
            # Regla 77: el conflicto no verificado degrada la confianza del dato
            # (se queda con la etiqueta MÁS DÉBIL entre la original y ESTIMADO).
            resultado.etiqueta = min(resultado.etiqueta, DataLabel.ESTIMADO,
                                     key=_peso_etiqueta)
    except (TypeError, ValueError):
        pass  # datos no numéricos: gana la jerarquía sin tolerancia
    return resultado


def _peso_etiqueta(e: str) -> float:
    return DataLabel.PESO.get(e, 0.0)


def _registrar_contradiccion(c: Contradiccion, ruta: str = FICHERO_CONTRAS) -> None:
    """Añade a curated/contradictions.json (crea estructura si no existe)."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    data: Dict[str, Any] = {"$comment": "Contradicciones entre fuentes (regla 74). "
                                        "Generado por el motor; revisable a mano.",
                            "entradas": []}
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    entradas = data.setdefault("entradas", [])
    if not any(e.get("campo") == c.campo and e.get("producto") == c.producto
               and e.get("valor_a") == c.valor_a and e.get("valor_b") == c.valor_b
               for e in entradas):
        entradas.append(c.to_dict())
        data["$actualizado"] = date.today().isoformat()
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
