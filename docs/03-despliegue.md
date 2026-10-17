# Despliegue a producción

## Requisitos

- python3 ≥ 3.9 (núcleo stdlib). Para la API: ≥ 3.9 + extras.
- Node/npx solo si se quiere el MCP `knowledge-graph` en un cliente MCP.
- Opcional: Docker (API + Firecrawl self-host), yfinance, clave LLM.

## Configuración

```bash
cp .env.example .env
# rellenar: ANALIZADOR_LLM_* (sin esto, modo determinista declarado)
# opcional: FIRECRAWL_BASE_URL / FIRECRAWL_API_KEY (si no, Jina Reader gratis)
```

## Opción A — CLI en local (ya funciona hoy)

```bash
PYTHONPATH=src python3 -m analizador.cli analizar "minería de cobre" \
    --perfil perfiles/perfil-ejemplo.json --cartera perfiles/cartera-ejemplo.json
```

## Opción B — API REST (Docker)

```bash
docker compose -f docker/docker-compose.yml up --build -d
# health: curl localhost:8000/health
# analizar: curl -X POST localhost:8000/analizar \
#   -H 'content-type: application/json' \
#   -d '{"tema":"minería de cobre","formato":"markdown"}'
```

El compose monta `.semantic-graph/`, `boveda/` y `datos/` como volúmenes: la
memoria del sistema es un artefacto vivo fuera de la imagen.

## Opción C — Firecrawl self-host (web→API gratuito e ilimitado en local)

```bash
docker run -d --name firecrawl -p 3002:3002 firecrawl/firecrawl
echo 'FIRECRAWL_BASE_URL=http://localhost:3002' >> .env
```

Con esto, `leer_web` / `ficha_emisor` usan tu instancia (sin créditos cloud);
sin esto, degradan automáticamente a Jina Reader (gratis, rate-limited).

## Agentes + MCPs en ZCode

- `.mcp.json` del proyecto ya registra `knowledge-graph` y `analizador-datos`.
- Subagentes en `.zcode/agents/`: `analista-fondos` (pipeline completo),
  `descubridor-universo` (reglas 8-11), `red-team-inversiones` (118-119).
- En una sesión ZCode dentro del proyecto: "analiza la minería de cobre con el
  analista" dispara el subagente con tools MCP + CLI + grafo.

## CI (GitHub Actions)

`.github/workflows/ci.yml` — tres jobs:
1. **tests**: unittest en python 3.9 y 3.12, sin red.
2. **grafo**: gates del pipeline + regresión QA + idempotencia del regenerado.
3. **api-build**: build de la imagen Docker.

## Seguridad y disciplina de producción

- Credenciales SOLO en `.env` (fuera de git). La API no expone claves (regla 137).
- Los datos personales (perfil/cartera reales) en `perfiles/*-real.json` (ignorados).
- Regla 101 en producción: cualquier dato sin fuente devuelve NO_DISPONIBLE —
  vigilar en logs que nadie "complete" huecos a mano.
