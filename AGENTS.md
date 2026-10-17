# Analizador de fondos y ETFs — mapa y convenciones

Proyecto personal de Kepa Cantero: analista profesional de fondos, fondos
indexados y ETFs según la metodología de `ANALIZADOR DE FONDOS Y ETFS.docx`
(156 reglas), con arquitectura de agentes + knowledge graph + bóveda Obsidian.
Los patrones de fukura se evaluaron uno a uno: adoptados 5, rechazados 2 —
verdad completa en `docs/01-evaluacion-patrones-fukura.md` y ADRs del grafo.

## Reglas críticas (leer primero)

1. **La fuente maestra es el DOCX.** Ante duda metodológica: regla N del
   documento. Los prompts (`src/analizador/agents/prompts/`) son su destilado.
2. **Nunca inventar datos financieros** (regla 101). Todo dato crítico lleva
   etiqueta VERIFICADO/CALCULADO/ESTIMADO/INFERIDO/NO_DISPONIBLE (regla 75).
   Un ISIN no verificado va `null`, jamás "parecido".
3. **El score lo calcula el motor determinista, no el LLM** (ADR-006). Los
   agentes aportan factores; pesos/penalizaciones/TOP 5 son código auditable.
4. **Curated, nunca el grafo a mano**: editar `.semantic-graph/curated/*.json`
   y regenerar con `python3 .semantic-graph/pipeline.py`. Las observaciones
   `manual:*` del grafo sobreviven re-syncs.
5. **La bóveda `boveda/` es una proyección read-only**: notas `generated: true`
   no se editan; se corrige la fuente y se regenera.
6. **Sin commit/push sin petición explícita del usuario** (convención fukura).
7. **Comunicación en español** con el usuario (regla 99).

## Mapa

| Ruta | Qué es |
|---|---|
| `ANALIZADOR DE FONDOS Y ETFS.docx` | Metodología maestra (156 reglas) |
| `src/analizador/` | Motor Python (stdlib puro): dominio, scoring, pipeline, agentes, MCP, CLI |
| `src/analizador/agents/prompts/` | Prompts por agente destilados de las 156 reglas |
| `.semantic-graph/` | Knowledge graph (patrón fukura): curated + pipeline + retriever + QA eval |
| `boveda/` | Bóveda Obsidian regenerada (entregable navegable del inversor) |
| `.zcode/agents/` | Subagentes: analista-fondos, descubridor-universo, red-team-inversiones |
| `.mcp.json` | MCPs del proyecto: knowledge-graph (server-memory) + analizador-datos (propio) |
| `datos/analisis/` | Análisis versionados (JSON, regla 137) — generado |
| `dashboard/` | Dashboard Streamlit+VectorBT de backtesting (venv `.venv/` del proyecto; instalar según cabecera de `dashboard/app.py`) |
| `perfiles/` | Perfil de inversor y cartera (reglas 13-14) — los reales NO se commitean |
| `docs/` | Arquitectura, evaluación de patrones fukura, despliegue, roadmap |
| `tests/` | unittest stdlib: scoring, TOP 5, crossval, storage, pipeline offline |

## Comandos

```bash
# Análisis completo (determinista si no hay ANALIZADOR_LLM_* en .env)
PYTHONPATH=src python3 -m analizador.cli analizar "minería de cobre"
PYTHONPATH=src python3 -m analizador.cli analizar "inteligencia artificial" \
    --perfil perfiles/perfil-ejemplo.json --cartera perfiles/cartera-ejemplo.json

# Demo sin red
PYTHONPATH=src python3 -m analizador.cli demo

# Historial versionado (reglas 105/137)
PYTHONPATH=src python3 -m analizador.cli historial "cobre"

# Grafo
python3 .semantic-graph/pipeline.py                       # regenerar grafo+bóveda+CLAUDE.md
python3 .semantic-graph/scripts/run_graph_qa_eval.py      # regresión del grafo
PYTHONPATH=src python3 -m analizador.cli grafo "consulta" # subgrafo legible

# Tests (CI usa lo mismo)
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Grafo semántico + suite de agentes (patrón fukura adaptado, ADR-001/007)

- Fuente de verdad del conocimiento: `.semantic-graph/memory.json` (JSONL
  server-memory), servido como MCP `knowledge-graph` (`.mcp.json`). Entidades:
  `theme:*` `category:*` `product:*` `analysis:*` `source:*` `adr:*`
  `contradiction:*` `method:*`.
- Cadena adaptada de fukura: consultar grafo (ask) → interpretar/descubrir
  (define) → analizar + red team (verify) → publicar bóveda (implement) →
  regenerar grafo (sync). Equivale 1:1 a las reglas 134 (modo actualización)
  y 105 (seguimiento).
- Metabolismo de datos (ADR-003): TTL por tipo de dato en
  `curated/metabolism-policy.json` (regla 72); contradicciones entre fuentes
  (regla 74) caen en `curated/contradictions.json` y entran al grafo.
- Gates del pipeline: G1 productos con categoría, G2 TOP 5 completo o
  declarado, G3 pesos suman 1.00, G4 cero huérfanas. Rojo = no se publica.

## MCP tooling

- **knowledge-graph**: `@modelcontextprotocol/server-memory` (npx) sobre
  `memory.json` — `read_graph`, `search_nodes`, etc.
- **analizador-datos**: servidor propio stdlib (`python3 -m analizador.mcp.server`)
  con `buscar_productos`, `cotizacion`, `historico`, `puntuar`, `leer_web`,
  `consultar_grafo`. `leer_web` convierte cualquier web en markdown (Firecrawl
  self-host gratis o Jina Reader gratis sin clave) — leer la página del EMISOR
  da prioridad 1 (regla 73); yfinance (pip) hace robustas las cotizaciones si
  está presente. `historico` devuelve la serie de cierres con métricas
  CALCULADO (volatilidad anual, máximo drawdown, Sharpe, Sortino — regla 75)
  que alimentan el factor `volatilidad_drawdown` vía `scoring/metricas.py`
  (ids brutos, regla 63).
- **Cadena de fuentes de mercado** (`data/sources/mercado.py`): cotizaciones e
  históricos nunca dependen de un solo proveedor — Yahoo (v8 JSON) y Stooq
  (CSV diario sin clave, https://stooq.com/db/h/) en orden configurable con
  `ANALIZADOR_FUENTES_MERCADO` (defecto `yahoo,stooq`). Todo fallo degrada a
  NO_DISPONIBLE con traza de qué fuente se intentó (regla 101). Stooq filtra
  IPs de datacenter con reto JS: desde casa responde CSV; los nuevos
  adaptadores se añaden SOLO en mercado.py, el pipeline no se toca.
- Ambos requieren `npx` (Node) para el primero y `python3` para el segundo;
  config en `.mcp.json` (rutas absolutas de este proyecto).

## Modo de operación

- Sin `ANALIZADOR_LLM_API_KEY` todo el sistema corre DETERMINISTA (proveedor
  eco): el pipeline completo funciona, los factores de juicio son neutros y el
  informe lo declara — salvo `volatilidad_drawdown`, que si hay red se calcula
  desde cierres reales (CALCULADO, regla 75; `scoring/metricas.py`). Es la
  garantía de que nada "parece" análisis real sin serlo.
- Con LLM configurado: los agentes aportan los juicios; el motor sigue
  calculando scores. Revisar el bloque "Avisos del sistema" del informe.
- Datos de red vía la cadena Yahoo→Stooq sin clave (ver "Cadena de fuentes de
  mercado"); `ANALIZADOR_ALLOW_NETWORK=0` para offline.
