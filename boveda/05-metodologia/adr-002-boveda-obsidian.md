---
type: 'adr'
graph_id: 'adr:002-boveda-obsidian'
generated: true
generated_at: '2026-10-14'
---

# ADR-002: Bóveda Obsidian como entregable navegable

- estado: aceptado
- decision: Proyección read-only del grafo en boveda/ (una nota por entidad, frontmatter graph_id como join key, generated: true).
- motivo: Aquí el lector final es el inversor: la bóveda ES el producto de lectura. Patrón fukura de proyección regenerada evita divergencias.
- alternativas: Dashboard web (coste de desarrollo); solo PDFs (no navegable).

## Relaciones
- PART_OF → [[method-metodologia-156-reglas]]
