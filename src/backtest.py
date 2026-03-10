#!/usr/bin/env python3
"""
Backtesting metrics for MA Sabres signals.

Standalone usage:
    python -m src.backtest

Programmatic usage:
    from src.backtest import compute_metrics
    metrics = compute_metrics(signals_df, ohlcv_df, horizons=[4, 8, 24])
"""
import numpy as np
import pandas as pd


def compute_metrics(signals: pd.DataFrame, ohlcv: pd.DataFrame,
                    horizons: list = [4, 8, 24]) -> pd.DataFrame:
    """
    Compute forward-return metrics for a set of signals.

    Parameters
    ----------
    signals : DataFrame with columns [datetime, ma_signal ('buy'|'sell')]
              datetime must be UTC-aware (or naive UTC).
    ohlcv   : DataFrame indexed by UTC datetime with at least a 'value' column (close price).
    horizons: list of integer hour offsets at which to evaluate the trade.

    Returns
    -------
    DataFrame indexed by horizon with columns:
        n_signals, win_rate, avg_win_pct, avg_loss_pct, expectancy_pct, sharpe
    """
    if signals.empty or ohlcv.empty:
        return pd.DataFrame()

    # Ensure ohlcv index is sorted
    ohlcv = ohlcv.sort_index()

    rows = []
    for _, sig in signals.iterrows():
        dt     = pd.to_datetime(sig["datetime"], utc=True)
        signal = sig["ma_signal"]

        # Entry: nearest bar at or after signal datetime
        future = ohlcv[ohlcv.index >= dt]
        if future.empty:
            continue
        entry_price = float(future.iloc[0]["value"])

        for h in horizons:
            exit_dt   = dt + pd.Timedelta(hours=h)
            exit_bars = ohlcv[ohlcv.index >= exit_dt]
            if exit_bars.empty:
                continue
            exit_price = float(exit_bars.iloc[0]["value"])

            ret = (exit_price - entry_price) / entry_price
            if signal == "sell":
                ret = -ret  # profit when price falls

            rows.append({"horizon": h, "return": ret})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    records = []
    for h in horizons:
        sub = df[df["horizon"] == h]["return"].dropna()
        if sub.empty:
            continue
        wins   = sub[sub > 0]
        losses = sub[sub <= 0]
        win_rate    = len(wins) / len(sub)
        avg_win     = float(wins.mean())   if len(wins)   else 0.0
        avg_loss    = float(losses.mean()) if len(losses) else 0.0
        expectancy  = win_rate * avg_win + (1 - win_rate) * avg_loss
        sharpe      = float(sub.mean() / sub.std() * np.sqrt(8760 / h)) if sub.std() > 0 else 0.0
        records.append({
            "horizon_h":     h,
            "n_signals":     len(sub),
            "win_rate":      round(win_rate, 4),
            "avg_win_pct":   round(avg_win  * 100, 3),
            "avg_loss_pct":  round(avg_loss * 100, 3),
            "expectancy_pct": round(expectancy * 100, 3),
            "sharpe":        round(sharpe, 3),
        })

    return pd.DataFrame(records).set_index("horizon_h")


def main():
    import warnings
    warnings.filterwarnings("ignore")

    from sqlalchemy import text
    from .db import get_engine, load_dataframes

    print("Loading signals from database...")
    eng = get_engine()
    with eng.connect() as conn:
        signals_all = pd.read_sql(text("""
            SELECT ss.datetime, t.sname, s.name AS strategy, ss.signal AS ma_signal
            FROM strategies_signals ss
            JOIN timeseries t ON t.id = ss.timeseries_id
            JOIN strategies s ON s.id  = ss.strategy_id
            ORDER BY ss.datetime
        """), conn)

    if signals_all.empty:
        print("No signals found in database.")
        return

    signals_all["datetime"] = pd.to_datetime(signals_all["datetime"], utc=True)

    print("Loading OHLCV data...")
    _, ohlcv_all, _ = load_dataframes()
    ohlcv_all["datetime"] = pd.to_datetime(ohlcv_all["datetime"], utc=True)

    print()
    header = f"{'Symbol':<12} {'Strategy':<38} {'H':>4} {'N':>5} {'Win%':>7} {'AvgW%':>7} {'AvgL%':>7} {'Exp%':>7} {'Sharpe':>7}"
    print(header)
    print("-" * len(header))

    for sname in sorted(signals_all["sname"].unique()):
        sym_sigs  = signals_all[signals_all["sname"] == sname]
        sym_ohlcv = ohlcv_all[ohlcv_all["sname"] == sname].set_index("datetime").sort_index()

        for strategy in sorted(sym_sigs["strategy"].unique()):
            strat_sigs = sym_sigs[sym_sigs["strategy"] == strategy]
            metrics = compute_metrics(strat_sigs, sym_ohlcv, horizons=[4, 8, 24])

            if metrics.empty:
                continue

            for h, row in metrics.iterrows():
                print(
                    f"{sname:<12} {strategy:<38} {h:>4}h "
                    f"{row['n_signals']:>5} "
                    f"{row['win_rate']*100:>6.1f}% "
                    f"{row['avg_win_pct']:>+7.2f}% "
                    f"{row['avg_loss_pct']:>+7.2f}% "
                    f"{row['expectancy_pct']:>+7.2f}% "
                    f"{row['sharpe']:>7.2f}"
                )
        print()


if __name__ == "__main__":
    main()
