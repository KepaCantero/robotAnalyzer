"""API REST opcional — regla 137 (API/automatización).

Arranque (requiere extras): pip install -e ".[api]" && uvicorn analizador.api.app:app

Endpoints:
  POST /analizar        {tema, perfil?, cartera?}  → análisis completo (JSON)
  GET  /analises        ?tema=                     → historial versionado
  GET  /grafo           ?q=                        → subgrafo
  GET  /health          → estado + modo (determinista/LLM)

Regla 137 aplicada: nunca exponer credenciales, mantener timestamps, conservar
fuentes y versiones del ranking (el almacén ya lo hace).
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
if RAIZ not in sys.path:
    sys.path.insert(0, os.path.join(RAIZ, "src"))

from typing import Any, Dict, Optional  # noqa: E402

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from analizador.agents.base import ProveedorOpenAICompat, proveedor_por_defecto  # noqa: E402
from analizador.domain.models import Cartera, PerfilInversor, Posicion  # noqa: E402
from analizador.pipeline.orquestador import OrquestadorAnalisis  # noqa: E402
from analizador.pipeline.reportero import render  # noqa: E402
from analizador.storage.analyses import AlmacenAnalisis  # noqa: E402

app = FastAPI(
    title="Analizador de Fondos y ETFs",
    version="0.1.0",
    description="Metodología de 156 reglas; motor determinista + agentes LLM.")

ALMACEN = AlmacenAnalisis(os.environ.get("ANALIZADOR_DATA_DIR",
                                         os.path.join(RAIZ, "datos", "analisis")))


class PeticionAnalisis(BaseModel):
    tema: str
    perfil: dict | None = None
    cartera: dict | None = None
    formato: str = "json"          # json | markdown


@app.get("/health")
def health():
    p = ProveedorOpenAICompat()
    return {"estado": "ok",
            "modo": "llm" if p.disponible else "determinista",
            "modelo": p.model if p.disponible else "proveedor-eco"}


@app.post("/analizar")
def analizar(peticion: PeticionAnalisis):
    if not peticion.tema.strip():
        raise HTTPException(422, "tema requerido")
    perfil = PerfilInversor.from_dict(peticion.perfil) if peticion.perfil else None
    cartera = None
    if peticion.cartera:
        cartera = Cartera(posiciones=[Posicion(**p)
                                      for p in peticion.cartera.get("posiciones", [])])
    orq = OrquestadorAnalisis(almacen=ALMACEN)
    resultado = orq.analizar_tematica(peticion.tema, perfil=perfil, cartera=cartera)
    dict_final = resultado.to_dict()
    dict_final["avisos"] = orq.avisos
    if peticion.formato == "markdown":
        return {"informe_markdown": render(resultado, dict_final), **dict_final}
    return dict_final


@app.get("/analises")
def listar(tema: Optional[str] = None):
    return {"analisis": ALMACEN.listar(tema)}


@app.get("/grafo")
def grafo(q: str, estrategia: str = "hybrid"):
    sys.path.insert(0, os.path.join(RAIZ, ".semantic-graph", "scripts"))
    from subgraph_retriever import recuperar
    return {"texto": recuperar(q, estrategia=estrategia)}
