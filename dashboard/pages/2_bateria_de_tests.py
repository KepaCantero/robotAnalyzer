"""Batería de tests visible en Streamlit — ¿el análisis es correcto?

Tres bloques que responden tres preguntas distintas:
  A) MOTOR DE BACKTESTING: ¿el motor calcula bien? (V1-V6 de verificar_backtest)
  B) ANALIZADOR (156 REGLAS): ¿el pipeline cumple su metodología? (37 unittest
     del motor de scoring/TOP 5/crossval ejecutados en vivo)
  C) VALIDACIÓN EX-POST: ¿las selecciones del analizador acertaron? (event
     study: retornos forward del TOP 5 vs universo vs benchmark desde la fecha
     de cada análisis almacenado)

Página de Streamlit (se auto-registra en el sidebar junto a la app principal).
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from datetime import date, datetime

import pandas as pd
import streamlit as st

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (os.path.dirname(os.path.abspath(__file__)), RAIZ,
          os.path.join(RAIZ, "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

import verificar_backtest as vb  # noqa: E402  (misma carpeta que la app)

st.set_page_config(page_title="Batería de tests", page_icon="🧪", layout="wide")


def _ancho() -> dict:
    try:
        mayor, menor = st.__version__.split(".")[:2]
        if (int(mayor), int(menor)) >= (1, 49):
            return {"width": "stretch"}
    except (ValueError, AttributeError):
        pass
    return {"use_container_width": True}


# ═══════════════════════════════════════════════════════════════════════════
# BLOQUE A — Motor de backtesting
# ═══════════════════════════════════════════════════════════════════════════

def _pintar_bloque(b) -> None:
    for linea in b.lineas:
        st.caption(linea)
    filas = [{"Check": c.nombre,
              "Resultado": "✅ OK" if c.ok else ("⚠️ aviso" if c.tipo == "aviso" else "❌ FALLO"),
              "Detalle": c.detalle} for c in b.checks]
    st.dataframe(pd.DataFrame(filas), hide_index=True, **_ancho())


def bloque_motor() -> None:
    st.subheader("A · Motor de backtesting — ¿calcula bien?")
    st.caption("V1-V3: correctitud (respuesta conocida a mano, invariantes y doble "
               "motor independiente). V4-V6: diagnóstico metodológico (avisos, no fallos).")
    if not st.button("▶️ Ejecutar tests del motor", type="primary"):
        return
    bloques = []
    with st.spinner("V1 sintético…"):
        bloques.append(vb.checks_v1())
    try:
        with st.spinner("Descargando AAPL (3 años)…"):
            df = vb.descargar_para_verificacion()
    except Exception as exc:
        df = None
        st.warning(f"Sin datos de Yahoo ({exc}); se ejecuta solo V1 (offline).")
    if df is not None:
        close = df["Close"]
        with st.spinner("V2-V6 sobre datos reales…"):
            bloques += [vb.checks_v2(close), vb.checks_v3(close),
                        vb.bloque_v4(df, close), vb.bloque_v5(close), vb.bloque_v6(close)]

    fallos = sum(1 for b in bloques for c in b.checks
                 if not c.ok and c.tipo == "correctitud")
    avisos = sum(1 for b in bloques for c in b.checks if not c.ok and c.tipo == "aviso")
    if fallos:
        st.error(f"❌ {fallos} fallos de correctitud — el motor NO está verificado.")
    else:
        st.success(f"✅ Motor verificado: 0 fallos de correctitud ({avisos} avisos metodológicos).")
    for b in bloques:
        with st.expander(b.titulo, expanded=fallos > 0):
            _pintar_bloque(b)


# ═══════════════════════════════════════════════════════════════════════════
# BLOQUE B — Analizador (156 reglas) vía unittest en vivo
# ═══════════════════════════════════════════════════════════════════════════

class _Recolector(unittest.TestResult):
    """TestResult que acumula (test, estado, detalle) para la tabla de Streamlit."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filas = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.filas.append((test.id(), "PASS", ""))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.filas.append((test.id(), "FAIL", str(err[1])[:160]))

    def addError(self, test, err):
        super().addError(test, err)
        self.filas.append((test.id(), "ERROR", str(err[1])[:160]))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.filas.append((test.id(), "SKIP", reason))


def _suite_tests():
    cargador = unittest.defaultTestLoader
    return cargador.discover(os.path.join(RAIZ, "tests"), pattern="test_*.py",
                             top_level_dir=RAIZ)


def bloque_analizador() -> None:
    st.subheader("B · Analizador (156 reglas) — ¿cumple su metodología?")
    st.caption("Los unittest del proyecto ejecutados en vivo: pesos de scoring "
               "(reglas 58-64), TOP 5 obligatorio (7, 79-80, 147), validación "
               "cruzada de fuentes (73-74), almacen/seguimiento (105, 137) y "
               "pipeline completo offline.")
    if not st.button("▶️ Ejecutar los 37 tests del analizador", type="primary"):
        return
    with st.spinner("Ejecutando la suite unittest…"):
        suite = _suite_tests()
        recolector = _Recolector()
        corredor = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0,
                                           resultclass=_Recolector)
        resultado = corredor.run(suite)
    df = pd.DataFrame(recolector.filas, columns=["Test", "Estado", "Detalle"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", resultado.testsRun)
    c2.metric("PASS", len(df[df["Estado"] == "PASS"]))
    c3.metric("Fallos + errores",
              int((df["Estado"].isin(["FAIL", "ERROR"])).sum()))
    if (df["Estado"].isin(["FAIL", "ERROR"])).any():
        st.error("❌ El analizador NO cumple alguna regla — ver tabla.")
    else:
        st.success("✅ El motor del analizador cumple las reglas verificadas.")
    with st.expander("Detalle test a test", expanded=(df["Estado"] != "PASS").any()):
        st.dataframe(df, hide_index=True, **_ancho())


# ═══════════════════════════════════════════════════════════════════════════
# BLOQUE C — Validación ex-post: ¿las selecciones acertaron?
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800, show_spinner=False)
def _descargar_cierres(tickers: tuple, desde: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(list(tickers), start=desde, interval="1d", auto_adjust=True,
                     progress=False, threads=False, group_by="column")
    cierres = df["Close"]
    if isinstance(cierres, pd.Series):
        cierres = cierres.to_frame(name=tickers[0])
    return cierres


def _mapa_tickers() -> dict:
    ruta = os.path.join(RAIZ, ".semantic-graph", "curated", "seed-productos.json")
    with open(ruta, encoding="utf-8") as f:
        semilla = json.load(f)
    return {p["nombre"]: p.get("ticker", "") for p in semilla["productos"]}


def _retorno_forward(serie: pd.Series, desde_fecha) -> tuple:
    """(retorno_desde_el_análisis, días) o (None, 0) si aún no hay datos."""
    validas = serie.dropna()
    posteriores = validas[validas.index >= pd.Timestamp(desde_fecha)]
    if posteriores.empty:
        return None, 0
    dias = (posteriores.index[-1] - posteriores.index[0]).days
    if len(posteriores) < 2:
        return 0.0, dias
    return float(posteriores.iloc[-1] / posteriores.iloc[0] - 1), dias


def bloque_validacion_expost() -> None:
    st.subheader("C · Validación ex-post — ¿el análisis acertó?")
    st.caption("Event study: para cada análisis almacenado, retorno forward del "
               "TOP 5 desde su fecha vs el universo descartado vs el benchmark. "
               "Aquí el backtest juzga las SELECCIONES del analizador.")

    almacen_dir = os.path.join(RAIZ, "datos", "analisis")
    if not os.path.isdir(almacen_dir) or not os.listdir(almacen_dir):
        st.info("No hay análisis almacenados todavía. Genera uno con "
                "`analizador analizar \"tema\"` y vuelve aquí.")
        return

    benchmark = st.selectbox("Benchmark", ["IWDA.AS", "SPY", "CSPX.AS"],
                             help="ETF mundo/EUA como referencia de buy & hold.")
    if not st.button("▶️ Evaluar análisis almacenados", type="primary"):
        return

    mapa = _mapa_tickers()
    import glob
    ficheros = sorted(glob.glob(os.path.join(almacen_dir, "*.json")))
    analisis = []
    for ruta in ficheros:
        with open(ruta, encoding="utf-8") as f:
            analisis.append(json.load(f))
    if not analisis:
        st.warning("Los ficheros de análisis están vacíos.")
        return

    tickers_necesarios = {benchmark}
    for a in analisis:
        for item in a.get("top5", []):
            t = mapa.get(item["producto"]["nombre"], "")
            if t:
                tickers_necesarios.add(t)
        for d in a.get("descartados", []):
            t = mapa.get(d.get("producto", ""), "")
            if t:
                tickers_necesarios.add(t)

    try:
        with st.spinner(f"Descargando {len(tickers_necesarios)} tickers…"):
            cierres = _descargar_cierres(tuple(sorted(tickers_necesarios)),
                                         min(a["fecha"] for a in analisis))
    except Exception as exc:
        st.error(f"No se pudieron descargar los precios ({exc}). El bloque C "
                 "requiere red.")
        return

    filas_resumen = []
    detalle_por_analisis = {}
    for a in analisis:
        fecha = a["fecha"]
        filas = []
        for i, item in enumerate(a.get("top5", []), 1):
            nombre = item["producto"]["nombre"]
            t = mapa.get(nombre, "")
            ret, _ = _retorno_forward(cierres[t], fecha) if t in cierres else (None, 0)
            filas.append({"Producto": nombre, "Ticker": t or "—", "Posición": str(i),
                          "R/R": item.get("scores", {}).get("rentabilidad_riesgo"),
                          "Grupo": "TOP 5", "Retorno forward": ret})
        for d in a.get("descartados", []):
            nombre = d.get("producto", "")
            t = mapa.get(nombre, "")
            ret, _ = _retorno_forward(cierres[t], fecha) if t in cierres else (None, 0)
            filas.append({"Producto": nombre, "Ticker": t or "—", "Posición": "—",
                          "R/R": None, "Grupo": "Universo", "Retorno forward": ret})
        if not filas:
            continue
        detalle = pd.DataFrame(filas)
        detalle_por_analisis[(a.get("tema", "?"), fecha)] = detalle

        top5 = detalle[detalle["Grupo"] == "TOP 5"]["Retorno forward"].dropna()
        univ = detalle[detalle["Grupo"] == "Universo"]["Retorno forward"].dropna()
        bench, dias = _retorno_forward(cierres[benchmark], fecha)
        media_top5 = float(top5.mean()) if len(top5) else None
        media_univ = float(univ.mean()) if len(univ) else None
        hit = (top5 > media_univ).mean() if len(top5) and media_univ is not None else None
        filas_resumen.append({
            "Fecha": fecha, "Tema": a.get("tema", "?"),
            "Días forward": dias,
            "TOP 5 (media)": media_top5, "Universo (media)": media_univ,
            "Benchmark": bench, "Hit rate TOP5>universo": hit,
            "Acierta vs bench": (media_top5 > bench) if media_top5 is not None
            and bench is not None else None,
        })

    resumen = pd.DataFrame(filas_resumen)
    fmt = {"TOP 5 (media)": "{:.2%}", "Universo (media)": "{:.2%}",
           "Benchmark": "{:.2%}", "Hit rate TOP5>universo": "{:.0%}"}
    st.markdown("**Resumen por análisis** — ¿el TOP 5 batió a su universo y al benchmark?")
    st.dataframe(resumen.style.format(fmt, na_rep="—"), hide_index=True, **_ancho())

    with st.expander("Detalle producto a producto (último análisis)", expanded=True):
        clave = list(detalle_por_analisis)[-1] if detalle_por_analisis else None
        if clave:
            det = detalle_por_analisis[clave].copy()
            det["Retorno forward"] = det["Retorno forward"].apply(
                lambda v: "—" if v is None else f"{v:+.2%}")
            st.caption(f"{clave[0]} · {clave[1]}")
            st.dataframe(det, hide_index=True, **_ancho())

    with st.expander("⚠️ Cómo leer esto (límites de la validación)", expanded=False):
        st.markdown(
            "- **Pocos días forward**: los análisis de HOY aún no dicen nada; "
            "necesitan semanas/meses de histórico.\n"
            "- **Modo determinista**: sin clave LLM los scores son neutros de "
            "proceso — este bloque mide la CADENA COMPLETA (almacenar → resolver "
            "tickers → retornos), no la calidad del juicio.\n"
            "- **Regla 101**: los productos sin ticker verificado quedan fuera "
            "del estudio (mejor fuera que con datos inventados).\n"
            "- **Regla 100/139**: superar al benchmark una vez no es 'acertar'; "
            "la significación exige muchas observaciones (regla 156: calidad de "
            "decisión, no cantidad de datos).")


# ═══════════════════════════════════════════════════════════════════════════

st.title("🧪 Batería de tests — ¿el análisis es correcto?")
st.caption("Tres niveles: el motor calcula bien (A) · el analizador cumple sus "
           "156 reglas (B) · las selecciones acertaron ex-post (C).")

bloque_motor()
st.divider()
bloque_analizador()
st.divider()
bloque_validacion_expost()
