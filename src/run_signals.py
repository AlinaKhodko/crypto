#!/usr/bin/env python3
import os, json, warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from datetime import datetime, timezone

from .config import ARG_START_DATE, END_DATE, START_DATE_UPLOAD
from .db import load_dataframes, insert_last_signal
from .sabres import detect_ma_sabres, res_to_dfs
from .supertrend import compute_supertrend, signals_from_supertrend
from .telegram import notify_telegram
        
def _ensure_utc(ts_like):
    ts = pd.to_datetime(ts_like)
    return ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")

def main():
    snames, values, strategies = load_dataframes()

    # parse strategies.params JSON once
    if isinstance(strategies.loc[strategies.index[0], "params"], str):
        strategies = strategies.copy()
        strategies["params_dict"] = strategies["params"].apply(json.loads)
    else:
        strategies["params_dict"] = strategies["params"]

    arg_start = _ensure_utc(ARG_START_DATE) if ARG_START_DATE else None
    end_dt    = _ensure_utc(END_DATE)

    # iterate ONE symbol at a time or all; here: all in table
    for sname in strategies["sname"].unique():
        df_sym = (values[values["sname"] == sname]
                  .sort_values("datetime")
                  .reset_index(drop=True))
        if df_sym.empty:
            continue

        # restrict to date range (for rolling simulation)
        df_sym["datetime"] = pd.to_datetime(df_sym["datetime"], utc=True)
        mask_period = (df_sym["datetime"] <= end_dt)
        df_sym_0 = df_sym.loc[mask_period].copy()
        if df_sym_0.empty: 
            continue
            
        # strategies for this symbol
        s_for_sym = strategies[strategies["sname"] == sname]

        # run each strategy
        for s in s_for_sym["name"].unique():
            strategy_data = s_for_sym[s_for_sym["name"] == s].iloc[0]
            p = strategy_data["params_dict"]
            length_sell = int(p.get("length_sell", 0))
            length_buy  = int(p.get("length_buy", 0))
            count_sell  = int(p.get("count_sell", 0))
            count_buy   = int(p.get("count_buy", 0))
            ma_type     = p.get("ma_type", "TEMA")
            supertrend_enabled = bool(p.get("supertrend_enabled", False))
            atr_period  = int(p.get("supertrend", {}).get("atr_period", 14)) if supertrend_enabled else None
            multiplier  = float(p.get("supertrend", {}).get("multiplier", 2.0)) if supertrend_enabled else None

            # rolling window size: take the max driver (safe default)
            window = max(length_sell, length_buy, count_sell, count_buy, atr_period or 0)+3
            if arg_start is not None:
                # find arg_start in df_sym_0
                df_sym_0 = df_sym_0.sort_values("datetime").reset_index(drop=True)
            
                # position of arg_start in the index (nearest <=)
                pos = df_sym_0.index[df_sym_0["datetime"] <= arg_start].max()
                lower = max(0, pos - window)
                df_sym = df_sym_0.iloc[lower:].copy()
            else:
                df_sym = df_sym_0.copy()
                    # index by datetime
            df_sym = df_sym.set_index("datetime").sort_index()
            
            if len(df_sym) <= window:
                print(f"{sname}/{s}: not enough rows (need > {window}, have {len(df_sym)})")
                continue

            # run indicators once on the full working window
            res = detect_ma_sabres(
                df_sym,
                ma_type=ma_type,
                length_buy=length_buy+1, count_buy=count_buy,
                length_sell=length_sell, count_sell=count_sell
            )
            _, ma_signals = res_to_dfs(res, sname)
            if ma_signals.empty:
                continue

            ma_signals = ma_signals.set_index("datetime").sort_index()

            # filter to signals at or after arg_start
            if arg_start is not None:
                ma_signals = ma_signals[ma_signals.index >= arg_start]
            if ma_signals.empty:
                continue

            if supertrend_enabled:
                st = compute_supertrend(df_sym, atr_period=atr_period, multiplier=multiplier, use_wilder_atr=True)
                st_signal = signals_from_supertrend(st, sname)
                summary = ma_signals.merge(st_signal[["side"]], left_index=True, right_index=True, how="left")
                summary["ma_signal"] = np.where(
                    (summary["ma_signal"] == "sell") & (summary["side"] == "buy"),
                    np.nan,
                    summary["ma_signal"]
                )
            else:
                summary = ma_signals[["ma_signal"]].copy()
                summary["sname"] = sname

            for dt, row in summary.iterrows():
                if pd.isna(row["ma_signal"]):
                    continue
                signal_row = pd.Series({
                    "datetime": dt,
                    "sname": sname,
                    "strategy": s,
                    "ma_signal": row["ma_signal"],
                })
                insert_last_signal(signal_row)
                notify_telegram(dt, sname, row["ma_signal"], s)

if __name__ == "__main__":
    main()

