import numpy as np
import pandas as pd
from .indicators import ma_series, atr, series_falling, series_rising, adx

def _safe_prev_value(series, n, default=np.nan):
    L = len(series)
    if L == 0: return default
    if 0 <= n < L and pd.notna(series.iloc[n]): return float(series.iloc[n])
    end = min(max(n, 0), L - 1)
    valid_slice = series.iloc[: end + 1].dropna()
    if len(valid_slice) > 0: return float(valid_slice.iloc[-1])
    return default

def detect_ma_sabres(df, ma_type="TEMA", length_buy=50, count_buy=20, length_sell=50, count_sell=20, atr_len=14,
                     min_slope_mult=0.0, vol_lookback=0, vol_mult=1.0, adx_threshold=0.0, adx_length=14):
    ma_buy = ma_series(df, ma_type, length_buy)
    ma_sell = ma_series(df, ma_type, length_sell)
    atr14 = atr(df, atr_len)

    fl = series_falling(ma_buy, count_buy)
    rs = series_rising (ma_sell, count_sell)

    if min_slope_mult > 0:
        buy_slope  = (ma_buy  - ma_buy.shift(count_buy)).abs()  / max(count_buy, 1)
        sell_slope = (ma_sell - ma_sell.shift(count_sell)).abs() / max(count_sell, 1)
        fl = fl & (buy_slope  >= atr14 * min_slope_mult)
        rs = rs & (sell_slope >= atr14 * min_slope_mult)

    up_cond = fl.shift(1).fillna(False) & (ma_buy > ma_buy.shift(1))
    dn_cond = rs.shift(1).fillna(False) & (ma_sell < ma_sell.shift(1))

    if vol_lookback > 0 and "volume" in df.columns:
        vol_ma  = df["volume"].rolling(vol_lookback, min_periods=1).mean()
        vol_ok  = df["volume"] >= vol_ma * vol_mult
        up_cond = up_cond & vol_ok
        dn_cond = dn_cond & vol_ok

    if adx_threshold > 0:
        adx_val  = adx(df, adx_length)
        trending = adx_val >= adx_threshold
        up_cond  = up_cond & trending
        dn_cond  = dn_cond & trending

    times = df.index
    if len(times) >= 2:
        step_seconds = np.median(np.diff(times.values).astype('timedelta64[s]').astype(np.int64))
        step = pd.to_timedelta(int(step_seconds), unit='s')
        if step <= pd.Timedelta(0): step = pd.Timedelta(hours=1)
    else:
        step = pd.Timedelta(hours=1)

    recent_range = (df["high"] - df["low"]).tail(50)
    fallback_atr = float(np.nanmedian(recent_range)) / 14.0 if len(recent_range) else 0.0
    if not np.isfinite(fallback_atr) or fallback_atr <= 0:
        fallback_atr = 1e-6

    def n_to_time(k):
        if k < len(times): return times[k]
        return times[-1] + (k - (len(times) - 1)) * step

    up_points, dn_points = [], []

    up_idx = np.where(up_cond.values)[0] if len(up_cond) else []
    for n in up_idx:
        if n - 1 < 0 or n >= len(df): continue
        low1 = float(df["low"].iloc[n - 1])
        a = _safe_prev_value(atr14, n, default=fallback_atr)
        x_idx = [n - 1, n + (length_buy // 2 - 1), n + length_buy, n + (length_buy // 2 - 1), n - 1]
        x = [n_to_time(k) for k in x_idx]
        y = [low1 - a / 15.0, low1 + a / 2.5, low1 + 2 * a, low1 + a / 2.5, low1 + a / 15.0]
        up_points.append({"n": n, "xy": (x, y), "circle": (times[n], low1)})

    dn_idx = np.where(dn_cond.values)[0] if len(dn_cond) else []
    for n in dn_idx:
        if n - 1 < 0 or n >= len(df): continue
        high1 = float(df["high"].iloc[n - 1])
        a = _safe_prev_value(atr14, n, default=fallback_atr)
        x_idx = [n - 1, n + (length_sell // 2 - 1), n + length_sell, n + (length_sell // 2 - 1), n - 1]
        x = [n_to_time(k) for k in x_idx]
        y = [high1 + a / 15.0, high1 - a / 2.5, high1 - 2 * a, high1 - a / 2.5, high1 - a / 15.0]
        dn_points.append({"n": n, "xy": (x, y), "circle": (times[n], high1)})

    return {"ma": ma_buy, "up_points": up_points, "dn_points": dn_points}

def res_to_dfs(res, sname="UNKNOWN"):
    df_ma = res["ma"].to_frame(name="ma")
    df_ma["sname"] = sname

    rows = []
    for side, points in [("buy", res.get("up_points", [])),
                         ("sell", res.get("dn_points", []))]:
        for p in points:
            dt, price = p["circle"]
            rows.append({
                "datetime": pd.to_datetime(dt).tz_convert("UTC"),
                "ma_signal": side,
                "ma_level": price
            })
    df_signals = pd.DataFrame(rows)
    return df_ma, df_signals

