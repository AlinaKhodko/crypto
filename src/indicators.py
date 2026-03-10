import numpy as np
import pandas as pd

def sma(s, length): return s.rolling(length, min_periods=length).mean()
def ema(s, length): return s.ewm(span=length, adjust=False).mean()

def rma(s, length):
    return s.ewm(alpha=1.0 / length, adjust=False).mean()

def wma(s, length):
    w = np.arange(1, length + 1)
    return s.rolling(length).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)

def hma(s, length):
    l1 = int(length)
    l2 = max(1, l1 // 2)
    l3 = int(np.sqrt(l1))
    wma1 = wma(s, l2); wma2 = wma(s, l1)
    raw = 2 * wma1 - wma2
    return wma(raw, max(1, l3))

def vwma(close, volume, length):
    pv = close * volume
    return pv.rolling(length).sum() / volume.rolling(length).sum()

def dema(s, length):
    e1 = ema(s, length); e2 = ema(e1, length)
    return 2 * e1 - e2

def tema(s, length):
    e1 = ema(s, length); e2 = ema(e1, length); e3 = ema(e2, length)
    return 3*e1 - 3*e2 + e3

def ma_series(df, ma_type="TEMA", length=50):
    c = df["value"]; m = ma_type.upper()
    if m == "SMA":  return sma(c, length)
    if m == "EMA":  return ema(c, length)
    if m in ("SMMA","RMA","SMMA (RMA)"): return rma(c, length)
    if m in ("HULLMA","HULL"):          return hma(c, length)
    if m == "WMA":  return wma(c, length)
    if m == "VWMA": return vwma(df["value"], df["volume"], length)
    if m == "DEMA": return dema(c, length)
    if m == "TEMA": return tema(c, length)
    if m == "NONE": return pd.Series(np.nan, index=df.index)
    raise ValueError(f"Unknown ma_type: {ma_type}")

def atr(df, length=14):
    high, low, close = df["high"], df["low"], df["value"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low),(high - prev_close).abs(),(low - prev_close).abs()], axis=1).max(axis=1)
    return rma(tr, length)

def series_falling(s, n):
    d = s.diff()
    cond = d < 0
    return cond.rolling(n).apply(lambda x: 1.0 if np.all(x) else 0.0, raw=True).astype(bool)

def series_rising(s, n):
    d = s.diff()
    cond = d > 0
    return cond.rolling(n).apply(lambda x: 1.0 if np.all(x) else 0.0, raw=True).astype(bool)

def adx(df, length=14):
    high, low, close = df["high"], df["low"], df["value"]
    up_move   = high - high.shift(1)
    down_move = low.shift(1) - low
    dm_plus  = pd.Series(np.where((up_move > down_move)  & (up_move > 0),   up_move,   0.0), index=df.index)
    dm_minus = pd.Series(np.where((down_move > up_move)  & (down_move > 0), down_move, 0.0), index=df.index)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr_s    = rma(tr, length)
    di_plus  = 100 * rma(dm_plus,  length) / atr_s
    di_minus = 100 * rma(dm_minus, length) / atr_s
    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    return rma(dx.fillna(0), length)

