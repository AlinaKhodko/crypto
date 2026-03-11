# Crypto MA Signals

An automated hourly pipeline that fetches OHLCV data from Binance, runs technical analysis to detect buy/sell signals, persists them to a PostgreSQL database (Supabase), and sends alerts to a Telegram channel.

---

## How It Works

```
Every 59 minutes on GitHub Actions:

  Job 1: binance_parser.py
  ┌─────────────────────────────────────────────────┐
  │ Binance API → fetch last 1h candle              │
  │ for BTC, ETH, ARB, SOL                          │
  │ → upsert into ohlc table (Supabase/PG)          │
  └─────────────────────────────────────────────────┘
                          ↓
  Job 2: src/run_signals.py
  ┌─────────────────────────────────────────────────┐
  │ Load OHLCV + strategy configs from DB           │
  │ → run MA Sabres signal detection                │
  │ → apply optional filters                        │
  │ → insert signals into strategies_signals        │
  │ → send Telegram alert                           │
  └─────────────────────────────────────────────────┘
```

Job 2 waits for Job 1 to finish so the new candle is in the DB before signals are computed.

---

## Project Structure

```
crypto/
├── binance_parser.py          # Fetches OHLCV from Binance API → DB
├── src/
│   ├── config.py              # Env-driven date range + DB config
│   ├── db.py                  # SQL queries: load data, insert signals
│   ├── indicators.py          # SMA, EMA, RMA, WMA, HMA, VWMA, DEMA, TEMA, ATR, ADX
│   ├── sabres.py              # MA Sabres signal detection (slope, volume, ADX filters)
│   ├── supertrend.py          # Supertrend indicator
│   ├── run_signals.py         # Orchestration: load → compute → filter → store → notify
│   ├── backtest.py            # Forward-return metrics: win rate, expectancy, Sharpe
│   └── telegram.py            # Telegram bot notifications
├── instructions/
│   ├── create_tables.sql      # DB schema
│   ├── inserts.sql            # Seed timeseries + strategy configs
│   └── fix_idle.sql
├── .github/workflows/
│   └── ma_technicals.yml      # GitHub Actions: fetch + compute, every 59 min
├── .env.example               # Required environment variables
└── requirements.txt
```

---

## Database

Four tables, each with a clear role.

**`timeseries`** — registry of every symbol being tracked

```
id | sname    | lname    | ...
1  | BTCUSDT  | Bitcoin  | ...
2  | ETHUSDT  | Ethereum | ...
```

**`ohlc`** — raw price data, one row per candle

```
timeseries_id | datetime             | value   | open    | high    | low     | volume
1             | 2026-03-11 10:00:00  | 82000.0 | 81500.0 | 82300.0 | 81200.0 | 1234.5
```

`value` = close price. Unique constraint on `(timeseries_id, datetime)` makes upserts safe and idempotent.

**`strategies`** — per-symbol strategy configurations stored as JSONB

```
timeseries_id | name                           | params (JSONB)
1             | MA Sabres (TEMA) — baseline    | {"length_buy": 60, ...}
1             | MA Sabres (TEMA) + Supertrend  | {"length_buy": 60, "supertrend_enabled": true, ...}
```

Each symbol can have multiple independent strategies.

**`strategies_signals`** — the output: every detected buy/sell signal

```
timeseries_id | strategy_id | datetime             | signal
1             | 1           | 2026-03-10 14:00:00  | buy
1             | 2           | 2026-03-09 08:00:00  | sell
```

Unique on `(timeseries_id, strategy_id, datetime)` — the same signal is never inserted twice.

---

## Data Ingestion (`binance_parser.py`)

Fetches OHLCV candles from `api.binance.us` and writes them to the `ohlc` table.

**Two modes:**
- `FULL` — loads everything from 2020-01-01 to now (used for initial backfill)
- `RECENT_1H` — loads only the last 1 hour (used every 59 minutes in production)

**Pagination:** Each API call fetches up to 1000 candles. The script tracks the last `close_time` and advances the cursor until it reaches the end of the requested range.

**Reliability:** Retries with exponential backoff on failures or rate limits (HTTP 429). Uses `ON CONFLICT DO UPDATE` — so every run is idempotent; re-running never creates duplicate data.

---

## Signal Computation (`src/run_signals.py`)

The orchestrator. For each symbol × strategy combination:

```
1. Load all OHLCV rows for the symbol (filtered to date window)
2. Trim to a working window starting just before arg_start
   (gives the MA enough bars to warm up without processing all history)
3. Call detect_ma_sabres() once → get all signals in the window
4. Filter signals to only those at or after arg_start
5. Apply Supertrend filter (if enabled)
6. Apply multi-timeframe alignment filter (if enabled)
7. For each remaining signal → insert to DB + send Telegram
```

**Why `arg_start`?**
In production, `ARG_START_DATE` is approximately now. The pipeline only processes the current hour's signal, not the entire history. Combined with `ON CONFLICT DO NOTHING`, re-runs are always safe.

---

## The Core Math: MA Sabres (`src/sabres.py`)

**Concept:** A moving average that has been trending in one direction for a sustained period has built-up momentum. When it reverses, that's a meaningful signal.

**Buy signal:**
1. Compute a moving average with period `length_buy`
2. Check if that MA has been **falling** for every one of the last `count_buy` bars
3. If yes, and the MA is now **rising** → **buy**

**Sell signal:**
1. Compute a moving average with period `length_sell`
2. Check if that MA has been **rising** for every one of the last `count_sell` bars
3. If yes, and the MA is now **falling** → **sell**

Buy and sell use **separate MAs** with independent periods — entries and exits can have different sensitivities. For example, using a shorter MA for buys and a longer one for sells reflects that crypto rallies tend to be slower and more sustained while reversals are sharper.

**The signal fires exactly once** — on the first bar of the reversal. Once the MA is rising, the "was falling" condition becomes false, so no duplicate signals on consecutive bars.

**In code:**
```python
fl = series_falling(ma_buy, count_buy)     # True where MA fell for count_buy consecutive bars
rs = series_rising(ma_sell, count_sell)    # True where MA rose for count_sell consecutive bars

up_cond = fl.shift(1) & (ma_buy > ma_buy.shift(1))    # was falling, now rising → buy
dn_cond = rs.shift(1) & (ma_sell < ma_sell.shift(1))  # was rising, now falling → sell
```

---

## Moving Averages (`src/indicators.py`)

All computed on the `value` (close price) column:

| Type | Formula | Character |
|---|---|---|
| `SMA` | Rolling mean | Slow, stable |
| `EMA` | Exponential with `span=length` | Faster than SMA |
| `RMA` / `SMMA` | Wilder's MA: `ewm(alpha=1/length)` | Very smooth, used for ATR |
| `WMA` | Linearly weighted (recent bars weighted more) | Faster than SMA |
| `HMA` / `HULLMA` | `WMA(2×WMA(n/2) − WMA(n), √n)` | Very low lag |
| `VWMA` | Price × volume weighted mean | Volume-aware |
| `DEMA` | `2×EMA − EMA(EMA)` | Reduced lag vs EMA |
| `TEMA` | `3×EMA − 3×EMA(EMA) + EMA(EMA(EMA))` | Minimal lag (default) |

**ATR (Average True Range):**
```
True Range  = max(high − low, |high − prev_close|, |low − prev_close|)
ATR         = RMA(True Range, length)
```
Measures volatility. Used to scale signal quality filters.

**ADX (Average Directional Index):**
```
+DM  = max(high − prev_high, 0)  when > −DM, else 0
−DM  = max(prev_low − low, 0)    when > +DM, else 0
+DI  = 100 × RMA(+DM) / ATR
−DI  = 100 × RMA(−DM) / ATR
DX   = 100 × |+DI − −DI| / (+DI + −DI)
ADX  = RMA(DX)
```
Measures trend **strength** (not direction). Below ~20 = ranging market. Above 25 = trending market. Used to gate signals.

---

## Supertrend (`src/supertrend.py`)

A trend-following indicator that uses ATR to compute dynamic support/resistance bands:

```
Source      = (open + high + low + close) / 4
Upper band  = source + multiplier × ATR    ← resistance in downtrend
Lower band  = source − multiplier × ATR    ← support in uptrend
```

The bands **ratchet** — the lower band can only move up (never down) in a bullish trend, and vice versa. This prevents the indicator from flipping on small pullbacks.

**Trend state:**
- `+1` (bullish) when price is above the lower band
- `−1` (bearish) when price is below the upper band

**As a filter:** The Supertrend side is looked up at the exact datetime of each MA Sabres signal. A sell signal that occurs while Supertrend is bullish is suppressed — you don't want to exit a strong uptrend on a minor MA wobble.

---

## Optional Filters

All filters are opt-in via strategy JSON params. Defaults leave the original behaviour untouched.

### Supertrend filter

| Param | Default | Description |
|---|---|---|
| `supertrend_enabled` | `false` | Enable Supertrend filter |
| `supertrend.atr_period` | `14` | ATR lookback |
| `supertrend.multiplier` | `2.0` | ATR multiplier for bands |
| `supertrend_symmetric` | `false` | Also suppress buys when Supertrend is bearish |

### Slope magnitude filter

```
avg_slope = |MA[t] − MA[t − count]| / count
threshold = ATR × min_slope_mult
Signal only fires if avg_slope >= threshold
```

Prevents weak, barely-moving MAs from triggering. `min_slope_mult=0.05` means the MA must move at least 5% of ATR per bar on average.

| Param | Default | Description |
|---|---|---|
| `min_slope_mult` | `0.0` | Min avg MA slope as × ATR per bar (0 = off) |

### Volume confirmation

```
vol_MA = rolling_mean(volume, vol_lookback)
Signal only fires if volume[t] >= vol_MA × vol_mult
```

Requires meaningful participation at the signal bar. A reversal on thin volume is less reliable.

| Param | Default | Description |
|---|---|---|
| `vol_lookback` | `0` | Volume MA lookback (0 = off) |
| `vol_mult` | `1.0` | Volume must be ≥ vol_mult × vol MA |

### ADX regime gate

```
Signal only fires if ADX >= adx_threshold
```

Turns the strategy off in sideways/choppy markets where MA reversals are noise. Typical value: 25.

| Param | Default | Description |
|---|---|---|
| `adx_threshold` | `0.0` | Min ADX to allow a signal (0 = off) |
| `adx_length` | `14` | ADX lookback period |

### Multi-timeframe alignment

```
Resample 1h OHLCV → higher timeframe (e.g. 4h)
Compute MA on 4h data, forward-fill direction to 1h
Buy suppressed  if 4h MA is falling
Sell suppressed if 4h MA is rising
```

Ensures 1h signals are trading with the larger trend.

| Param | Default | Description |
|---|---|---|
| `mtf_enabled` | `false` | Enable higher-timeframe filter |
| `mtf_resample` | `"4h"` | Pandas resample rule |
| `mtf_ma_length` | `20` | MA period on the higher timeframe |

### Full example strategy

```json
{
  "ma_type": "TEMA",
  "length_buy": 60,   "count_buy": 30,
  "length_sell": 120, "count_sell": 10,
  "supertrend_enabled": true,
  "supertrend": { "atr_period": 60, "multiplier": 2.0 },
  "supertrend_symmetric": true,
  "min_slope_mult": 0.05,
  "vol_lookback": 20, "vol_mult": 1.2,
  "adx_threshold": 25, "adx_length": 14,
  "mtf_enabled": true, "mtf_resample": "4h", "mtf_ma_length": 20
}
```

---

## Backtesting (`src/backtest.py`)

Measures whether historical signals actually made money.

**How it works:**
For each signal, the entry price is the close at the signal bar. The exit price is the close N hours later. Returns are sign-adjusted for direction (buy profits when price rises; sell profits when price falls).

**Metrics per forward-return horizon (4h, 8h, 24h):**

| Metric | Formula |
|---|---|
| Win rate | % of trades with positive return |
| Avg win | Mean return of winning trades |
| Avg loss | Mean return of losing trades |
| Expectancy | `win_rate × avg_win + loss_rate × avg_loss` |
| Sharpe | `mean(returns) / std(returns) × √(8760 / H)` annualised |

Run it after signals have been generated:

```bash
python -m src.backtest
```

Output:
```
Symbol       Strategy                               H     N    Win%  AvgW%  AvgL%   Exp%  Sharpe
-------------------------------------------------------------------------------------------------
BTCUSDT      MA Sabres (TEMA) — baseline           4h    42   54.8%  +1.23%  -0.91%  +0.26%   1.42
BTCUSDT      MA Sabres (TEMA) — baseline           8h    42   57.1%  +1.87%  -1.12%  +0.59%   1.71
...
```

---

## Alerts (`src/telegram.py`)

When a signal is generated, a message is sent to a Telegram chat:

```
🟢 BUY 🚀 BTCUSDT 2026-03-11 10:00 @ 82000.0
🔴 SELL 💥 ETHUSDT 2026-03-11 09:00 @ 3200.0
```

If `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` are not set, this silently does nothing — the pipeline continues normally.

---

## GitHub Actions

The workflow (`.github/workflows/ma_technicals.yml`) runs every 59 minutes (not 60 — GitHub's scheduler drifts, so 59 avoids accumulating offset).

**Two sequential jobs:**

```
Job 1: recent-hour (Python 3.11)
  pip install requests pandas psycopg2-binary
  python binance_parser.py --symbols "BTC,ETH,ARB,SOL" --interval 1h --mode RECENT_1H

         ↓ (needs: recent-hour)

Job 2: calc (Python 3.12)
  pip install -r requirements.txt
  python -m src.run_signals
```

Required GitHub Secrets:

| Secret | Maps to env var |
|---|---|
| `PG_DSN_CRYPTO` | `PG_DSN` |
| `TELEGRAM_BOT_TOKEN` | `TELEGRAM_BOT_TOKEN` |
| `TELEGRAM_GROUP_ID` | `TELEGRAM_CHAT_ID` |

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo>
cd crypto
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `PG_DSN_CRYPTO` | PostgreSQL connection string (Supabase or other) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (optional) |
| `TELEGRAM_CHAT_ID` | Telegram chat/group ID (optional) |
| `ARG_START_DATE` | Start of signal computation window (UTC) |
| `END_DATE` | End of signal computation window (UTC) |
| `START_DATE_UPLOAD` | Earliest OHLCV date to load from DB |

### 3. Initialise the database

```sql
\i instructions/create_tables.sql
\i instructions/inserts.sql
```

### 4. Load historical OHLCV data

```bash
# Full history from 2020
python binance_parser.py --symbols "BTC,ETH,SOL,ARB" --interval 1h --mode FULL

# Recent 1 hour only
python binance_parser.py --symbols "BTC,ETH,SOL,ARB" --interval 1h --mode RECENT_1H
```

### 5. Run signal computation

```bash
python -m src.run_signals
```

### 6. Evaluate signal quality

```bash
python -m src.backtest
```

---

## Open Improvements

**No structured logging** — bare `print()` throughout. Replacing with Python's `logging` module would add log levels, timestamps, and easier filtering in GitHub Actions.

**No pre-computation deduplication check** — signals are computed even if they already exist in the DB. A cheap `SELECT` before heavy indicator computation would skip redundant work on re-runs.

**No `src/__init__.py`** — the package works with `python -m src.run_signals` but would fail with certain import styles and linters.

**Hardcoded symbol list in workflow YAML** — adding/removing symbols requires editing the file. A repository variable or workflow input would be cleaner.

**No strategy param schema validation** — a missing key silently falls back to a default (e.g. `length_sell=0`), which can produce unexpected signals.

**Only Binance.US by default** — `BINANCE_BASE_URL` defaults to `api.binance.us` which is geo-restricted. Can be overridden via env var to use `api.binance.com`.

**Undocumented +1h offset in `config.py`** — both `ARG_START_DATE` and `END_DATE` have `+ timedelta(hours=1)` applied unconditionally, silently shifting any date the caller provides.
