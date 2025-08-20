#!/usr/bin/env python3
import os
import time
import math
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
import psycopg2
import argparse
from psycopg2.extras import execute_values

# --------------------------
# Configuration (env-driven)
# --------------------------
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "https://api1.binance.com")
USER_AGENT = os.getenv("USER_AGENT", "binance-history-loader/1.0")
REQUEST_LIMIT = int(os.getenv("REQUEST_LIMIT", "1000"))
SLEEP_BETWEEN_CALLS = float(os.getenv("SLEEP_BETWEEN_CALLS", "0.2"))
RETRY_MAX = int(os.getenv("RETRY_MAX", "5"))
RETRY_BACKOFF = float(os.getenv("RETRY_BACKOFF", "1.5"))



def parse_args():
    parser = argparse.ArgumentParser(description="Fetch Binance OHLCV and insert into Supabase.")
    parser.add_argument("--symbols", type=str, default=os.getenv("SYMBOLS", "INJ,BTC"),
                        help="Comma-separated list of symbols (default: env SYMBOLS or 'INJ,BTC')")
    parser.add_argument("--interval", type=str, default=os.getenv("BINANCE_INTERVAL", "1h"),
                        help="Binance kline interval (default: 1h)")
    parser.add_argument("--mode", type=str, choices=["FULL","RECENT_1H"],
                        default=os.getenv("MODE", "FULL").upper(),
                        help="FULL = from 2010, RECENT_1H = last 1h (default: FULL)")
    return parser.parse_args()


# --------------------------
# Helpers
# --------------------------
def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def kline_url():
    return f"{BINANCE_BASE_URL}/api/v3/klines"

def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int):
    """Fetch a single page of klines."""
    params = {"symbol": symbol, "interval": interval, "limit": REQUEST_LIMIT, "startTime": start_ms, "endTime": end_ms}
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(1, RETRY_MAX + 1):
        try:
            r = requests.get(kline_url(), params=params, headers=headers, timeout=20)
            if r.status_code == 429:
                wait = min(60, RETRY_BACKOFF ** attempt)
                print(f"[{symbol}] 429 rate limit; sleeping {wait:.1f}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == RETRY_MAX:
                raise
            wait = RETRY_BACKOFF ** attempt
            print(f"[{symbol}] fetch error {e}; retry in {wait:.1f}s ({attempt}/{RETRY_MAX})")
            time.sleep(wait)

def klines_to_df(klines):
    cols = [
        "open_time","open","high","low","close","volume","close_time","quote_asset_volume",
        "number_of_trades","taker_buy_base","taker_buy_quote","ignore"
    ]
    if not klines:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(klines, columns=cols)
    num_cols = ["open","high","low","close","volume","quote_asset_volume","taker_buy_base","taker_buy_quote"]
    df[num_cols] = df[num_cols].astype(float)
    df["number_of_trades"] = df["number_of_trades"].astype(int)
    df["open_time"]  = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    df["time"] = df["open_time"]
    return df

def paginate_klines(symbol: str, interval: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    """Fetch full range [start_dt, end_dt] by paging."""
    cursor = to_ms(start_dt)
    end_ms = to_ms(end_dt)
    out = []
    batches = 0
    while cursor < end_ms:
        data = fetch_klines(symbol, interval, cursor, end_ms)
        if not data:
            break
        df = klines_to_df(data)
        if df.empty:
            break
        out.append(df)
        batches += 1
        last_close_ms = int(df["close_time"].iloc[-1].timestamp() * 1000)
        cursor = last_close_ms + 1
        print(f"[{symbol}] batch {batches} rows={len(df)} {df['time'].iloc[0]} → {df['time'].iloc[-1]}")
        time.sleep(SLEEP_BETWEEN_CALLS)
        if len(df) < REQUEST_LIMIT and cursor <= last_close_ms + 1:
            break
    if not out:
        return pd.DataFrame(columns=["time","open","high","low","close","volume","open_time","close_time"])
    all_df = pd.concat(out, ignore_index=True)
    # de-dup & sort
    all_df = all_df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

    return all_df

def to_hourly_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep raw 1h OHLCV (no daily aggregation).
    Output: datetime, open, high, low, close, volume
    """
    if df.empty:
        return pd.DataFrame(columns=["datetime","open","high","low","close","volume"])
    df = df.copy()
    df["datetime"] = df["time"].dt.tz_convert("UTC")
    return df[["datetime","open","high","low","close","volume"]]


def to_daily_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1h klines to daily OHLCV to match stock_price schema.
    Output columns: date, open, high, low, close, volume
    """
    if df.empty:
        return pd.DataFrame(columns=["date","open","high","low","close","volume"])
    df = df.set_index("time")
    # Binance times are UTC; resample in UTC daily boundaries
    daily = pd.DataFrame({
        "open":  df["open"].resample("1D").first(),
        "high":  df["high"].resample("1D").max(),
        "low":   df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
        "volume":df["volume"].resample("1D").sum()
    }).dropna(subset=["open","high","low","close"], how="any")
    daily = daily.reset_index()
    #daily["date"] = daily["time"].dt.date
    daily["date"] = daily["time"].dt.tz_convert("UTC")
    return daily[["date","open","high","low","close","volume"]]

# --------------------------
# Database helpers
# --------------------------
def get_timeseries_id(conn, sname: str) -> int:
    with conn.cursor() as cur:
        cur.execute("select id from timeseries where sname = %s", (sname,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"timeseries not found for sname={sname}")
        return row[0]

def upsert_stock_price(conn, timeseries_id: int, hourly_df: pd.DataFrame):
    if hourly_df.empty:
        print(f"[ts={timeseries_id}] nothing to insert.")
        return
    records = [
        (timeseries_id, r.datetime, r.close, r.open, r.high, r.low, r.volume)
        for r in hourly_df.itertuples(index=False)
    ]
    sql = """
        insert into ohlc(timeseries_id, datetime, value, open, high, low, volume)
        values %s
        on conflict (timeseries_id, datetime) do update
        set value = excluded.value,
            open  = excluded.open,
            high  = excluded.high,
            low   = excluded.low,
            volume= excluded.volume,
            updated_at = now();
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, records, template="(%s,%s,%s,%s,%s,%s,%s)")
    conn.commit()
    print(f"[ts={timeseries_id}] upserted {len(records)} rows.")

# --------------------------
# Runner
# --------------------------
def date_range_for_mode(mode: str):
    now = utc_now()
    if mode == "FULL":
        start_dt = datetime(2018,1,1, tzinfo=timezone.utc)
        end_dt = now
    elif mode == "RECENT_1H":
        # Fetch a small window (last 2 hours for safety) and it will roll into today's daily bucket
        end_dt = now
        start_dt = now - timedelta(hours=2)
    else:
        raise ValueError("MODE must be FULL or RECENT_1H")
    return start_dt, end_dt

def main():
    args = parse_args()

    import os
    print("PG_DSN_CRYPTO =", os.getenv("PG_DSN"))

    # Postgres (Supabase) connection (use the "Connection string" ending with ?sslmode=require)
    PG_DSN = os.getenv("PG_DSN")

    if not PG_DSN:
        raise SystemExit("Missing PG_DSN env var (Supabase Postgres connection string).")

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    start_dt, end_dt = date_range_for_mode(args.mode)
    print(f"MODE={args.mode}  RANGE: {start_dt} → {end_dt}  interval={args.interval}  symbols={symbols}")

    with psycopg2.connect(PG_DSN) as conn:
            for base_symbol in symbols:
                binance_symbol = f"{base_symbol}USDT"
                sname = binance_symbol
                try:
                    ts_id = get_timeseries_id(conn, sname)
                except Exception as e:
                    print(f"[{sname}] skipped: {e}")
                    continue
                df_1h = paginate_klines(binance_symbol, args.interval, start_dt, end_dt)
                hourly = to_hourly_ohlcv(df_1h)   # if you want hourly
                upsert_stock_price(conn, ts_id, hourly)
if __name__ == "__main__":
    main()
