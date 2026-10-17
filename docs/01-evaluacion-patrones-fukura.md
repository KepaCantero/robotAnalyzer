# Evaluación de patrones fukura para el analizador

Fecha: 2026-10-14. Contexto: el usuario pidió estructurar el analizador siguiendo
los patrones de su workspace `~/fukura` (knowledge graph + Obsidian + suite de
agentes) *si ayudan* — evaluación honesta, no replicación ciega. Fukura es un
workspace multi-repo de trabajo en equipo (Jira/Confluence, dashboards Appfire);
el analizador es un producto individual de análisis de inversión. Lo que sirve
en uno no tiene por qué servir en el otro.

## Resumen ejecutivo

5 patrones adoptados (algunos adaptados), 2 rechazados, 1 adoptado solo como
principio. Los ADRs del grafo (`adr:001`–`adr:007`) registran cada decisión con
alternativas y consecuencias.

## Adopciones

### 1. Knowledge graph (server-memory + memory.json) — ADR-001 ✅
Fukura lo usa para centralizar tickets/dominios/contradicciones desde Jira y
Confluence. El analizador lo usa para lo que sus reglas ya exigían sin saberlo:
- **Regla 105** (seguimiento): comparar ranking anterior vs actual exige memoria
  persistente de análisis y productos.
- **Regla 137** (API/automatización): conservar versiones del ranking.
- **Regla 74** (validación cruzada): las contradicciones entre fuentes son
  entidades de primera clase en fukura — aquí son exactamente TER distinto en
  emisor vs agregador.
Reutilización directa: formato JSONL de `@modelcontextprotocol/server-memory`
servido como MCP `knowledge-graph` (cero código: config en `.mcp.json`).

### 2. Capa curated (editar JSON, nunca el grafo) — ADR-001 ✅
Los pesos de scoring (reglas 58-62), la política de TTL (regla 72), la taxonomía
de categorías (regla 9), la jerarquía de fuentes (regla 73) y la semilla de
productos viven en `.semantic-graph/curated/*.json`. El pipeline los valida
(gates G1-G4) antes de publicar.

### 3. Metabolismo de memoria (TTL/decay/consolidación) — ADR-003 ✅
Encaje directo con la regla 72 ("nunca presentar datos antiguos como actuales"):
TTL por tipo de dato (precio 1d, AUM 7d, TER 30d…) con degradación de etiqueta
de calidad al caducar. En fukura esto evita conclusions con issues viejos; aquí
evita recomendar con un AUM de hace un mes.

### 4. Bóveda Obsidian como proyección read-only — ADR-002 ✅ (con cambio de rol)
En fukura la bóveda es vista de navegación para el desarrollador. Aquí el lector
final es el inversor: `boveda/` es **el entregable navegable** (temas, productos,
análisis, fuentes, metodología/ADRs, contradicciones), regenerada por el pipeline
con la misma disciplina (`generated: true`, frontmatter `graph_id` como join key).

### 5. QA eval del grafo — ✅
`run_graph_qa_eval.py` con banco en `curated/graph-qa-eval.json` (5/5 PASS).
Es la automatización del "control final" (regla 144) sobre la base de
conocimiento, no sobre un análisis concreto.

### 6. Suite de skills sobre el grafo — ADR-007 ⚠️ adoptada la IDEA, no la lista
La cadena fukura (ask-kg → define-with-kg → verify-with-kg → implement-with-kg →
sync-kg → evolve-with-kg) es dev-céntrica (tickets → PR). El análogo del
analizador son las fases de su propia metodología: consultar grafo (regla 105) →
interpretar/descubrir (reglas 2-11) → analizar + red team (17-54, 118-119) →
publicar bóveda → regenerar grafo. Se materializa como subagentes
`.zcode/agents/` (analista-fondos, descubridor-universo, red-team-inversiones) y
como prompts por fase en `src/analizador/agents/prompts/`.

## Rechazos

### 7. agent-hud / Agent Control Center — ADR-004 ❌
HUD HTTP en localhost:7600 con decisiones y pasos para coordinar trabajo humano
multi-repo. Para un producto de una persona es complejidad sin beneficio.
Revisión: si hay operación multiusuario.

### 8. kg_sync externo por agentes (Jira/Confluence con TTL) — ADR-005 ❌
Las "fuentes externas" del analizador no son documentos que ingerir y re-sincronizar:
son APIs de mercado consultadas **en el momento del análisis**. La frescura la
garantiza la capa de datos en runtime (etiquetas + TTL del metabolism-policy),
no re-sincronizaciones nocturnas de agente. Lo que sí se adopta del patrón: el
TTL como concepto y el estado de última ejecución.

## No adoptado explícitamente pero heredado

- `.memory/` con notas operativas (pequeño, una nota).
- Convención "nunca commit/push sin petición explícita".
- Disciplina de documentar decisiones como ADRs dentro del propio grafo.
