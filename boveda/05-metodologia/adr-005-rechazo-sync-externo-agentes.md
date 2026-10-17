---
type: 'adr'
graph_id: 'adr:005-rechazo-sync-externo-agentes'
generated: true
generated_at: '2026-10-14'
---

# ADR-005: RECHAZAR kg_sync externo por agentes

- estado: rechazado
- decision: No replicar la sync Jira/Confluence por scripts de agente con TTL.
- motivo: Las 'fuentes externas' del analizador son APIs de mercado consumidas en cada análisis, no documentos que ingerir.
- alternativas: Capa de datos en el motor (sources/registry.py + adaptador Yahoo) con caché y TTL del metabolism-policy: la frescura la garantiza código en runtime, no re-sincronizaciones de agente.

## Relaciones
- PART_OF → [[method-metodologia-156-reglas]]
