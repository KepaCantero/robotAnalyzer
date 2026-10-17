---
type: 'adr'
graph_id: 'adr:007-suite-agentes-analisis'
generated: true
generated_at: '2026-10-14'
---

# ADR-007: Skills de análisis sobre el grafo (patrón fukura adaptado)

- estado: aceptado
- decision: El ciclo ask→define→verify→implement→sync de fukura se adapta a las fases del análisis: consultar grafo → interpretar/descubrir → analizar+red team → publicar en bóveda → regenerar grafo. Subagentes en .zcode/agents/.
- motivo: Regla 134 (modo actualización) equivale a sync-kg; regla 105 (seguimiento) equivale a la comparación de versiones del grafo. El patrón encaja 1:1.
- alternativas: 

## Relaciones
- PART_OF → [[method-metodologia-156-reglas]]
