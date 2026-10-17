# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD DE BACKTESTING — Streamlit + VectorBT
# ═══════════════════════════════════════════════════════════════════════════
#
# INSTALACIÓN (entorno virtual limpio):
#   python3 -m venv .venv
#   source .venv/bin/activate        # Windows: .venv\Scripts\activate
#   pip install "streamlit>=1.32,<2" "vectorbt>=0.26,<0.28" "yfinance>=0.2.40" \
#               "plotly>=5.18" "pandas>=1.5,<2.3" "numpy>=1.23,<2"
#
#   Nota: numpy se limita a <2 porque VectorBT (OSS) depende de numba,
#   que aún no es compatible con numpy 2.x.
#
# EJECUCIÓN:
#   streamlit run app.py
#
# El archivo es autocontenido y modular por secciones:
#   1) CAPA DE DATOS      → descarga de Yahoo Finance (cacheada)
#   2) CAPA DE BACKTEST   → estrategia cruce de medias móviles (SMA/EMA)
#   3) CAPA DE RENDERIZADO→ KPIs, gráfico Plotly, stats, trades
#   4) UI PRINCIPAL       → sidebar + panel con pestañas
# ═══════════════════════════════════════════════════════════════════════════

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import vectorbt as vbt
import yfinance as yf

# ─────────────────────────────────────────────────────────────────────────────
# 1) CAPA DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def descargar_datos(ticker: str, inicio: date, fin: date) -> pd.DataFrame:
    """Descarga OHLCV de Yahoo Finance y normaliza columnas.

    Sube ValueError con mensaje limpio si el ticker no existe o Yahoo no
    devuelve datos; la UI la convierte en st.error sin romper la app.

    yfinance >= 0.2.51 devuelve columnas MultiIndex (precio, ticker) con
    auto_adjust=True por defecto: se aplana para trabajar con nombres simples.
    """
    df = yf.download(
        ticker,
        start=inicio.isoformat(),
        end=(fin + timedelta(days=1)).isoformat(),  # end de yf es exclusivo
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        raise ValueError(
            f"Yahoo Finance no devolvió datos para '{ticker}'. "
            "Comprueba que el ticker existe (ej. AAPL, BTC-USD) y que el "
            "rango de fechas es válido."
        )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
        if isinstance(df.columns, pd.MultiIndex):  # variantes antiguas
            df.columns = df.columns.droplevel(0)
    faltan = [c for c in ("Close", "Volume") if c not in df.columns]
    if faltan:
        raise ValueError(f"Datos incompletos para '{ticker}': faltan {faltan}.")
    df = df.dropna(subset=["Close"]).sort_index()
    if df.empty:
        raise ValueError(f"El ticker '{ticker}' no tiene precios válidos en el rango.")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2) CAPA DE BACKTEST
# ─────────────────────────────────────────────────────────────────────────────

def ejecutar_backtest(
    df: pd.DataFrame,
    tipo_ma: str,
    rapido: int,
    lento: int,
    capital_inicial: float,
    comision: float,
):
    """Estrategia cruce de medias móviles sobre el cierre.

    Señales (convención VectorBT):
      - Entrada: la MA rápida CRUZA POR ENCIMA de la lenta (golden cross).
      - Salida : la MA rápida CRUZA POR DEBAJO de la lenta (death cross).
    Nota: si la rápida ya está por encima en la primera vela no hay cruce,
    por lo que no se entra hasta el primer cruce efectivo (comportamiento
    estándar del tutorial de VectorBT).

    Devuelve (portfolio, close, ma_rapida, ma_lenta, entradas, salidas).
    """
    close = df["Close"].astype(float)
    es_ema = tipo_ma == "EMA"

    ma_rapida = vbt.MA.run(close, window=rapido, ewm=es_ema, short_name="rápida")
    ma_lenta = vbt.MA.run(close, window=lento, ewm=es_ema, short_name="lenta")

    entradas = ma_rapida.ma_crossed_above(ma_lenta)
    salidas = ma_rapida.ma_crossed_below(ma_lenta)

    portfolio = vbt.Portfolio.from_signals(
        close=close,
        entries=entradas,
        exits=salidas,
        init_cash=capital_inicial,
        fees=comision,
        freq="1D",  # anualización de Sharpe/Sortino (VectorBT usa 365 días)
    )
    return portfolio, close, ma_rapida, ma_lenta, entradas, salidas


# ─────────────────────────────────────────────────────────────────────────────
# 3) HELPERS DE FORMATO
# ─────────────────────────────────────────────────────────────────────────────

def _serie(x) -> pd.Series:
    """VectorBT devuelve Series/df con una columna por combinación de
    parámetros; aquí siempre hay una → se aplana a pd.Series."""
    if isinstance(x, pd.DataFrame):
        return x.iloc[:, 0]
    return x


def _escalar(x) -> float:
    s = _serie(x)
    return float(s.iloc[0]) if isinstance(s, pd.Series) else float(s)


def _ancho_completo() -> dict:
    """Kwargs para que gráficos/tablas ocupen todo el ancho en cualquier
    versión de Streamlit: >=1.49 usa width='stretch' (use_container_width
    está deprecado y se elimina tras 2025-12-31); versiones anteriores usan
    use_container_width=True."""
    try:
        mayor, menor = st.__version__.split(".")[:2]
        if (int(mayor), int(menor)) >= (1, 49):
            return {"width": "stretch"}
    except (ValueError, AttributeError):
        pass
    return {"use_container_width": True}


# ─────────────────────────────────────────────────────────────────────────────
# 4) CAPA DE RENDERIZADO (UI)
# ─────────────────────────────────────────────────────────────────────────────

def render_kpis(portfolio: vbt.Portfolio, close: pd.Series) -> None:
    """Fila de métricas clave: retorno, Sharpe, drawdown y nº de operaciones."""
    retorno = _escalar(portfolio.total_return()) * 100
    # Buy & hold calculado desde precios (compatible con cualquier versión de
    # VectorBT OSS; portfolio.buy_and_hold_return() solo existe en la versión Pro)
    buy_hold = (close.iloc[-1] / close.iloc[0] - 1.0) * 100
    sharpe = _escalar(portfolio.sharpe_ratio())
    max_dd = _escalar(portfolio.max_drawdown()) * 100
    n_trades = int(_escalar(portfolio.trades.count()))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "📈 Retorno Total",
        f"{retorno:,.2f}%",
        delta=f"{retorno - buy_hold:,.2f}% vs Buy&Hold",
        help="Retorno neto de la estrategia. El delta compara con comprar y mantener.",
    )
    c2.metric(
        "⚖️ Ratio de Sharpe",
        f"{sharpe:,.2f}",
        help="Retorno por unidad de riesgo, anualizado (VectorBT anualiza con 365 días).",
    )
    c3.metric(
        "📉 Max Drawdown",
        f"{max_dd:,.2f}%",
        help="Máxima caída desde un pico de la curva de equidad (negativo = pérdida).",
    )
    c4.metric("🔁 Operaciones", f"{n_trades:,}", help="Número total de operaciones cerradas.")


def construir_grafico(
    df: pd.DataFrame,
    close: pd.Series,
    ma_rapida: vbt.MA,
    ma_lenta: vbt.MA,
    entradas,
    salidas,
    equity: pd.Series,
) -> go.Figure:
    """Figura Plotly con precio+señales+medias, equidad vs buy&hold y volumen."""
    ent = _serie(entradas).astype(bool)
    sal = _serie(salidas).astype(bool)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.50, 0.28, 0.22], vertical_spacing=0.04,
        subplot_titles=("Precio, medias móviles y señales",
                        "Curva de equidad vs Buy & Hold",
                        "Volumen"),
    )

    # Fila 1: precio, medias y señales de entrada/salida
    fig.add_trace(go.Scatter(x=close.index, y=close, name="Precio",
                             line=dict(color="#4f8fd6", width=1.6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=close.index, y=_serie(ma_rapida.ma), name=f"MA rápida",
                             line=dict(color="#ffb74d", width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=close.index, y=_serie(ma_lenta.ma), name=f"MA lenta",
                             line=dict(color="#9575cd", width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=close.index[ent], y=close[ent], name="Compra",
                             mode="markers", marker=dict(symbol="triangle-up", size=12,
                                                         color="#26a69a", line=dict(width=1, color="#0b6e5f"))),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=close.index[sal], y=close[sal], name="Venta",
                             mode="markers", marker=dict(symbol="triangle-down", size=12,
                                                         color="#ef5350", line=dict(width=1, color="#8e2620"))),
                  row=1, col=1)

    # Fila 2: equidad de la estrategia vs buy & hold
    fig.add_trace(go.Scatter(x=equity.index, y=equity, name="Estrategia",
                             line=dict(color="#26a69a", width=1.8), fill="tozeroy",
                             fillcolor="rgba(38,166,154,0.08)"), row=2, col=1)
    bh = equity.iloc[0] * close / close.iloc[0]
    fig.add_trace(go.Scatter(x=bh.index, y=bh, name="Buy & Hold",
                             line=dict(color="#9aa5b1", width=1.4, dash="dot")), row=2, col=1)

    # Fila 3: volumen
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volumen",
                         marker_color="#7e8b9a", opacity=0.65), row=3, col=1)

    fig.update_layout(
        height=820, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(l=10, r=10, t=80, b=10),
    )
    fig.update_yaxes(title_text="Precio", row=1, col=1)
    fig.update_yaxes(title_text="Equidad", row=2, col=1)
    fig.update_yaxes(title_text="Volumen", row=3, col=1)
    return fig


def render_stats(portfolio: vbt.Portfolio) -> None:
    """Tabla completa de pf.stats() con formato limpio."""
    try:
        stats = portfolio.stats()
    except Exception:
        stats = pd.Series({
            "Total Return [%]": _escalar(portfolio.total_return()) * 100,
            "Sharpe Ratio": _escalar(portfolio.sharpe_ratio()),
            "Max Drawdown [%]": _escalar(portfolio.max_drawdown()) * 100,
            "Total Trades": int(_escalar(portfolio.trades.count())),
        })
    def _fmt(v) -> str:
        # pf.stats() mezcla floats, Timestamps, Timedeltas y bools; una sola
        # columna de texto evita los errores de serializacion Arrow y permite
        # un formato legible por tipo.
        if isinstance(v, (bool, np.bool_)):
            return str(v)
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        if isinstance(v, (float, np.floating)):
            return "—" if pd.isna(v) else f"{v:,.4f}".rstrip("0").rstrip(".")
        return str(v)

    tabla = pd.DataFrame({"Métrica": stats.index,
                          "Valor": [_fmt(v) for v in stats.values]})
    st.dataframe(tabla, hide_index=True, **_ancho_completo())


# Nombres exactos de trades.records_readable en VectorBT 0.27
COLUMNAS_TRADES = [
    "Column", "Size", "Entry Timestamp", "Avg Entry Price",
    "Exit Timestamp", "Avg Exit Price", "PnL", "Return", "Direction", "Status",
]


def render_trades(portfolio: vbt.Portfolio) -> None:
    """Historial de operaciones, línea por línea, con exportación a CSV."""
    trades = portfolio.trades.records_readable.copy()
    columnas = [c for c in COLUMNAS_TRADES if c in trades.columns]
    if columnas:
        trades = trades[columnas]
    st.caption(f"{len(trades)} operaciones registradas (orden de ejecución).")
    st.dataframe(trades, hide_index=True, height=480, **_ancho_completo())
    st.download_button(
        "⬇️ Descargar historial completo (CSV)",
        data=trades.to_csv(index=False).encode("utf-8"),
        file_name="trades_backtest.csv",
        mime="text/csv",
        **_ancho_completo(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5) UI PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Backtesting Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("📊 Dashboard de Backtesting — Cruce de Medias Móviles")
    st.caption(
        "Motor vectorial VectorBT · datos de Yahoo Finance · "
        "configura la estrategia en la barra lateral y ejecuta el backtest."
    )

    # ── Sidebar: parámetros ──────────────────────────────────────────────
    with st.sidebar:
        st.header("⚙️ Configuración")

        ticker = st.text_input(
            "Ticker (Yahoo Finance)",
            value="AAPL",
            help="Cualquier símbolo de Yahoo Finance: acciones (AAPL, SAN.MC), "
                 "índices (^IBEX), cripto (BTC-USD)…",
        ).strip().upper()

        hoy = date.today()
        inicio = st.date_input("Fecha de inicio", value=hoy - timedelta(days=365 * 3),
                               max_value=hoy)
        fin = st.date_input("Fecha de fin", value=hoy, max_value=hoy)

        st.subheader("Estrategia: cruce de medias")
        tipo_ma = st.selectbox("Tipo de media móvil", ["SMA", "EMA"],
                               help="SMA = media simple · EMA = media exponencial.")
        rapido = st.number_input("Período rápido", min_value=2, max_value=200,
                                 value=20, step=1)
        lento = st.number_input("Período lento", min_value=3, max_value=400,
                                value=50, step=1)

        with st.expander("Parámetros avanzados"):
            capital = st.number_input("Capital inicial ($)", min_value=100.0,
                                      value=10_000.0, step=500.0)
            comision = st.slider("Comisión por operación (%)", min_value=0.0,
                                 max_value=0.5, value=0.1, step=0.01,
                                 help="Coste aplicado a cada entrada y salida.") / 100.0

        ejecutar = st.button("🚀 Ejecutar Backtest", type="primary", use_container_width=True)

    # ── Validaciones previas ─────────────────────────────────────────────
    if ejecutar:
        if not ticker:
            st.error("Introduce un ticker (ej. AAPL o BTC-USD).")
            st.stop()
        if inicio >= fin:
            st.error("La fecha de inicio debe ser anterior a la fecha de fin.")
            st.stop()
        if rapido >= lento:
            st.error("El período rápido debe ser menor que el período lento "
                     f"(ahora: rápido={rapido}, lento={lento}).")
            st.stop()

    # ── Ejecución: descarga + backtest ───────────────────────────────────
    if ejecutar:
        try:
            with st.spinner(f"Descargando '{ticker}' de Yahoo Finance…"):
                df = descargar_datos(ticker, inicio, fin)
        except Exception as exc:
            st.error(f"❌ Error descargando datos: {exc}")
            st.stop()

        if len(df) < lento + 5:
            st.error(
                f"Solo hay {len(df)} velas para '{ticker}' en el rango elegido; "
                f"la media lenta necesita al menos {lento + 5}. Amplía el rango "
                "o reduce los períodos."
            )
            st.stop()

        try:
            with st.spinner("Ejecutando simulación con VectorBT…"):
                portfolio, close, ma_rapida, ma_lenta, entradas, salidas = (
                    ejecutar_backtest(df, tipo_ma, rapido, lento, capital, comision))
        except Exception as exc:
            st.error(f"❌ Error ejecutando el backtest: {exc}")
            st.stop()

        equity = _serie(portfolio.value())
        st.session_state["resultado"] = {
            "df": df, "close": close, "ma_rapida": ma_rapida, "ma_lenta": ma_lenta,
            "entradas": entradas, "salidas": salidas,
            "portfolio": portfolio, "equity": equity,
            "meta": {"ticker": ticker, "tipo_ma": tipo_ma, "rapido": rapido,
                     "lento": lento, "capital": capital, "comision": comision,
                     "inicio": inicio.isoformat(), "fin": fin.isoformat()},
        }

    # ── Panel principal (persiste el último resultado en session_state) ──
    if "resultado" not in st.session_state:
        st.info("👈 Configura el ticker, el rango de fechas y los períodos de las "
                "medias móviles, y pulsa **Ejecutar Backtest**.")
        return

    r = st.session_state["resultado"]
    meta = r["meta"]
    st.subheader(f"{meta['ticker']} · {meta['tipo_ma']}({meta['rapido']}/{meta['lento']}) "
                 f"· {meta['inicio']} → {meta['fin']} · capital ${meta['capital']:,.0f}")

    render_kpis(r["portfolio"], r["close"])

    tab_stats, tab_grafico, tab_trades = st.tabs(
        ["📋 Métricas detalladas", "📈 Gráfico interactivo", "🧾 Historial de operaciones"]
    )
    with tab_stats:
        render_stats(r["portfolio"])
    with tab_grafico:
        st.plotly_chart(
            construir_grafico(r["df"], r["close"], r["ma_rapida"], r["ma_lenta"],
                              r["entradas"], r["salidas"], r["equity"]),
            **_ancho_completo(),
        )
    with tab_trades:
        render_trades(r["portfolio"])


if __name__ == "__main__":
    main()
