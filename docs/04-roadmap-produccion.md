# Roadmap a producción

Qué falta, por orden de valor, para pasar de la base actual (funcionando en
modo determinista con infraestructura completa) a producto de producción.

## Fase 1 — Datos reales (lo que más limita el valor hoy)

- [ ] **Verificar ISINs del universo semilla** (regla 101): los marcados
      `isin_verificado: false` van a null a propósito. Con `leer_web` +
      ficha_emisor se pueden verificar y fijar en curated.
- [ ] Levantar **Firecrawl self-host** (docker) para leer emisor/justETF sin
      rate limit, y extraer TER/AUM/holdings estructurados (schema de Firecrawl).
- [ ] `pip install yfinance` para cotizaciones robustas (el adaptador ya lo
      usa si está presente).
- [ ] Adaptadores específicos: Morningstar (requiere clave), CNMV/DEFI
      (fondo traspasable ES — clave para la regla 29).

## Fase 2 — LLM real

- [ ] Configurar `ANALIZADOR_LLM_*` (cualquier endpoint OpenAI-compatible:
      OpenAI, Groq, Ollama local…).
- [ ] Calibrar los prompts de `agents/prompts/` con 3-5 temáticas de prueba;
      revisar que los factores llegan con métricas y sin dobles.
- [ ] Evaluar la salida contra el checklist de la regla 144 (ampliar
      `graph-qa-eval.json` con casos de metodología, no solo de grafo).

## Fase 3 — Operación

- [ ] API en Docker con autenticación (hoy sin auth: uso personal/local).
- [ ] Cronograma de re-análisis (regla 151: actualización mínima precio/
      valoración/AUM/riesgos) — CronCreate del entorno o systemd timer.
- [ ] Alertas (regla 106): qué vigilar por producto ya se genera; falta el
      canal de aviso (email/telegram) cuando un invalidador se activa.

## Fase 4 — Profundidad metodológica

- [ ] Modo comparación (regla 130) y modo DCA (regla 133) como comandos CLI
      propios (hoy el orquestador cubre descubrimiento/actualización).
- [ ] Overlap de cartera (regla 45): comparar holdings reales entre posiciones.
- [ ] Simulaciones de escenarios (regla 89) con supuestos explícitos.

## No hacer (decisión)

- Dashboard web propio: la bóveda Obsidian cubre la lectura humana; un HUD
  tipo fukura-agent-hud quedó rechazado en ADR-004.
- OWL/SHACL u ontologías formales: mismo veredicto que fukura (AGENTS.md,
  2026-10-02) — el valor está en la capa curada del "por qué", no en RDF.
