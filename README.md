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

**Supertrend filter** (optional per strategy): if the MA issues a sell signal but Supertrend is bullish, the sell is suppressed.

---

## Project Structure

```
crypto/
├── binance_parser.py          # Fetches OHLCV from Binance API → DB
├── src/
│   ├── config.py              # Env-driven date range + DB config
│   ├── db.py                  # SQL queries: load data, insert signals
│   ├── indicators.py          # SMA, EMA, RMA, WMA, HMA, VWMA, DEMA, TEMA, ATR
│   ├── sabres.py              # MA Sabres signal detection
│   ├── supertrend.py          # Supertrend indicator
│   ├── run_signals.py         # Orchestration: load → compute → store → notify
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

Strategy params (stored as JSONB):

| Field                | Description                                    |
|----------------------|------------------------------------------------|
| `ma_type`            | MA algorithm: TEMA, EMA, HMA, VWMA, etc.      |
| `length_buy`         | MA period for the buy signal MA                |
| `count_buy`          | Bars MA must fall before a buy triggers        |
| `length_sell`        | MA period for the sell signal MA               |
| `count_sell`         | Bars MA must rise before a sell triggers       |
| `supertrend_enabled` | Whether to apply Supertrend filter             |
| `supertrend.atr_period` | ATR lookback for Supertrend                 |
| `supertrend.multiplier` | ATR multiplier for Supertrend bands         |

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

## Possible Improvements

### Performance

**1. Eliminate bar-by-bar rolling loop (biggest win)**
`run_signals.py` re-runs `detect_ma_sabres` for every single candle in the selected window. Since the underlying logic in `sabres.py` is fully vectorized, the result changes only at the final bar. The loop could be replaced with a single call over the full dataset, checking only the last row for a signal. This would reduce compute time from O(N) indicator evaluations to O(1) per symbol/strategy.

**2. Python `for` loop in `rma()` (indicators.py)**
The `rma()` function in `indicators.py` uses a Python-level loop for Wilder's smoothing, which is slow on long series. `supertrend.py` already implements the same thing correctly using `series.ewm(alpha=1/length, adjust=False).mean()`. Both files should use the same vectorized implementation.

**3. New DB engine created per signal**
`insert_last_signal()` calls `get_engine()` on every invocation. SQLAlchemy engines are meant to be long-lived; creating one per call wastes connection overhead. A module-level engine or connection pool should be shared.

### Correctness

**4. Duplicate `end_dt` assignment (run_signals.py:30-31)**
`end_dt = _ensure_utc(END_DATE)` is written twice on consecutive lines — dead code that should be removed.

**5. Dead assignment overwritten immediately (run_signals.py:122-123)**
```python
last["sname"] = s       # set to strategy name
last["sname"] = sname   # immediately overwritten with symbol name
```
The first line has no effect.

**6. +1 hour offset applied unconditionally in config.py**
Both `ARG_START_DATE` and `END_DATE` have a `+ timedelta(hours=1)` applied regardless of input. This workaround is not documented and will silently shift any date the caller provides.

**7. `_tg_escape_md2` is defined but never called**
The Telegram message is sent as plain text (no `parse_mode` set), but the escape helper exists as dead code. If MarkdownV2 formatting is ever added, the function also has a subtle bug: it doesn't escape `\` first, so backslashes inserted during earlier iterations get double-escaped in later ones.

**8. FULL mode comment says "from 2010" but starts from 2020**
`binance_parser.py` `date_range_for_mode()` sets `start_dt = datetime(2020,1,1, ...)` while the workflow comment says "from 2010".

### Reliability & Observability

**9. No structured logging**
All output uses bare `print()`. Replacing with Python's `logging` module would allow log levels (DEBUG/INFO/WARNING), timestamps, and easier filtering in GitHub Actions logs.

**10. No signal deduplication check before computation**
The DB insert uses `ON CONFLICT DO NOTHING`, but the signal is still computed even if it already exists. A cheap `SELECT` before the heavy rolling computation would skip redundant work on re-runs.

**11. No `src/__init__.py`**
The `src/` package has no `__init__.py`. It works when invoked with `python -m src.run_signals` but would fail with certain import styles and linters.

### Security

**12. Real credentials in `.env.example`**
The `.env.example` file contains an actual Supabase connection string including username and password. It should be replaced with placeholder values (e.g., `PG_DSN_CRYPTO=postgresql://user:password@host:5432/db`). Rotate the exposed credentials.

### Extensibility

**13. Hardcoded symbol list in GitHub Actions**
Symbols (`BTC,ETH,ARB,SOL`) are hardcoded in the workflow YAML. Making this a workflow input or a repository variable would let you add/remove symbols without editing the workflow file.

**14. Strategy params have no schema validation**
Strategy params are raw JSONB with no enforcement. A missing key silently falls back to a default (e.g., `length_sell` defaults to 0), which can produce unexpected signals. Adding validation when a strategy is loaded would catch misconfiguration early.

**15. Only Binance.US is supported by default**
`BINANCE_BASE_URL` defaults to `https://api.binance.us`. Binance.US is geo-restricted. `https://api.binance.com` would give broader coverage; the URL could be swapped via the existing env var.
