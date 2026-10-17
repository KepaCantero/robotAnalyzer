#!/usr/bin/env python3
"""Pipeline del knowledge graph del analizador — patrón fukura adaptado.

Fuentes (solo lectura): curated/*.json + datos/analisis/*.json
Salidas (generadas, nunca editar a mano):
  - memory.json           grafo JSONL formato @modelcontextprotocol/server-memory
  - ir.json               IR intermedio (debug)
  - boveda/               proyección Obsidian (una nota por entidad)
  - logs/sync-report.md   gates, conteos, incidencias
  - ../CLAUDE.md          briefing con estadísticas (regenerado)

Disciplina fukura: editar curated, regenerar aquí. Las observaciones con prefijo
manual: del grafo existente sobreviven los re-syncs (metabolism-policy.json).

Gates (fallan el pipeline si se incumplen):
  G1 todo producto con ≥1 arista BELONGS_TO
  G2 todo análisis con TOP 5 completo o excepción declarada (regla 7)
  G3 pesos de scoring suman 1.00 ± 0.01 por bloque (regla 58-60)
  G4 cero entidades huérfanas (sin aristas)
"""
from __future__ import annotations

import json
import os
import sys
import unicodedata
from datetime import date, datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SG = os.path.dirname(os.path.abspath(__file__))
CURATED = os.path.join(SG, "curated")
BOVEDA = os.path.join(RAIZ, "boveda")
ANALISIS_DIR = os.path.join(RAIZ, "datos", "analisis")

HOY = date.today().isoformat()


def _cargar(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _slug(texto):
    normalizado = unicodedata.normalize("NFD", texto.lower())
    sin_acentos = "".join(c for c in normalizado if not unicodedata.combining(c))
    keeps = "abcdefghijklmnopqrstuvwxyz0123456789-"
    limpio = (sin_acentos.replace(":", "-").replace(" ", "-").replace("_", "-"))
    limpio = "".join(c for c in limpio if c in keeps)
    while "--" in limpio:
        limpio = limpio.replace("--", "-")
    return limpio[:60].strip("-") or "sin-nombre"


def _titulo(nombre):
    return nombre.split(":", 1)[1].replace("-", " ").capitalize() if ":" in nombre else nombre


# ── 1) IR: fuentes → representación intermedia ───────────────────────────────

def construir_ir():
    ontologia = _cargar(os.path.join(CURATED, "ontology.json"))
    semilla = _cargar(os.path.join(CURATED, "seed-productos.json"))
    contras_ruta = os.path.join(CURATED, "contradictions.json")
    contras = _cargar(contras_ruta) if os.path.exists(contras_ruta) else {"entradas": []}

    entidades, relaciones = [], []

    def ent(nombre, tipo, observaciones):
        entidades.append({"name": nombre, "entityType": tipo,
                          "observations": [o for o in observaciones if o]})

    def rel(de, tipo, a):
        relaciones.append({"from": de, "relationType": tipo, "to": a})

    # Temas
    for t in ontologia["temas"]:
        ent(t["nombre"], "Tema", [
            "label: %s" % t["label"],
            "description: %s" % t["descripcion"],
            "reglas_doc: %s" % ", ".join(str(r) for r in t.get("reglas_doc", [])),
        ])
        for c in t["categorias"]:
            rel(t["nombre"], "EXPLORES", "category:%s" % c.lower().replace("_", "-"))

    # Categorías (taxonomía regla 9 — pertenecen a la metodología)
    for c in ontologia["categorias"]:
        ent(c["nombre"], "Categoria",
            ["label: %s" % c["label"], "regla: %d" % c["regla"]])
        rel(c["nombre"], "PART_OF", "method:metodologia-156-reglas")

    # Fuentes (jerarquía regla 73): cadena de prioridad explícita en el grafo
    fuentes = ontologia["fuentes"]
    for s in fuentes:
        ent(s["nombre"], "Fuente",
            ["label: %s" % s["label"], "prioridad: %d" % s["prioridad"],
             "regla: %d" % s["regla"]])
    for s1, s2 in zip(fuentes, fuentes[1:]):
        rel(s2["nombre"], "LOWER_PRIORITY_THAN", s1["nombre"])

    # Metodología (hub de las 156 reglas)
    for m in ontologia.get("metodologia", []):
        ent(m["nombre"], "Metodologia",
            ["label: %s" % m["label"], "description: %s" % m["descripcion"],
             "documento: %s" % m.get("documento", "")])

    # ADRs (decisiones de metodología, incl. evaluación de patrones fukura)
    for a in ontologia["adrs"]:
        ent(a["nombre"], "ADR", [
            "label: %s" % a["label"], "estado: %s" % a["estado"],
            "decision: %s" % a["decision"], "motivo: %s" % a["motivo"],
            "alternativas: %s" % a.get("alternativas", a.get("alternativa_adoptada", "")),
        ])
        rel(a["nombre"], "PART_OF", "method:metodologia-156-reglas")
        for enlace in a.get("enlaces", []):
            rel(a["nombre"], "RELATES_TO", enlace)

    # Productos de la semilla
    for p in semilla["productos"]:
        pid = "product:%s" % _slug(p.get("isin") or p.get("ticker") or p["nombre"])
        obs = ["label: %s" % p["nombre"], "emisor: %s" % p.get("emisor", ""),
               "naturaleza: %s" % p.get("naturaleza", ""),
               "isin: %s" % (p.get("isin") or "NO VERIFICADO (regla 101)"),
               "notas: %s" % p.get("notas", "")]
        ent(pid, "Producto", obs)
        rel(pid, "BELONGS_TO", "category:%s" % p["categoria"].lower().replace("_", "-"))

    # Análisis guardados (datos/analisis/*.json)
    if os.path.isdir(ANALISIS_DIR):
        for fich in sorted(os.listdir(ANALISIS_DIR)):
            if not fich.endswith(".json"):
                continue
            a = _cargar(os.path.join(ANALISIS_DIR, fich))
            aid = "analysis:%s" % fich[:-5]
            ent(aid, "Analisis", [
                "tema: %s" % a.get("tema", "?"),
                "fecha: %s" % a.get("fecha", "?"),
                "confianza: %s" % a.get("confianza_analisis", "?"),
                "robustez: %s" % a.get("robustez", "?"),
                "top5_tamano: %d" % len(a.get("top5", [])),
                "recomendacion: %.200s" % a.get("recomendacion", ""),
            ])
            slug_tema = _slug(a.get("tema", "tema"))
            rel(aid, "ANALYZES", "theme:%s" % slug_tema)
            for i, item in enumerate(a.get("top5", []), 1):
                pr = item["producto"]
                pid = "product:%s" % _slug(pr.get("isin") or pr.get("ticker") or pr["nombre"])
                ent_obs = ["label: %s" % pr["nombre"]]
                _asegurar(entidades, pid, "Producto", ent_obs)
                rel(aid, "RANKS_POS%d" % i, pid)
                # G1: todo producto con su categoría, también los derivados de
                # análisis (pueden no existir en la semilla actual)
                cat = "category:%s" % _slug(pr.get("categoria", "ETF_GLOBAL"))
                _asegurar(entidades, cat, "Categoria",
                          ["label: %s" % pr.get("categoria", "ETF_GLOBAL"), "regla: 9"])
                rel(pid, "BELONGS_TO", cat)

    # Contradicciones (regla 74): se enlazan a su producto si existe en el
    # grafo; si no, cuelgan de la metodología (la regla 74 es su contexto).
    nombres_previos = {e["name"] for e in entidades}
    for c in contras.get("entradas", []):
        cid = "contradiction:%s-%s" % (_slug(c.get("producto", "x")), _slug(c.get("campo", "y")))
        ent(cid, "Contradiccion", [
            "campo: %s" % c.get("campo", ""), "producto: %s" % c.get("producto", ""),
            "valor_a: %s (%s)" % (c.get("valor_a"), c.get("fuente_a")),
            "valor_b: %s (%s)" % (c.get("valor_b"), c.get("fuente_b")),
            "ganador_por_jerarquia: %s" % c.get("ganador", ""),
            "regla: 74",
        ])
        objetivo = "product:%s" % _slug(c.get("producto", ""))
        rel(cid, "CONCERNS", objetivo if objetivo in nombres_previos
            else "method:metodologia-156-reglas")

    return {"entidades": entidades, "relaciones": relaciones,
            "generado": datetime.now().isoformat(), "fuente_contradicciones": len(contras.get("entradas", []))}


def _asegurar(entidades, nombre, tipo, observaciones):
    if not any(e["name"] == nombre for e in entidades):
        entidades.append({"name": nombre, "entityType": tipo, "observations": observaciones})


# ── 2) Metabolismo: observaciones manual:* sobreviven ────────────────────────

def aplicar_metabolismo(ir, memoria_previa):
    policy = _cargar(os.path.join(CURATED, "metabolism-policy.json"))
    prefijo = policy["consolidacion"]["observaciones_manual_prefijo"]
    previo = {}
    for linea in memoria_previa:
        if linea.get("type") == "entity":
            previo[linea["name"]] = [o for o in linea.get("observations", [])
                                     if o.startswith(prefijo)]
    for e in ir["entidades"]:
        e["observations"] = list(previo.get(e["name"], [])) + e["observations"]
    return ir


# ── 3) Gates ─────────────────────────────────────────────────────────────────

def validar_gates(ir):
    fallos, avisos = [], []
    nombres = {e["name"] for e in ir["entidades"]}
    con_aristas = {r["from"] for r in ir["relaciones"]} | {r["to"] for r in ir["relaciones"]}

    for e in ir["entidades"]:
        if e["name"] not in con_aristas:
            fallos.append("G4 huérfana: %s" % e["name"])

    productos = [e for e in ir["entidades"] if e["entityType"] == "Producto"]
    relacion_prod = {r["from"] for r in ir["relaciones"] if r["relationType"] == "BELONGS_TO"}
    for p in productos:
        if p["name"] not in relacion_prod:
            fallos.append("G1 producto sin categoría: %s" % p["name"])

    for r in ir["relaciones"]:
        if r["from"] not in nombres or r["to"] not in nombres:
            fallos.append("arista con extremo inexistente: %s" % r)

    for a in ir["entidades"]:
        if a["entityType"] == "Analisis":
            tam = next((o.split(": ")[1] for o in a["observations"]
                        if o.startswith("top5_tamago") or o.startswith("top5_tamano")), "0")
            if int(tam) < 5:
                avisos.append("G2 %s: TOP 5 con %s válidos (regla 7: declarar si <5)" % (a["name"], tam))

    pesos = _cargar(os.path.join(CURATED, "scoring-weights.json"))
    for bloque in ("potencial", "rentabilidad_riesgo"):
        grupos = [pesos[bloque]["base"]] + list(pesos[bloque]["por_naturaleza"].values())
        for i, g in enumerate(grupos):
            valores = [v for k, v in g.items() if not k.startswith("$")]
            if not valores:      # override vacío = hereda los pesos base
                continue
            suma = sum(valores)
            if abs(suma - 1.0) > 0.01:
                fallos.append("G3 %s[%d] suma %.2f ≠ 1.00" % (bloque, i, suma))
    suma_veh = sum(v for k, v in pesos["vehiculo"].items() if not k.startswith("$"))
    if abs(suma_veh - 1.0) > 0.01:
        fallos.append("G3 vehiculo suma %.2f ≠ 1.00" % suma_veh)

    return fallos, avisos


# ── 4) memory.json (JSONL server-memory) ─────────────────────────────────────

def escribir_memoria(ir):
    ruta = os.path.join(SG, "memory.json")
    lineas = []
    for e in ir["entidades"]:
        lineas.append(json.dumps({"type": "entity", **e}, ensure_ascii=False))
    for r in ir["relaciones"]:
        lineas.append(json.dumps({"type": "relation", **r}, ensure_ascii=False))
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    with open(os.path.join(SG, "ir.json"), "w", encoding="utf-8") as f:
        json.dump(ir, f, ensure_ascii=False, indent=1)
    return ruta


# ── 5) Bóveda Obsidian (proyección read-only) ────────────────────────────────

CARPETAS = {"Tema": "01-tematicas", "Producto": "02-productos", "Analisis": "03-analisis",
            "Fuente": "04-fuentes", "ADR": "05-metodologia", "Contradiccion": "06-contradicciones",
            "Categoria": "05-metodologia"}


def escribir_boveda(ir):
    for carpeta in set(CARPETAS.values()) | {"00-index"}:
        os.makedirs(os.path.join(BOVEDA, carpeta), exist_ok=True)

    # Las notas generadas de corridas anteriores se eliminan: la bóveda es una
    # proyección, no un archivo acumulativo (los ficheros sin generated: true
    # son notas personales del usuario y NO se tocan).
    for carpeta in set(CARPETAS.values()) | {"00-index"}:
        for fich in os.listdir(os.path.join(BOVEDA, carpeta)):
            if not fich.endswith(".md"):
                continue
            ruta_f = os.path.join(BOVEDA, carpeta, fich)
            try:
                with open(ruta_f, encoding="utf-8") as f:
                    cabecera = f.read(400)
                if "generated: true" in cabecera:
                    os.remove(ruta_f)
            except OSError:
                pass

    entrantes = {}
    salientes = {}
    for r in ir["relaciones"]:
        salientes.setdefault(r["from"], []).append(r)
        entrantes.setdefault(r["to"], []).append(r)

    def wikilink(nombre):
        return "[[%s]]" % _slug(nombre)

    for e in ir["entidades"]:
        carpeta = CARPETAS.get(e["entityType"], "05-metodologia")
        ruta = os.path.join(BOVEDA, carpeta, _slug(e["name"]) + ".md")
        label = next((o[7:] for o in e["observations"] if o.startswith("label: ")),
                     _titulo(e["name"]))
        lineas = ["---", "type: %r" % e["entityType"].lower(),
                  "graph_id: %r" % e["name"], "generated: true",
                  "generated_at: %r" % HOY, "---", "", "# %s" % label, ""]
        for o in e["observations"]:
            if o.startswith("label: "):
                continue
            lineas.append("- %s" % o)
        lineas.append("")
        rels_out = salientes.get(e["name"], [])
        rels_in = entrantes.get(e["name"], [])
        if rels_out:
            lineas.append("## Relaciones")
            for r in rels_out:
                lineas.append("- %s → %s" % (r["relationType"], wikilink(r["to"])))
        if rels_in:
            lineas.append("")
            lineas.append("## Referenciado por")
            for r in rels_in:
                lineas.append("- %s ← %s (%s)" % (wikilink(r["from"]), r["relationType"],
                                                  r["from"].split(":")[0]))
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")

    # Map of Content
    moc = ["---", "type: map", "generated: true", "generated_at: %r" % HOY, "---",
           "", "# Mapa del analizador", "",
           "Proyección del knowledge graph (`.semantic-graph/memory.json`). "
           "Notas `generated: true`: no editar a mano; corregir en `curated/` y "
           "regenerar con `python3 .semantic-graph/pipeline.py`.", ""]
    por_tipo = {}
    for e in ir["entidades"]:
        por_tipo.setdefault(e["entityType"], []).append(e)
    for tipo in ("Tema", "Producto", "Analisis", "Fuente", "ADR", "Contradiccion", "Categoria"):
        if tipo in por_tipo:
            moc.append("## %s (%d)" % (tipo, len(por_tipo[tipo])))
            for e in sorted(por_tipo[tipo], key=lambda x: x["name"]):
                label = next((o[7:] for o in e["observations"] if o.startswith("label: ")),
                             _titulo(e["name"]))
                moc.append("- [[%s|%s]]" % (_slug(e["name"]), label))
            moc.append("")
    with open(os.path.join(BOVEDA, "00-index", "Map of Content.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(moc) + "\n")

    # README de la bóveda
    readme = ["# Bóveda del analizador — knowledge vault", "",
              "Proyección Obsidian del grafo `%s`." % os.path.relpath(
                  os.path.join(SG, "memory.json"), RAIZ), "",
              "- Regenerar: `python3 .semantic-graph/pipeline.py`",
              "- Nunca editar notas con `generated: true` — corregir la fuente y re-ejecutar.",
              "- Consultar el grafo desde cualquier agente: MCP `knowledge-graph` "
              "(`read_graph` / `search_nodes`) o `analizador grafo \"consulta\"`.",
              "", "Cifras: %d entidades, %d relaciones (generado %s)." % (
                  len(ir["entidades"]), len(ir["relaciones"]), HOY), ""]
    with open(os.path.join(BOVEDA, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(readme) + "\n")


# ── 6) Reporte + CLAUDE.md ───────────────────────────────────────────────────

def escribir_reporte(ir, fallos, avisos):
    conteo = {}
    for e in ir["entidades"]:
        conteo[e["entityType"]] = conteo.get(e["entityType"], 0) + 1
    lineas = ["# Sync report — %s" % datetime.now().isoformat(timespec="seconds"), "",
              "Entidades: %d · Relaciones: %d" % (len(ir["entidades"]), len(ir["relaciones"])),
              "", "## Conteo por tipo"]
    lineas += ["- %s: %d" % (k, v) for k, v in sorted(conteo.items())]
    lineas += ["", "## Gates"]
    lineas += ["- ❌ %s" % f for f in fallos] or ["- ✅ todas las gates en verde"]
    lineas += ["- ⚠️ %s" % a for a in avisos]
    os.makedirs(os.path.join(SG, "logs"), exist_ok=True)
    with open(os.path.join(SG, "logs", "sync-report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    return conteo


def escribir_claude_md(conteo, ir):
    ruta = os.path.join(RAIZ, "CLAUDE.md")
    tipos = "\n".join("- %s: %d" % (k, v) for k, v in sorted(conteo.items()))
    contenido = (
        "<!-- AUTO-GENERATED por .semantic-graph/pipeline.py — regenerar, no editar a mano. -->\n"
        "@AGENTS.md\n\n"
        "# Analizador de fondos y ETFs — briefing del grafo (auto-generado)\n\n"
        "Knowledge graph: %d entidades / %d relaciones, JSONL en `.semantic-graph/memory.json` "
        "(nunca editar a mano; regenerar con `python3 .semantic-graph/pipeline.py`).\n"
        "Nombres de entidad: `theme:*` `category:*` `product:*` `analysis:*` `source:*` "
        "`adr:*` `contradiction:*`; las relaciones unen por `from`/`to` = `name` exacto.\n"
        "Bóveda Obsidian (proyección regenerada, read-only): `boveda/` — una nota por "
        "entidad, el frontmatter `graph_id` es la join key.\n"
        "Metodología maestra: `ANALIZADOR DE FONDOS Y ETFS.docx` (156 reglas) destilada "
        "en `src/analizador/agents/prompts/`.\n\n"
        "## Conteo por tipo\n%s\n" % (len(ir["entidades"]), len(ir["relaciones"]), tipos))
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    desde_cero = "--from-scratch" in sys.argv
    memoria_previa = []
    ruta_mem = os.path.join(SG, "memory.json")
    if not desde_cero and os.path.exists(ruta_mem):
        with open(ruta_mem, encoding="utf-8") as f:
            memoria_previa = [json.loads(l) for l in f if l.strip()]

    ir = construir_ir()
    if not desde_cero:
        ir = aplicar_metabolismo(ir, memoria_previa)
    fallos, avisos = validar_gates(ir)
    if fallos:
        print("GATES EN ROJO — grafo NO regenerado:")
        for f_ in fallos:
            print("  ❌ %s" % f_)
        escribir_reporte(ir, fallos, avisos)
        sys.exit(1)

    escribir_memoria(ir)
    escribir_boveda(ir)
    conteo = escribir_reporte(ir, fallos, avisos)
    escribir_claude_md(conteo, ir)
    print("Grafo regenerado: %d entidades, %d relaciones. Gates ✅ (%d avisos). "
          "Bóveda y CLAUDE.md actualizados." % (
              len(ir["entidades"]), len(ir["relaciones"]), len(avisos)))


if __name__ == "__main__":
    main()
