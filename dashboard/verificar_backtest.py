#!/usr/bin/env python3
"""Verificación del sistema de backtesting — ¿cómo sé que funciona?

Cada bloque devuelve checks estructurados (dataclass Check) para dos consumidores:
  - CLI:      .venv/bin/python dashboard/verificar_backtest.py [--offline]
  - Streamlit: dashboard/pages/2_bateria_de_tests.py importa estas funciones

NIVEL 1 — CORRECTITUD DEL MOTOR (respuesta conocida)
  V1. Escenario sintético calculado a mano (señales, precios y PnL exactos).
  V2. Invariantes contables (valor final = capital·(1+retorno); fees nunca suman).
  V3. Doble motor independiente: bucle pandas vs VectorBT sobre datos reales.

NIVEL 2 — VALIDEZ METODOLÓGICA (diagnóstico, tipo="aviso")
  V4. Honestidad de ejecución (cierre misma vela vs apertura siguiente).
  V5. Sensibilidad paramétrica / detector de overfitting.
  V6. Out-of-sample 60/40.

Exit code 0 = sin fallos de correctitud (los avisos metodológicos no fallan).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd
import vectorbt as vbt

# ═══════════════════════════════════════════════════════════════════════════
# Estructura de resultados
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class Check:
    nombre: str
    ok: bool
    detalle: str = ""
    tipo: str = "correctitud"   # correctitud | aviso


@dataclass
class Bloque:
    titulo: str
    checks: List[Check] = field(default_factory=list)
    lineas: List[str] = field(default_factory=list)   # contexto adicional


def _serie(x) -> pd.Series:
    if isinstance(x, pd.DataFrame):
        return x.iloc[:, 0]
    return x


def _f(x) -> float:
    """Escalar robusto: VectorBT devuelve Series (1 col) o escalar según método."""
    if hasattr(x, "iloc"):
        return float(x.iloc[0])
    return float(x)


# ═══════════════════════════════════════════════════════════════════════════
# Motor de referencia independiente (bucle ingenuo de pandas — V3)
# ═══════════════════════════════════════════════════════════════════════════

def backtest_bucle(close: pd.Series, rapido: int, lento: int,
                   capital: float, comision: float):
    """Backtester clásico imperativo, SIN vectorización, SIN vectorbt.

    Misma semántica que la app: cruce estricto arriba → compra todo el cash al
    cierre de esa vela; cruce estricto abajo → vende todo al cierre. Comisión
    en ambos lados. Devuelve (trades_cerrados, equidad_final).
    """
    f = close.rolling(rapido).mean()
    s = close.rolling(lento).mean()
    en_pos = False
    cash, unidades = capital, 0.0
    entrada = None
    trades = []
    for i in range(1, len(close)):
        sube = f.iloc[i] > s.iloc[i] and f.iloc[i - 1] < s.iloc[i - 1]
        baja = f.iloc[i] < s.iloc[i] and f.iloc[i - 1] > s.iloc[i - 1]
        if sube and not en_pos and not np.isnan(s.iloc[i]):
            unidades = cash / (close.iloc[i] * (1 + comision))
            cash = 0.0
            entrada = (close.index[i], float(close.iloc[i]))
            en_pos = True
        elif baja and en_pos:
            cash = unidades * close.iloc[i] * (1 - comision)
            trades.append((entrada[0], entrada[1], close.index[i], float(close.iloc[i])))
            unidades, en_pos, entrada = 0.0, False, None
    equidad = cash + unidades * float(close.iloc[-1])
    return trades, float(equidad)


def _cruces(close: pd.Series, rapido: int, lento: int, direccion: str) -> pd.Series:
    f = vbt.MA.run(close, window=rapido, short_name="f")
    s = vbt.MA.run(close, window=lento, short_name="s")
    if direccion == "arriba":
        return _serie(f.ma_crossed_above(s)).astype(bool)
    return _serie(f.ma_crossed_below(s)).astype(bool)


# ═══════════════════════════════════════════════════════════════════════════
# NIVEL 1
# ═══════════════════════════════════════════════════════════════════════════

def checks_v1() -> Bloque:
    """Escenario sintético con respuesta calculada a mano."""
    # SMA(2)/SMA(4), cruce ESTRICTO (convención VectorBT: prev < otro y ahora >).
    # En i=3 las medias empatan → no hay cruce en i=4. Cruces en papel:
    #   compra i=7 (95), venta i=11 (105) → retorno exacto 105/95−1 = 2/19.
    precios = [100, 100, 100, 100, 90, 80, 85, 95, 110, 120, 110, 105, 80]
    idx = pd.date_range("2024-01-01", periods=len(precios), freq="D")
    close = pd.Series(precios, index=idx, dtype=float)

    rapida = vbt.MA.run(close, window=2, short_name="f")
    lenta = vbt.MA.run(close, window=4, short_name="s")
    entradas = _serie(rapida.ma_crossed_above(lenta)).astype(bool)
    salidas = _serie(rapida.ma_crossed_below(lenta)).astype(bool)

    b = Bloque("V1 · Escenario sintético (respuesta calculada a mano)")
    b.checks = [
        Check("señal de compra exactamente en i=7 (cierre 95)",
              list(close.index[entradas]) == [idx[7]],
              f"observed={list(close.index[entradas])}"),
        Check("señal de venta exactamente en i=11 (cierre 105)",
              list(close.index[salidas]) == [idx[11]],
              f"observed={list(close.index[salidas])}"),
    ]

    pf = vbt.Portfolio.from_signals(close, entradas, salidas,
                                    init_cash=10_000, fees=0.0, freq="1D")
    tr = pf.trades.records_readable
    b.checks += [
        Check("nº de operaciones = 1", _f(pf.trades.count()) == 1,
              f"observed={_f(pf.trades.count()):.0f}"),
        Check("retorno total = +10.5263% (cálculo manual exacto: 2/19)",
              abs(_f(pf.total_return()) - 2 / 19) < 1e-9,
              f"observed={_f(pf.total_return()):.6%}"),
        Check("precio de entrada 95", list(tr["Avg Entry Price"].round(6)) == [95.0]),
        Check("precio de salida 105", list(tr["Avg Exit Price"].round(6)) == [105.0]),
    ]
    return b


def checks_v2(close: pd.Series) -> Bloque:
    """Invariantes contables."""
    pf0 = vbt.Portfolio.from_signals(close, _cruces(close, 20, 50, "arriba"),
                                     _cruces(close, 20, 50, "abajo"),
                                     init_cash=10_000, fees=0.0, freq="1D")
    pfF = vbt.Portfolio.from_signals(close, _cruces(close, 20, 50, "arriba"),
                                     _cruces(close, 20, 50, "abajo"),
                                     init_cash=10_000, fees=0.001, freq="1D")
    valor_final = float(_serie(pf0.value()).iloc[-1])
    b = Bloque("V2 · Invariantes contables")
    b.checks = [
        Check("valor final = capital·(1+retorno total)",
              abs(valor_final - 10_000 * (1 + _f(pf0.total_return()))) < 1e-6,
              f"{valor_final:,.2f} vs {10_000 * (1 + _f(pf0.total_return())):,.2f}"),
        Check("las comisiones nunca aumentan el retorno",
              _f(pfF.total_return()) <= _f(pf0.total_return()) + 1e-12,
              f"sin fees {_f(pf0.total_return()):.4%} · con fees {_f(pfF.total_return()):.4%}"),
    ]
    return b


def checks_v3(close: pd.Series, rapido: int = 20, lento: int = 50) -> Bloque:
    """Doble motor: VectorBT vs bucle pandas independiente."""
    comision = 0.001
    pf = vbt.Portfolio.from_signals(close, _cruces(close, rapido, lento, "arriba"),
                                    _cruces(close, rapido, lento, "abajo"),
                                    init_cash=10_000, fees=comision, freq="1D")
    tr = pf.trades.records_readable
    n_abiertas = int((tr["Status"] == "Open").sum())
    tr = tr[tr["Status"] == "Closed"]   # el bucle solo registra trades cerrados
    vbt_trades = [(r["Entry Timestamp"], r["Avg Entry Price"],
                   r["Exit Timestamp"], r["Avg Exit Price"]) for _, r in tr.iterrows()]
    eq_vbt = float(_serie(pf.value()).iloc[-1])
    trades_bucle, eq_bucle = backtest_bucle(close, rapido, lento, 10_000, comision)

    b = Bloque("V3 · Doble motor: VectorBT vs bucle pandas independiente")
    b.lineas = [f"posición abierta al cierre: {n_abiertas} (su valor lo cubre el "
                "check de equidad final)"]
    coinciden = len(vbt_trades) == len(trades_bucle) and all(
        te == tb[0] and abs(pe - tb[1]) < 1e-9 and ts == tb[2] and abs(ps - tb[3]) < 1e-9
        for (te, pe, ts, ps), tb in zip(vbt_trades, trades_bucle))
    b.checks = [
        Check("mismo número de trades", len(vbt_trades) == len(trades_bucle),
              f"vbt={len(vbt_trades)} · bucle={len(trades_bucle)}"),
        Check("mismas entradas/salidas (fecha y precio) en TODOS los trades", coinciden),
        Check("misma equidad final (tolerancia 1e-6 relativa)",
              abs(eq_vbt - eq_bucle) < 1e-6 * eq_vbt,
              f"vbt={eq_vbt:,.4f} · bucle={eq_bucle:,.4f}"),
    ]
    return b


# ═══════════════════════════════════════════════════════════════════════════
# NIVEL 2
# ═══════════════════════════════════════════════════════════════════════════

def bloque_v4(df: pd.DataFrame, close: pd.Series, rapido: int = 20,
              lento: int = 50) -> Bloque:
    """Honestidad de ejecución: cierre misma vela vs apertura siguiente."""
    ent = _cruces(close, rapido, lento, "arriba")
    sal = _cruces(close, rapido, lento, "abajo")
    pf_cierre = vbt.Portfolio.from_signals(close, ent, sal, init_cash=10_000,
                                           fees=0.001, freq="1D")
    ent_realista = ent.shift(1).fillna(False).astype(bool)
    sal_realista = sal.shift(1).fillna(False).astype(bool)
    pf_apertura = vbt.Portfolio.from_signals(close, ent_realista, sal_realista,
                                             price=df["Open"], init_cash=10_000,
                                             fees=0.001, freq="1D")
    r1 = _f(pf_cierre.total_return()) * 100
    r2 = _f(pf_apertura.total_return()) * 100
    b = Bloque("V4 · Honestidad de ejecución")
    b.lineas = [
        f"ejecución al cierre: {r1:+.2f}%  ·  ejecución a apertura siguiente: "
        f"{r2:+.2f}%  ·  diferencia: {r1 - r2:+.2f} pp",
        "el número 'realista' es el que hay que mirar; una brecha grande indica "
        "que parte del resultado es el artefacto de ejecución.",
    ]
    b.checks = [Check("la variante realista se ejecuta sin errores",
                      bool(np.isfinite(r2)), tipo="aviso")]
    return b


def bloque_v5(close: pd.Series, rapido: int = 20, lento: int = 50) -> Bloque:
    """Sensibilidad paramétrica (detector de overfitting)."""
    resultados = {}
    for w_f in range(5, 61, 5):
        f = close.rolling(w_f).mean()
        f_prev = f.shift(1)
        for w_s in range(20, 201, 10):
            if w_f >= w_s:
                continue
            s = close.rolling(w_s).mean()
            s_prev = s.shift(1)
            ent = ((f > s) & (f_prev < s_prev)).fillna(False)
            sal = ((f < s) & (f_prev > s_prev)).fillna(False)
            pf = vbt.Portfolio.from_signals(close, ent, sal, init_cash=10_000,
                                            fees=0.001, freq="1D")
            resultados[(w_f, w_s)] = _f(pf.total_return())

    retornos = pd.Series(resultados)
    elegido = retornos[(rapido, lento)]
    pct = retornos.quantile([0.25, 0.5, 0.75]).tolist()
    positivos = float((retornos > 0).mean()) * 100
    percentil = float((retornos < elegido).mean()) * 100
    vecinos = retornos[[k for k in retornos.index
                        if abs(k[0] - rapido) <= 10 and abs(k[1] - lento) <= 20]]
    vecinos_ok = float((abs(vecinos - elegido) < 0.02).mean()) * 100

    b = Bloque("V5 · Sensibilidad paramétrica (detector de overfitting)")
    b.lineas = [
        f"{len(retornos)} combinaciones f<s · resultado en ({rapido},{lento}): "
        f"{elegido * 100:+.2f}%",
        f"retorno por percentiles 25/50/75: {pct[0]:+.2%} / {pct[1]:+.2%} / {pct[2]:+.2%}",
        f"rango: {retornos.min() * 100:+.1f}% … {retornos.max() * 100:+.1f}% · "
        f"rentables: {positivos:.0f}% · percentil del par elegido: {percentil:.0f}",
    ]
    b.checks = [
        Check(f"vecindario estable (>50% de combos cercanos a ±2pp de ({rapido},{lento}))",
              vecinos_ok >= 50,
              f"{vecinos_ok:.0f}% en ±2pp — isla aislada (curve fitting) o "
              "superficie ruidosa: mira el rango, no el punto", tipo="aviso"),
        Check("más del 30% del espacio paramétrico es rentable", positivos >= 30,
              f"{positivos:.0f}% rentables — casi todo en pérdidas con una isla "
              "verde = parámetros que memorizaron ruido", tipo="aviso"),
    ]
    return b


def bloque_v6(close: pd.Series, rapido: int = 20, lento: int = 50) -> Bloque:
    """Out-of-sample 60/40."""
    corte = int(len(close) * 0.6)
    b = Bloque("V6 · Out-of-sample (60% train / 40% test)")
    for nombre, serie in (("train", close.iloc[:corte]), ("test", close.iloc[corte:])):
        pf = vbt.Portfolio.from_signals(serie, _cruces(serie, rapido, lento, "arriba"),
                                        _cruces(serie, rapido, lento, "abajo"),
                                        init_cash=10_000, fees=0.001, freq="1D")
        r = _f(pf.total_return()) * 100
        bh = (serie.iloc[-1] / serie.iloc[0] - 1) * 100
        b.lineas.append(f"{nombre:5s}: estrategia {r:+8.2f}%  ·  buy&hold {bh:+8.2f}%"
                        f"  ·  {int(_f(pf.trades.count()))} trades")
    b.lineas.append("si el train es dorado y el test un desastre, los parámetros "
                    "memorizaron ruido. Con pocas decenas de trades, los intervalos "
                    "de confianza de CUALQUIER tramo son amplios.")
    return b


# ═══════════════════════════════════════════════════════════════════════════
# Datos y CLI
# ═══════════════════════════════════════════════════════════════════════════

def descargar_para_verificacion(ticker: str = "AAPL", periodo: str = "3y"
                                 ) -> Optional[pd.DataFrame]:
    import yfinance as yf
    df = yf.download(ticker, period=periodo, interval="1d", auto_adjust=True,
                     progress=False, threads=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df.dropna(subset=["Close"])


def _imprimir(b: Bloque) -> None:
    print(f"\n[{b.titulo}]")
    for linea in b.lineas:
        print(f"      {linea}")
    for c in b.checks:
        estado = "✅" if c.ok else ("⚠️ " if c.tipo == "aviso" else "❌")
        print(f"  {estado} {c.nombre}" + (f" — {c.detalle}" if c.detalle else ""))


def main() -> int:
    fallos = 0
    avisos = 0
    print("=" * 72)
    print("VERIFICACIÓN DEL SISTEMA DE BACKTESTING — dashboard/app.py")
    print("=" * 72)

    bloques: List[Bloque] = [checks_v1()]
    offline = "--offline" in sys.argv
    if offline:
        print("\n--offline: saltan las verificaciones con datos reales (V3-V6).")
    else:
        df = descargar_para_verificacion()
        if df is None:
            print("\nSin red/datos de Yahoo: saltan V3-V6 (usar --offline para silenciar).")
        else:
            close = df["Close"]
            print(f"\nAAPL 3y: {len(close)} velas "
                  f"{close.index[0].date()} → {close.index[-1].date()}")
            bloques += [checks_v2(close), checks_v3(close),
                        bloque_v4(df, close), bloque_v5(close), bloque_v6(close)]

    for b in bloques:
        _imprimir(b)
        fallos += sum(1 for c in b.checks if not c.ok and c.tipo == "correctitud")
        avisos += sum(1 for c in b.checks if not c.ok and c.tipo == "aviso")

    print("\n" + "=" * 72)
    print("%s — %d fallos de correctitud, %d avisos metodológicos" % (
        "❌ VERIFICACIÓN CON FALLOS" if fallos else "✅ MOTOR VERIFICADO",
        fallos, avisos))
    print("Nivel 1 (motor correcto) es verificable y queda demostrado arriba.")
    print("Nivel 2 (el resultado 'funciona') nunca es definitivo: un backtest")
    print("es evidencia histórica, no predicción.")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
