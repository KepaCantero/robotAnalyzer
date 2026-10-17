"""Base de agentes — proveedor LLM agnóstico.

Dos proveedores:
- ProveedorEco: determinista, sin red ni clave. Devuelve el payload de entrada
  como "borrador estructurado" para que el pipeline completo (scoring, TOP 5,
  reporte, grafo) sea ejecutable y testeable offline.
- ProveedorOpenAICompat: cualquier endpoint Chat Completions compatible
  (OpenAI, Groq, Ollama, vLLM…). Config por env (ver .env.example).

Regla 101 aplicada en el contrato: los agentes DEBEN devolver JSON con claves
"no_disponible" en lugar de inventar datos; _json() lo tolera.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Dict, Optional, Protocol


class ProveedorLLM(Protocol):
    def completar(self, system: str, user: str) -> str: ...


class ProveedorEco:
    """Modo determinista: devuelve un JSON mínimo que el pipeline completa."""

    def __init__(self, etiqueta: str = "proveedor-eco"):
        self.etiqueta = etiqueta

    def completar(self, system: str, user: str) -> str:
        return json.dumps({
            "modo": self.etiqueta,
            "aviso": ("Respuesta determinista sin LLM: completar con ProveedorOpenAICompat "
                      "para análisis reales (regla 144: calidad de datos)."),
            "entrada": user[:2000],
        }, ensure_ascii=False)


class ProveedorOpenAICompat:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, timeout_s: int = 90):
        self.base_url = (base_url or os.environ.get("ANALIZADOR_LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("ANALIZADOR_LLM_API_KEY", "")
        self.model = model or os.environ.get("ANALIZADOR_LLM_MODEL", "gpt-4o-mini")
        self.timeout_s = timeout_s

    @property
    def disponible(self) -> bool:
        return bool(self.base_url and self.api_key)

    def completar(self, system: str, user: str) -> str:
        if not self.disponible:
            raise RuntimeError("ProveedorOpenAICompat sin ANALIZADOR_LLM_BASE_URL/API_KEY")
        body = json.dumps({
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer %s" % self.api_key})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def proveedor_por_defecto() -> ProveedorLLM:
    p = ProveedorOpenAICompat()
    return p if p.disponible else ProveedorEco()


def extraer_json(texto: str) -> Optional[Dict[str, Any]]:
    """Extrae el primer objeto JSON de una respuesta (tolera ```json fences```)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    candidato = m.group(1) if m else None
    if candidato is None:
        ini = texto.find("{")
        fin = texto.rfind("}")
        if 0 <= ini < fin:
            candidato = texto[ini:fin + 1]
    if candidato is None:
        return None
    try:
        return json.loads(candidato)
    except json.JSONDecodeError:
        return None
