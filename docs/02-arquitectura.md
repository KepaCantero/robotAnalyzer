# Arquitectura del analizador

## Visión general

```
                 ┌────────────────────────────────────────────────┐
                 │  Metodología maestra: ANALIZADOR … ETFS.docx    │
                 │  (156 reglas — fuente de verdad)                │
                 └───────────────┬────────────────────────────────┘
                                 │ destilada en prompts por agente
   tema + perfil ──▶ ┌───────────▼───────────┐
                     │  ORQUESTADOR (regla 2)│  INPUT→INTERPRETACIÓN→TESIS→UNIVERSO
                     │  src/analizador/       │  →FILTRADO→ANÁLISIS→PUNTUACIÓN→TOP 5
                     │  pipeline/             │  →RECOMENDACIÓN→SEGUIMIENTO
                     └───┬──────────┬────────┘
          juicios LLM    │          │  determinismo
      ┌──────────────────▼──┐   ┌───▼──────────────────────────┐
      │ AGENTES             │   │ MOTOR (scoring/)             │
      │ intérprete          │   │ pesos (58-62) · doble conteo │
      │ descubridor         │   │ (63) · penalizaciones (77,92)│
      │ analista            │──▶│ confianza (76) · TOP 5 (147) │
      │ red team            │   │ robustez (116)               │
      └─────────────────────┘   └──────────┬───────────────────┘
                                            │ AnalisisCompleto (JSON)
      ┌─────────────────────────────────────▼──────────────────────┐
      │ SALIDAS                                                      │
      │ • informe markdown (regla 155)  • datos/analisis/*.json      │
      │ • knowledge graph (.semantic-graph)  • bóveda Obsidian       │
      └─────────────────────────────────────────────────────────────┘

   DATOS: sources/registry.py (jerarquía 73 + crossval 74 + calidad 75)
          sources/yahoo.py · sources/web2api.py (Firecrawl/Jina → any web)
          MCP analizador-datos (buscar, cotización, puntuar, leer_web, grafo)
          MCP knowledge-graph (server-memory sobre memory.json)
```

## Decisiones estructurales

1. **El score es código, no prompt** (ADR-006). Regla 144 exige control final
   auditable y regla 137 reproducibilidad: mismo input → mismo score. Los LLM
   aportan factores 0-100 con métricas de origen; el motor hace el resto.
2. **Modo determinista por defecto** (ProveedorEco): sin clave LLM todo el
   pipeline corre y produce un informe *que se declara a sí mismo* como juicio
   de proceso, no de mercado. Ante la regla 101 (no inventar), el sistema
   prefiere decir "no disponible" antes que parecer inteligente.
3. **Curated sobre generado** (patrón fukura): pesos, TTL, ontología y semilla
   son ficheros JSON editables; grafo y bóveda son proyecciones regenerables
   con gates que impiden publicar inconsistencias.
4. **Web → API** (`sources/web2api.py`): Firecrawl self-host (gratis, Docker) o
   Jina Reader (gratis, sin clave) convierten la web del EMISOR en fuente
   prioridad 1 de la regla 73 — el hueco que ninguna API gratuita cubre.
5. **stdlib puro en el núcleo**: motor, grafo, MCP y CLI corren con python3
   pelado (3.9+). FastAPI/yfinance son extras opcionales.

## Módulos

| Módulo | Responsabilidad | Reglas clave |
|---|---|---|
| `domain/models.py` | Producto, Dato, Tesis, Scores, Perfil, Cartera, Análisis | 5-6, 9, 13-14, 17-19, 41-42, 75-76, 86-87 |
| `scoring/engine.py` | pesos adaptativos, doble conteo, confianza, penalizaciones | 58-64, 76-78 |
| `scoring/top5.py` | TOP 5 obligatorio, control final, robustez, seguimiento | 7-8, 79-80, 116, 147 |
| `data/sources/registry.py` | jerarquía de fuentes, crossval, contradicciones | 73-74, 77 |
| `data/sources/yahoo.py` / `web2api.py` | cotizaciones; any-web→markdown | 72, 75, 101 |
| `agents/` | proveedor LLM agnóstico + 4 agentes + prompts | 1-4, 8-11, 17-54, 118-119 |
| `pipeline/orquestador.py` | proceso completo end-to-end | 2, 105, 137 |
| `pipeline/reportero.py` | informe estándar render determinista | 98-100, 122-129, 155 |
| `storage/analyses.py` | análisis versionados + seguimiento | 105, 122, 137 |
| `mcp/server.py` | MCP propio (stdio JSON-RPC) | 8, 58-60, 72, 75 |
| `.semantic-graph/` | grafo + curated + gates + retriever + QA | 72-74, 105, 137 |
| `boveda/` | proyección Obsidian del grafo | — |

## Ciclo de vida de un análisis

1. `analizador analizar "<tema>" [--perfil …]` → orquestador.
2. Cada agente devuelve JSON; el motor calcula; el top5 valida.
3. Informe markdown por stdout + JSON versionado en `datos/analisis/`.
4. `python3 .semantic-graph/pipeline.py` → grafo + bóveda + CLAUDE.md.
5. Siguiente análisis del mismo tema: el seguimiento (regla 105) diff-ea el
   TOP 5 contra el histórico automáticamente.
