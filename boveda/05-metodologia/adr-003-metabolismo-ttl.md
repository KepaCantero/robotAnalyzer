---
type: 'adr'
graph_id: 'adr:003-metabolismo-ttl'
generated: true
generated_at: '2026-10-14'
---

# ADR-003: Metabolismo de datos (TTL/decay)

- estado: aceptado
- decision: TTL por tipo de dato (precio 1d, AUM 7d, TER 30d…) con degradación de etiqueta al caducar.
- motivo: Regla 72: 'nunca presentar datos antiguos como actuales'. El metabolism fukura implementa la caducidad de forma mecánica, no discutible.
- alternativas: Datos inmortales.

## Relaciones
- PART_OF → [[method-metodologia-156-reglas]]
