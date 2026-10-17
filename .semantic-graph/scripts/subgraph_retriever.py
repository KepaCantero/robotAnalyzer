#!/usr/bin/env python3
"""Recuperación de subgrafo — patrón fukura (keyword / bfs / hybrid).

Uso:
  python3 .semantic-graph/scripts/subgraph_retriever.py "¿qué ADR rechaza agent-hud?" \
      [--estrategia keyword|bfs|hybrid] [--profundidad 2] [--limite 12]

Devuelve texto legible con entidades y aristas relevantes — el contexto que un
agente necesita antes de analizar (adaptación del skill ask-kg de fukura).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata

SG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORIA = os.path.join(SG, "memory.json")

PALABRAS_VACIAS = {"que", "cual", "cuales", "como", "donde", "qué", "cuál",
                   "cuáles", "cómo", "dónde", "los", "las", "el", "la", "de",
                   "del", "y", "o", "a", "en", "es", "son", "por", "para",
                   "con", "un", "una", "hay"}


def _norm(texto):
    n = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in n if not unicodedata.combining(c))


def cargar():
    entidades, relaciones = {}, []
    with open(MEMORIA, encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            o = json.loads(linea)
            if o["type"] == "entity":
                entidades[o["name"]] = o
            else:
                relaciones.append(o)
    return entidades, relaciones


def _keywords(pregunta):
    tokens = re.findall(r"[a-zA-Z0-9áéíóúñÁÉÍÓÚÑ:-]+", _norm(pregunta))
    return [t for t in tokens if t not in PALABRAS_VACIAS and len(t) > 2]


def estrategia_keyword(pregunta, entidades, relaciones, limite):
    kws = _keywords(pregunta)
    hits = []
    for nombre, e in entidades.items():
        blob = _norm(nombre + " " + " ".join(e.get("observations", [])))
        puntuacion = sum(1 for k in kws if k in blob)
        if puntuacion:
            hits.append((puntuacion, nombre))
    hits.sort(reverse=True)
    return [nombre for _, nombre in hits[:limite]]


def estrategia_bfs(pregunta, entidades, relaciones, limite, profundidad=2):
    semillas = estrategia_keyword(pregunta, entidades, relaciones, 3)
    adyacencia = {}
    for r in relaciones:
        adyacencia.setdefault(r["from"], []).append(r["to"])
        adyacencia.setdefault(r["to"], []).append(r["from"])
    visitados, frontera = list(semillas), list(semillas)
    for _ in range(profundidad):
        nueva = []
        for nodo in frontera:
            for vecino in adyacencia.get(nodo, []):
                if vecino not in visitados:
                    visitados.append(vecino)
                    nueva.append(vecino)
        frontera = nueva
        if len(visitados) >= limite:
            break
    return visitados[:limite]


def recuperar(pregunta, estrategia="hybrid", limite=12, profundidad=2):
    entidades, relaciones = cargar()
    if estrategia == "keyword":
        nombres = estrategia_keyword(pregunta, entidades, relaciones, limite)
    elif estrategia == "bfs":
        nombres = estrategia_bfs(pregunta, entidades, relaciones, limite, profundidad)
    else:  # hybrid: keyword ∪ bfs-1-salto de las 3 mejores semillas
        kw = estrategia_keyword(pregunta, entidades, relaciones, limite // 2)
        bf = estrategia_bfs(pregunta, entidades, relaciones, limite, profundidad=1)
        nombres = list(dict.fromkeys(kw + bf))[:limite]

    incluidos = set(nombres)
    lineas = ["Subgrafo para: '%s' (estrategia %s, %d entidades)" % (
        pregunta, estrategia, len(nombres)), ""]
    for nombre in nombres:
        e = entidades[nombre]
        lineas.append("■ %s [%s]" % (nombre, e["entityType"]))
        for o in e.get("observations", []):
            lineas.append("   · %s" % o)
    lineas.append("")
    lineas.append("Aristas internas:")
    for r in relaciones:
        if r["from"] in incluidos and r["to"] in incluidos:
            lineas.append("   %s —%s→ %s" % (r["from"], r["relationType"], r["to"]))
    return "\n".join(lineas)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("pregunta")
    p.add_argument("--estrategia", default="hybrid",
                   choices=["keyword", "bfs", "hybrid"])
    p.add_argument("--profundidad", type=int, default=2)
    p.add_argument("--limite", type=int, default=12)
    a = p.parse_args()
    print(recuperar(a.pregunta, a.estrategia, a.limite, a.profundidad))


if __name__ == "__main__":
    sys.exit(main())
