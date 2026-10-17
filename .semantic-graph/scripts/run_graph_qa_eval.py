#!/usr/bin/env python3
"""Regresión QA del grafo — patrón fukura (banco en curated/graph-qa-eval.json).

Cada caso: la clave esperada debe aparecer en el subgrafo recuperado.
PASS/FAIL + resumen; exit 1 si hay fallos (usable como gate de CI).

  python3 .semantic-graph/scripts/run_graph_qa_eval.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subgraph_retriever import recuperar  # noqa: E402

SG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(SG, "curated", "graph-qa-eval.json")


def main() -> int:
    with open(EVAL, encoding="utf-8") as f:
        banco = json.load(f)
    fallos = 0
    for caso in banco["casos"]:
        salida = recuperar(caso["pregunta"], estrategia=caso.get("estrategia", "hybrid"))
        ok = caso["clave_esperada"] in salida
        print("%s %s — %s" % ("✅ PASS" if ok else "❌ FAIL", caso["id"], caso["pregunta"]))
        if not ok:
            fallos += 1
            print("   clave esperada: %s" % caso["clave_esperada"])
    print("\n%d/%d casos PASS" % (len(banco["casos"]) - fallos, len(banco["casos"])))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
