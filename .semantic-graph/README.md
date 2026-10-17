# .semantic-graph — maquinaria del knowledge graph del analizador

Patrón fukura adaptado al dominio de inversión (ADR-001). Fuente de verdad del
conocimiento centralizado: `memory.json` (JSONL, formato
`@modelcontextprotocol/server-memory`), servido como MCP `knowledge-graph`
(config en `.mcp.json` del proyecto). La bóveda `../boveda/` es una proyección.

## Uso diario

```bash
# regenerar grafo + bóveda + CLAUDE.md tras editar curated/*.json (~1 s)
python3 .semantic-graph/pipeline.py

# recuperar subgrafo para una pregunta (ask-kg adaptado)
python3 .semantic-graph/scripts/subgraph_retriever.py "¿qué ADR rechaza agent-hud?"
PYTHONPATH=src python3 -m analizador.cli grafo "cobre"   # atajo

# regresión QA del grafo (gate de CI)
python3 .semantic-graph/scripts/run_graph_qa_eval.py

# regenerar desde cero (ignora observaciones manual: conservadas)
python3 .semantic-graph/pipeline.py --from-scratch
```

## Mapa de ficheros

| Fichero | Qué es |
|---|---|
| `pipeline.py` | fuentes → IR → memory.json + bóveda + gates + reporte + CLAUDE.md |
| `curated/*.json` | **la capa editable a mano** — nunca tocar memory.json |
| `memory.json` | el grafo (generado; las observaciones `manual:*` sobreviven) |
| `ir.json` | IR intermedio (debug) |
| `logs/sync-report.md` | gates y conteos del último sync |

## Curated (qué tocar para qué)

| Fichero | Para qué |
|---|---|
| `ontology.json` | temas, categorías (regla 9), jerarquía de fuentes (regla 73), ADRs, metodología |
| `scoring-weights.json` | pesos base + adaptativos por naturaleza (reglas 58-62) y penalizaciones |
| `metabolism-policy.json` | TTL por tipo de dato, decay de etiquetas (reglas 72, 77) |
| `seed-productos.json` | universo semilla (ISIN solo si verificado — regla 101) |
| `contradictions.json` | discrepancias entre fuentes (regla 74; generado por el motor, revisable) |
| `graph-qa-eval.json` | banco de regresión del grafo |

## Gates (fallan el sync y NO se publica)

- **G1** todo producto con ≥1 arista BELONGS_TO
- **G2** todo análisis con TOP 5 completo o excepción declarada (regla 7)
- **G3** pesos de scoring suman 1.00 ± 0.01 por bloque
- **G4** cero entidades huérfanas

## Plan B

Si `@modelcontextprotocol/server-memory` desaparece del registry npm: el
escritor está aislado en `escribir_memoria()` (emite JSONL entity/relation);
re-apuntar a un sucesor (p. ej. Basic Memory) exportando desde `ir.json`.
