---
type: 'adr'
graph_id: 'adr:006-scoring-determinista'
generated: true
generated_at: '2026-10-14'
---

# ADR-006: El score lo calcula código, no el LLM

- estado: aceptado
- decision: Los agentes aportan factores 0-100 con métricas de origen; pesos, doble conteo, penalizaciones, confianza y TOP 5 los aplica el motor determinista.
- motivo: Regla 144 (control final auditable) y regla 137 (API/automatización): la reproducibilidad exige que el mismo input dé el mismo score. Un LLM no garantiza eso; el sí lo hace.
- alternativas: 

## Relaciones
- PART_OF → [[method-metodologia-156-reglas]]
