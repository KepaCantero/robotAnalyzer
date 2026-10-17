# Analizador de Fondos y ETFs

Analista profesional independiente de fondos, fondos indexados, ETFs, ETCs y
ETPs según la metodología de **156 reglas** de `ANALIZADOR DE FONDOS Y ETFS.docx`
(interpretación → tesis → universo → análisis → TOP 5 → recomendación →
seguimiento), construido con:

- **Motor de scoring determinista** (el score lo calcula código auditable, no
  el LLM — reglas 58-64, 79-80, 147).
- **Agentes LLM agnósticos** con prompts destilados regla a regla, y modo
  determinista offline que se declara a sí mismo (regla 101: nada inventado).
- **Knowledge graph + bóveda Obsidian** (patrones fukura evaluados y adaptados:
  ver `docs/01-evaluacion-patrones-fukura.md` y los ADRs del grafo).
- **2 MCPs**: `knowledge-graph` (server-memory) y `analizador-datos` (propio,
  stdlib): buscar_productos, cotizacion, puntuar, leer_web, consultar_grafo.
- **Web→API**: Firecrawl self-host (gratis) o Jina Reader (gratis, sin clave)
  convierten la web del emisor en fuente prioridad 1 (regla 73).
- **Cadena de fuentes de mercado**: Yahoo (v8) → Stooq (CSV sin clave) con
  degradación auditable — ningún dato depende de un solo proveedor (regla 101).

> **¿Nuevo aquí?** Empieza por [`docs/05-eli5.md`](docs/05-eli5.md) — el
> sistema explicado fácil en cinco ideas.

## Inicio rápido (0 dependencias)

```bash
# Demo determinista completa del ejemplo de la regla 3
PYTHONPATH=src python3 -m analizador.cli demo

# Análisis real de una temática (con perfil y cartera opcionales)
PYTHONPATH=src python3 -m analizador.cli analizar "minería de cobre" \
    --perfil perfiles/perfil-ejemplo.json --cartera perfiles/cartera-ejemplo.json

# Dashboard de backtesting (Streamlit + VectorBT) y su página de tests
source .venv/bin/activate && streamlit run dashboard/app.py
# La página "2_bateria_de_tests" del sidebar ejecuta: tests del motor (V1-V6),
# los 37 tests del analizador (156 reglas) y la validación ex-post de los
# análisis almacenados (retornos forward TOP 5 vs universo vs benchmark).

# Verificación del backtesting (niveles 1 y 2, ver dashboard/verificar_backtest.py)
.venv/bin/python dashboard/verificar_backtest.py

# Historial versionado (reglas 105/137)
PYTHONPATH=src python3 -m analizador.cli historial

# Tests
PYTHONPATH=src python3 -m unittest discover -s tests -t .
```

Sin `ANALIZADOR_LLM_API_KEY` el sistema corre en **modo determinista**: el
pipeline completo funciona pero los juicios de mercado quedan pendientes de LLM
— y el informe lo dice. Con LLM: los agentes aportan factores, el motor calcula.

## Mapa

| Ruta | Qué es |
|---|---|
| `src/analizador/` | Motor Python stdlib (dominio, scoring, pipeline, agentes, MCP, CLI, API opcional) |
| `dashboard/app.py` | Dashboard de backtesting Streamlit + VectorBT (venv propio, ver cabecera del archivo) |
| `.semantic-graph/` | Knowledge graph: curated editable + pipeline con gates + retriever + QA eval |
| `boveda/` | Bóveda Obsidian regenerada — el entregable navegable del inversor |
| `.zcode/agents/` | Subagentes: analista-fondos, descubridor-universo, red-team-inversiones |
| `.mcp.json` | MCPs del proyecto |
| `perfiles/` | Perfil de inversor y cartera (ejemplos; los reales no se commitean) |
| `docs/` | Arquitectura, evaluación de patrones fukura, despliegue, roadmap |
| `docker/` + `.github/` | API en contenedor y CI (tests + gates de grafo + build) |

## Documentación

- `docs/05-eli5.md` — **empieza aquí**: el sistema explicado fácil (cinco ideas)
- `docs/01-evaluacion-patrones-fukura.md` — qué se adoptó y qué se rechazó de fukura y por qué
- `docs/02-arquitectura.md` — módulos y decisiones estructurales
- `docs/03-despliegue.md` — CLI local, API Docker, Firecrawl self-host, MCPs en ZCode
- `docs/04-roadmap-produccion.md` — qué falta para producción, por fases
- `AGENTS.md` — convenciones para agentes que trabajen en este repo

## Aviso

Herramienta de investigación personal. No es asesoramiento financiero; la
propia metodología (regla 100) prohíbe presentar estimaciones como certezas.
