# Notas operativas del analizador

Memoria del proyecto (patrón fukura `.memory/`): cómo se trabaja aquí, decisiones
de operación que no viven en el código.

## Ciclo de trabajo vigente

1. Análisis nuevo → CLI `analizar` → revisar bloque "Control final del TOP 5".
2. Publicar → `python3 .semantic-graph/pipeline.py` (grafo + bóveda + CLAUDE.md).
3. Cierre de sesión → `run_graph_qa_eval.py` en verde antes de dar por bueno el día.

## Lecciones (añadir con fecha)

- 2026-10-14: las gates del pipeline cazaron 3 bugs reales en el primer arranque
  (slugs con tildes, categorías `_` vs `-`, pesos vacíos que sumaban 0). Las gates
  no son decoración: fallan el sync y evitan publicar grafo roto.
- 2026-10-14: el modo determinista deja los scores ~40-50 y confianza ~0-7 con la
  semilla actual. ES CORRECTO: casi todo el universo semilla tiene TER/AUM sin
  verificar. No "arreglar" la confianza con datos inventados (regla 101).
- 2026-10-14: verificado el handshake MCP real (initialize → tools/call) contra
  `analizador-datos`, incluida una cotización en vivo de IWDA.AS (131.81 USD,
  VERIFICADO, 2026-10-14). Yahoo responde sin clave desde esta máquina.

## Pendiente de decisión del usuario

- API real de LLM (`.env`) — sin ella, análisis deterministas únicamente.
- Broker del perfil (regla 71): accesibilidad queda "pendiente" hasta conocerlo.
- Si incorporar Morningstar/justETF (necesitan clave) al registro de fuentes.
