# Crypto MA Signals

Automated hourly pipeline that fetches OHLCV data from Binance, computes **MA Sabres** and **Supertrend** signals, persists them to a PostgreSQL database (Supabase), and pushes buy/sell alerts to a Telegram channel.

---

## How It Works

```
GitHub Actions (every 59 min)
        │
        ▼
┌─────────────────┐        ┌─────────────────────────────┐
│ binance_parser  │──────▶│ ohlc table (Supabase/PG)    │
│ (RECENT_1H mode)│        └────────────┬────────────────┘
└─────────────────┘                     │
                                        ▼
                           ┌────────────────────────────┐
                           │  src/run_signals.py        │
                           │  • loads OHLC + strategies │
                           │  • runs MA Sabres logic    │
                           │  • optional Supertrend     │
                           │    filter                  │
                           └────────┬───────────────────┘
                                    │
                    ┌───────────────┴──────────────┐
                    ▼                              ▼
         strategies_signals table         Telegram notification
```

### Signal Logic

**MA Sabres** — detects when a moving average reverses direction after a sustained trend:

- **Buy**: MA was falling for `count_buy` consecutive bars → starts rising
- **Sell**: MA was rising for `count_sell` consecutive bars → starts falling

Separate MA periods (`length_buy`, `length_sell`) allow asymmetric sensitivity for entries vs exits.

**Optional filters** (configured per strategy via JSON params):

| Filter | What it does |
|---|---|
| Supertrend | Suppresses sell signals when Supertrend is bullish; optionally symmetric (also suppresses buys in downtrends) |
| Slope magnitude | Requires the MA to have moved at least N × ATR over the count window — eliminates weak, flat reversals |
| Volume confirmation | Signal bar volume must exceed a rolling average by a configurable multiplier |
| ADX regime gate | Blocks all signals when ADX < threshold — keeps the strategy inactive in choppy, ranging markets |
| Multi-timeframe alignment | Resamples 1h data to a higher timeframe (e.g. 4h), computes MA direction, and suppresses signals that trade against the HTF trend |

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

## Database Schema

```
timeseries          → registry of symbols (sname = e.g. "BTCUSDT")
ohlc                → OHLCV rows, unique (timeseries_id, datetime)
strategies          → per-symbol strategy configs (JSON params)
strategies_signals  → computed buy/sell signals, unique (timeseries_id, strategy_id, datetime)
```

Strategy params (stored as JSONB). All fields are optional — omitting any new param leaves existing behaviour unchanged.

**Core**

| Field                | Default | Description                                    |
|----------------------|---------|------------------------------------------------|
| `ma_type`            | `"TEMA"` | MA algorithm: TEMA, EMA, HMA, VWMA, etc.     |
| `length_buy`         | —       | MA period for the buy signal MA                |
| `count_buy`          | —       | Bars MA must fall before a buy triggers        |
| `length_sell`        | —       | MA period for the sell signal MA               |
| `count_sell`         | —       | Bars MA must rise before a sell triggers       |

**Supertrend filter**

| Field                      | Default | Description                                         |
|----------------------------|---------|-----------------------------------------------------|
| `supertrend_enabled`       | `false` | Apply Supertrend filter                             |
| `supertrend.atr_period`    | `14`    | ATR lookback for Supertrend                         |
| `supertrend.multiplier`    | `2.0`   | ATR multiplier for Supertrend bands                 |
| `supertrend_symmetric`     | `false` | Also suppress buys when Supertrend is bearish       |

**Signal quality filters**

| Field             | Default | Description                                                      |
|-------------------|---------|------------------------------------------------------------------|
| `min_slope_mult`  | `0.0`   | Min avg MA slope as × ATR per bar (0 = off)                     |
| `vol_lookback`    | `0`     | Volume MA lookback for confirmation (0 = off)                   |
| `vol_mult`        | `1.0`   | Volume must be ≥ vol_mult × rolling volume average              |
| `adx_threshold`   | `0.0`   | Min ADX to allow a signal — 25 is a typical trending threshold  |
| `adx_length`      | `14`    | ADX lookback period                                             |

**Multi-timeframe alignment**

| Field           | Default  | Description                                          |
|-----------------|----------|------------------------------------------------------|
| `mtf_enabled`   | `false`  | Enable higher-timeframe trend filter                 |
| `mtf_resample`  | `"4h"`   | Pandas resample rule for the higher timeframe        |
| `mtf_ma_length` | `20`     | MA period on the higher timeframe                    |

**Example strategy with all filters enabled:**

```json
{
  "ma_type": "TEMA",
  "length_buy": 60,  "count_buy": 30,
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

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo>
cd crypto
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable             | Description                                      |
|----------------------|--------------------------------------------------|
| `PG_DSN_CRYPTO`      | PostgreSQL connection string (Supabase or other) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (optional)                    |
| `TELEGRAM_CHAT_ID`   | Telegram chat/group ID (optional)                |
| `ARG_START_DATE`     | Start of signal computation window (UTC)         |
| `END_DATE`           | End of signal computation window (UTC)           |
| `START_DATE_UPLOAD`  | Earliest OHLCV date to load from DB              |

### 3. Initialize the database

Run the SQL scripts in order:

```sql
-- 1. Create tables
\i instructions/create_tables.sql

-- 2. Seed symbols and strategies
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

### 6. Run backtesting metrics

After signals have been generated, evaluate their quality:

```bash
python -m src.backtest
```

Prints a table like:

```
Symbol       Strategy                               H     N    Win%  AvgW%  AvgL%   Exp%  Sharpe
-------------------------------------------------------------------------------------------------
BTCUSDT      MA Sabres (TEMA) — baseline           4h    42   54.8%  +1.23%  -0.91%  +0.26%   1.42
BTCUSDT      MA Sabres (TEMA) — baseline           8h    42   57.1%  +1.87%  -1.12%  +0.59%   1.71
...
```

Horizons evaluated: **4h**, **8h**, **24h** forward returns.

---

## GitHub Actions

The workflow (`.github/workflows/ma_technicals.yml`) runs automatically every 59 minutes:

1. **`recent-hour`** job: fetches last hour of OHLCV for BTC, ETH, ARB, SOL from Binance
2. **`calc`** job: runs `src.run_signals`, inserts signals, sends Telegram alerts

Required GitHub Secrets:

| Secret                | Maps to env var        |
|-----------------------|------------------------|
| `PG_DSN_CRYPTO`       | `PG_DSN`               |
| `TELEGRAM_BOT_TOKEN`  | `TELEGRAM_BOT_TOKEN`   |
| `TELEGRAM_GROUP_ID`   | `TELEGRAM_CHAT_ID`     |

---

## Supported Moving Averages

| Type       | Description                         |
|------------|-------------------------------------|
| `SMA`      | Simple Moving Average               |
| `EMA`      | Exponential Moving Average          |
| `RMA`/`SMMA` | Wilder's Smoothed MA              |
| `WMA`      | Weighted Moving Average             |
| `HMA`/`HULLMA` | Hull Moving Average             |
| `VWMA`     | Volume-Weighted Moving Average      |
| `DEMA`     | Double EMA                          |
| `TEMA`     | Triple EMA (default)                |

---

## Open Improvements

### Reliability & Observability

**No structured logging**
All output uses bare `print()`. Replacing with Python's `logging` module would allow log levels (DEBUG/INFO/WARNING), timestamps, and easier filtering in GitHub Actions logs.

**No signal deduplication check before computation**
The DB insert uses `ON CONFLICT DO NOTHING`, but the signal is still computed even if it already exists. A cheap `SELECT` before the heavy rolling computation would skip redundant work on re-runs.

**No `src/__init__.py`**
The `src/` package has no `__init__.py`. It works when invoked with `python -m src.run_signals` but would fail with certain import styles and linters.

### Extensibility

**Hardcoded symbol list in GitHub Actions**
Symbols (`BTC,ETH,ARB,SOL`) are hardcoded in the workflow YAML. Making this a workflow input or a repository variable would let you add/remove symbols without editing the workflow file.

**Strategy params have no schema validation**
Strategy params are raw JSONB with no enforcement. A missing key silently falls back to a default (e.g., `length_sell` defaults to 0), which can produce unexpected signals. Adding validation when a strategy is loaded would catch misconfiguration early.

**Only Binance.US is supported by default**
`BINANCE_BASE_URL` defaults to `https://api.binance.us`. Binance.US is geo-restricted. `https://api.binance.com` would give broader coverage; the URL can be swapped via the existing env var.

**+1 hour offset applied unconditionally in config.py**
Both `ARG_START_DATE` and `END_DATE` have a `+ timedelta(hours=1)` applied regardless of input. This undocumented workaround silently shifts any date the caller provides.
