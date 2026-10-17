---
type: 'adr'
graph_id: 'adr:001-knowledge-graph'
generated: true
generated_at: '2026-10-14'
---

# ADR-001: Adoptar knowledge graph (patrón fukura)

- estado: aceptado
- decision: Grafo JSONL formato server-memory (@modelcontextprotocol/server-memory) servido como MCP knowledge-graph, con curated/*.json como capa editable y memory.json generado.
- motivo: Reglas 105/137: el seguimiento necesita memoria de rankings anteriores y productos descubiertos. El grafo fukura resuelve exactamente persistencia + consulta semántica con coste cero de infraestructura.
- alternativas: Sin grafo (análisis aislados); base de datos relacional (peso innecesario para conocimiento narrativo).

## Relaciones
- PART_OF → [[method-metodologia-156-reglas]]
