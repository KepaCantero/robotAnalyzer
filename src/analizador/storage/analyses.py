"""Almacén de análisis versionados — reglas 105, 122, 134, 137.

Cada análisis se guarda con fecha de corte (regla 122) y se conservan TODAS las
versiones del ranking (regla 137). El seguimiento (regla 105) compara el ranking
anterior con el actual e informa de subidas/bajadas/entradas/salidas.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from analizador.scoring.top5 import diferencia_rankings

SLUG_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789-"


def _slug(tema: str) -> str:
    s = tema.lower().strip().replace(" ", "-").replace("_", "-")
    return "".join(c for c in s if c in SLUG_CHARS)[:60] or "tema"


class AlmacenAnalisis:
    def __init__(self, directorio: str):
        self.dir = directorio
        os.makedirs(directorio, exist_ok=True)

    def guardar(self, analisis_dict: Dict, tema: Optional[str] = None) -> str:
        """Guarda una versión; devuelve el identificador."""
        tema = tema or analisis_dict.get("tema", "tema")
        slug = _slug(tema)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        iden = "%s_%s" % (slug, ts)
        ruta = os.path.join(self.dir, iden + ".json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(analisis_dict, f, ensure_ascii=False, indent=2)
        return iden

    def listar(self, tema: Optional[str] = None) -> List[Dict]:
        prefijo = (_slug(tema) + "_") if tema else ""
        out = []
        for nombre in sorted(os.listdir(self.dir)):
            if nombre.startswith(prefijo) and nombre.endswith(".json"):
                with open(os.path.join(self.dir, nombre), encoding="utf-8") as f:
                    d = json.load(f)
                d["_id"] = nombre[:-5]
                out.append(d)
        return out

    def ultimo(self, tema: str) -> Optional[Dict]:
        todos = self.listar(tema)
        return todos[-1] if todos else None

    def obtener(self, iden: str) -> Optional[Dict]:
        ruta = os.path.join(self.dir, iden + ".json")
        if not os.path.exists(ruta):
            return None
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def nombres_top5(analisis_dict: Dict) -> List[str]:
        return [a["producto"]["nombre"] for a in analisis_dict.get("top5", [])]

    def seguimiento(self, analisis_actual: Dict) -> List[str]:
        """Regla 105: comparar con el análisis anterior de la misma temática.

        El análisis actual aún no está guardado al invocar esto, así que todo
        lo almacenado es histórico — vale incluso si es del mismo día.
        """
        previo = None
        for a in self.listar(analisis_actual.get("tema", "")):
            previo = a   # el último almacenado
        if previo is None:
            return ["Primer análisis registrado de esta temática (regla 105): sin histórico que comparar."]
        return diferencia_rankings(self.nombres_top5(previo), self.nombres_top5(analisis_actual))
