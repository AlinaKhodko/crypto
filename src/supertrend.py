import numpy as np
import pandas as pd

def _wilder_rma(series: pd.Series, length: int) -> pd.Series:
    alpha = 1.0 / length
    return series.ewm(alpha=alpha, adjust=False).mean()

def _atr(df: pd.DataFrame, length: int, wilder: bool = True) -> pd.Series:
    high, low, close = df["high"], df["low"], df["value"]
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    return _wilder_rma(tr, length) if wilder else tr.rolling(length, min_periods=length).mean()

def compute_supertrend(df: pd.DataFrame, atr_period: int = 10, multiplier: float = 3.0,
                       use_wilder_atr: bool = False, source: str = "ohlc4", show_signals: bool = True):
    out = df.copy()
    if source == "hl2":
        src = (out["high"] + out["low"]) / 2.0
    elif source == "ohlc4":
        src = (out["open"] + out["high"] + out["low"] + out["value"]) / 4.0
    else:
        src = out["value"]

    atr_wilder = _atr(out, atr_period, wilder=use_wilder_atr)
    atr = atr_wilder

    up = src - (multiplier * atr)
    dn = src + (multiplier * atr)

    up1 = up.shift(1)
    dn1 = dn.shift(1)
    prev_close = out["value"].shift(1)

    up_line = np.where(prev_close > up1, np.maximum(up, up1), up)
    dn_line = np.where(prev_close < dn1, np.minimum(dn, dn1), dn)

    trend = np.full(len(out), np.nan, dtype=float)
    trend[0] = 1.0
    for i in range(1, len(out)):
        t = trend[i-1]
        c = out["value"].iloc[i]
        if (t == -1) and (c > dn1.iloc[i]): t = 1.0
        elif (t == 1) and (c < up1.iloc[i]): t = -1.0
        trend[i] = t

    trend = pd.Series(trend, index=out.index).astype(int)
    st_up = pd.Series(up_line, index=out.index)
    st_dn = pd.Series(dn_line, index=out.index)

    out["st_trend"] = trend
    out["st_up"] = st_up.where(trend == 1, np.nan)
    out["st_dn"] = st_dn.where(trend == -1, np.nan)

    if show_signals:
        out["st_buy"] = (trend == 1) & (trend.shift(1) == -1)
        out["st_sell"] = (trend == -1) & (trend.shift(1) == 1)
    return out

def signals_from_supertrend(st: pd.DataFrame, sname="X"):
    return st.assign(
        side=st["st_trend"].map({1: "buy", -1: "sell"}),
        price=np.where(st["st_trend"] == 1, st["st_up"], st["st_dn"]),
        sname=sname
    )[["sname", "side", "price"]].dropna(subset=["side"])

