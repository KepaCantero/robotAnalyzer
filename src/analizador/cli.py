"""CLI del analizador — stdlib puro (argparse).

Uso:
  analizador analizar "minería de cobre" [--perfil perfiles/perfil.json]
                                    [--cartera perfiles/cartera.json]
                                    [--json] [--sin-red]
  analizador historial [tema]
  analizador grafo "consulta"            # subgrafo del knowledge graph
  analizador grafo-rebuild               # regenerar grafo + bóveda Obsidian
  analizador demo                        # análisis determinista de ejemplo
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if RAIZ not in sys.path:
    sys.path.insert(0, os.path.join(RAIZ, "src"))


def _cargar_json(ruta: str):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def cmd_analizar(args) -> int:
    from analizador.domain.models import Cartera, PerfilInversor, Posicion
    from analizador.pipeline.orquestador import OrquestadorAnalisis
    from analizador.pipeline.reportero import render

    perfil = None
    cartera = None
    if args.perfil:
        perfil = PerfilInversor.from_dict(_cargar_json(args.perfil))
    if args.cartera:
        data = _cargar_json(args.cartera)
        cartera = Cartera(posiciones=[Posicion(**p) for p in data.get("posiciones", [])])
    if args.sin_red:
        os.environ["ANALIZADOR_ALLOW_NETWORK"] = "0"

    orq = OrquestadorAnalisis(con_red=not args.sin_red)
    resultado = orq.analizar_tematica(args.tema, perfil=perfil, cartera=cartera)

    dict_final = json.loads(resultado.to_json())
    dict_final["avisos"] = orq.avisos
    if args.json:
        print(json.dumps(dict_final, ensure_ascii=False, indent=2))
    else:
        print(render(resultado, dict_final))
    return 0


def cmd_historial(args) -> int:
    from analizador.storage.analyses import AlmacenAnalisis
    alm = AlmacenAnalisis(os.path.join(RAIZ, "datos", "analisis"))
    filas = alm.listar(args.tema)
    if not filas:
        print("Sin análisis almacenados%s." % ((" de '%s'" % args.tema) if args.tema else ""))
        return 0
    for f in filas:
        top = ", ".join(alm.nombres_top5(f)[:3]) + ("…" if len(f["top5"]) > 3 else "")
        print("%s  %s  → %s" % (f.get("fecha", "?"), f.get("tema", "?"), top))
    return 0


def cmd_grafo(args) -> int:
    sys.path.insert(0, os.path.join(RAIZ, ".semantic-graph", "scripts"))
    from subgraph_retriever import recuperar
    print(recuperar(args.consulta, estrategia=args.estrategia))
    return 0


def cmd_grafo_rebuild(args) -> int:
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(RAIZ, ".semantic-graph", "pipeline.py")])
    return r.returncode


def cmd_demo(args) -> int:
    """Análisis determinista completo del ejemplo de la regla 3 (minería de cobre)."""
    args.tema = "minería de cobre"
    args.perfil = None
    args.cartera = None
    args.json = False
    args.sin_red = True
    return cmd_analizar(args)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="analizador",
                                description="Analizador profesional de fondos y ETFs (156 reglas)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("analizar", help="Pipeline completo sobre una temática")
    pa.add_argument("tema")
    pa.add_argument("--perfil", help="JSON con PerfilInversor (regla 13)")
    pa.add_argument("--cartera", help="JSON con cartera (regla 14)")
    pa.add_argument("--json", action="store_true", help="salida JSON en vez de informe")
    pa.add_argument("--sin-red", action="store_true", help="sin llamadas de red")
    pa.set_defaults(fn=cmd_analizar)

    ph = sub.add_parser("historial", help="Análisis almacenados (regla 137)")
    ph.add_argument("tema", nargs="?", default=None)
    ph.set_defaults(fn=cmd_historial)

    pg = sub.add_parser("grafo", help="Consulta el knowledge graph")
    pg.add_argument("consulta")
    pg.add_argument("--estrategia", default="hybrid",
                    choices=["keyword", "bfs", "hybrid"])
    pg.set_defaults(fn=cmd_grafo)

    pr = sub.add_parser("grafo-rebuild", help="Regenera grafo + bóveda Obsidian")
    pr.set_defaults(fn=cmd_grafo_rebuild)

    pd = sub.add_parser("demo", help="Demo determinista: 'minería de cobre' sin red")
    pd.set_defaults(fn=cmd_demo)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
