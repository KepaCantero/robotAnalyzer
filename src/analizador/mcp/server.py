"""Servidor MCP de datos del analizador — stdlib puro, sin SDK.

Protocolo Model Context Protocol sobre stdio (JSON-RPC 2.0): initialize,
tools/list, tools/call. Compatible con ZCode/Claude Code/Cursor vía .mcp.json:

    {"analizador-datos": {"command": "python3", "args": ["-m", "analizador.mcp.server"]}}

Tools expuestos:
  buscar_productos(query, limite)   búsqueda de tickers Yahoo (regla 8)
  cotizacion(ticker)                precio con fecha y etiqueta de calidad (reglas 72/75)
  historico(ticker, rango)          serie de cierres + métricas CALCULADO (regla 75)
  puntuar(factores, bloque, naturaleza)  motor determinista (reglas 58-60)
  consultar_grafo(query)            subgrafo del knowledge graph (patrón fukura)

Regla 101: los fallos devuelven NO_DISPONIBLE, jamás un valor inventado.
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
SRC = os.path.join(RAIZ, "src")
for p in (SRC, os.path.join(RAIZ, ".semantic-graph", "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

PROTOCOLO = "2025-06-18"
NOMBRE_SERVIDOR = "analizador-datos"


def _tools():
    return [
        {"name": "buscar_productos",
         "description": "Busca tickers/fondos por nombre (descubrimiento de universo, regla 8). Requiere red; sin red devuelve lista vacía.",
         "inputSchema": {"type": "object",
                         "properties": {"query": {"type": "string"},
                                        "limite": {"type": "integer", "default": 10}},
                         "required": ["query"]}},
        {"name": "cotizacion",
         "description": "Último precio de un ticker con fecha de corte y etiqueta de calidad de dato (reglas 72/75). Fuente financiera reconocida (jerarquía regla 73, prioridad 6).",
         "inputSchema": {"type": "object",
                         "properties": {"ticker": {"type": "string"}},
                         "required": ["ticker"]}},
        {"name": "historico",
         "description": "Serie de cierres ajustados diarios de un ticker y métricas de riesgo calculadas sobre ella (volatilidad anualizada, máximo drawdown, Sharpe, Sortino — etiqueta CALCULADO, regla 75; ids brutos para el control de doble conteo, regla 63). Sin red → NO_DISPONIBLE.",
         "inputSchema": {"type": "object",
                         "properties": {"ticker": {"type": "string"},
                                        "rango": {"type": "string", "default": "2y"}},
                         "required": ["ticker"]}},
        {"name": "puntuar",
         "description": "Aplica el motor de scoring determinista (reglas 58-60) a un bloque de factores 0-100. Devuelve score y avisos (doble conteo, pesos).",
         "inputSchema": {"type": "object",
                         "properties": {"factores": {"type": "object"},
                                        "bloque": {"type": "string",
                                                   "enum": ["potencial", "rr", "vehiculo"],
                                                   "default": "potencial"},
                                        "naturaleza": {"type": "string",
                                                       "default": "ETF_ACCIONES"}},
                         "required": ["factores"]}},
        {"name": "leer_web",
         "description": "Convierte cualquier web en markdown (Firecrawl self-host/cloud o Jina Reader gratuito sin clave). Para fichas de emisor (prioridad 1, regla 73), justETF/Morningstar o prensa. Devuelve Dato con fuente/fecha/etiqueta de calidad.",
         "inputSchema": {"type": "object",
                         "properties": {"url": {"type": "string"},
                                        "fuente": {"type": "string",
                                                   "enum": ["emisor", "fuente_financiera", "secundaria"],
                                                   "default": "fuente_financiera"}},
                         "required": ["url"]}},
        {"name": "consultar_grafo",
         "description": "Recupera el subgrafo del knowledge graph del analizador (temas, productos, análisis, ADRs, fuentes) para una pregunta en lenguaje natural.",
         "inputSchema": {"type": "object",
                         "properties": {"query": {"type": "string"}},
                         "required": ["query"]}},
    ]


def _llamar(nombre, args):
    if nombre == "buscar_productos":
        from analizador.data.sources import yahoo
        res = yahoo.buscar(args["query"], int(args.get("limite", 10)))
        return res if res else {"aviso": "sin resultados o sin red (regla 101: no se inventan productos)"}
    if nombre == "cotizacion":
        from analizador.data.sources import web2api, mercado
        d = web2api.cotizacion_yfinance(args["ticker"])   # yfinance si está instalado
        if d.etiqueta == "NO_DISPONIBLE":
            d = mercado.cotizacion(args["ticker"])        # cadena yahoo→stooq
        return d.to_dict()
    if nombre == "historico":
        from analizador.data.sources import web2api, mercado
        from analizador.scoring import metricas as mod_metricas
        rango = args.get("rango", "2y")
        h = web2api.historico_yfinance(args["ticker"], rango)   # yfinance si está
        if h.etiqueta == "NO_DISPONIBLE":
            h = mercado.historico(args["ticker"], rango)        # cadena yahoo→stooq
        out = h.to_dict()
        out["n"] = len(h.valor or [])
        if h.valor:
            out["desde"], out["hasta"] = h.valor[0][0], h.valor[-1][0]
        out["metricas"] = {k: d.to_dict()
                           for k, d in mod_metricas.metricas_desde_dato(h).items()}
        return out
    if nombre == "leer_web":
        from analizador.data.sources import web2api
        return web2api.leer_web(args["url"], etiqueta_fuente=args.get("fuente", "fuente_financiera")).to_dict()
    if nombre == "puntuar":
        from analizador.scoring.engine import ScoringEngine, factores_desde_dict
        motor = ScoringEngine()
        factores = factores_desde_dict(args["factores"])
        naturaleza = args.get("naturaleza", "ETF_ACCIONES")
        bloque = args.get("bloque", "potencial")
        if bloque == "potencial":
            score, avisos = motor.score_potencial(factores, naturaleza)
        elif bloque == "rr":
            score, avisos = motor.score_rr(factores, naturaleza)
        else:
            score, avisos = motor.score_vehiculo(factores)
        return {"score": score, "avisos": avisos, "bloque": bloque}
    if nombre == "consultar_grafo":
        from subgraph_retriever import recuperar
        return {"texto": recuperar(args["query"])}
    raise ValueError("tool desconocida: %s" % nombre)


def _respuesta(id_rpc, resultado):
    return {"jsonrpc": "2.0", "id": id_rpc, "result": resultado}


def _error(id_rpc, codigo, mensaje):
    return {"jsonrpc": "2.0", "id": id_rpc,
            "error": {"code": codigo, "message": mensaje}}


def manejar(mensaje):
    metodo = mensaje.get("method", "")
    id_rpc = mensaje.get("id")
    params = mensaje.get("params", {}) or {}

    if metodo == "initialize":
        return _respuesta(id_rpc, {
            "protocolVersion": params.get("protocolVersion", PROTOCOLO),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": NOMBRE_SERVIDOR, "version": "0.1.0"}})
    if metodo == "notifications/initialized":
        return None  # notificación: sin respuesta
    if metodo == "ping":
        return _respuesta(id_rpc, {})
    if metodo == "tools/list":
        return _respuesta(id_rpc, {"tools": _tools()})
    if metodo == "tools/call":
        try:
            resultado = _llamar(params.get("name", ""), params.get("arguments", {}) or {})
            return _respuesta(id_rpc, {
                "content": [{"type": "text",
                             "text": json.dumps(resultado, ensure_ascii=False,
                                                default=str)}]})
        except Exception as e:  # noqa: BLE001 — el error viaja al cliente MCP
            return _respuesta(id_rpc, {
                "content": [{"type": "text", "text": "ERROR: %s" % e}],
                "isError": True})
    if id_rpc is not None:
        return _error(id_rpc, -32601, "método desconocido: %s" % metodo)
    return None


def main():
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            mensaje = json.loads(linea)
        except json.JSONDecodeError:
            continue
        respuesta = manejar(mensaje)
        if respuesta is not None:
            sys.stdout.write(json.dumps(respuesta, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
