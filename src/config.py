import os

# Date window for loading OHLC and iterating
ARG_START_DATE     = os.getenv("ARG_START_DATE", "2025-01-01 00:00:00")  # None for full history
START_DATE_UPLOAD  = os.getenv("START_DATE_UPLOAD", "2023-01-01 00:00:00")
END_DATE           = os.getenv("END_DATE", "2025-08-22 16:00:00")

# DB
PG_DSN = os.getenv("PG_DSN_CRYPTO") or os.getenv("PG_DSN")

if not PG_DSN:
    raise SystemExit("Missing PG_DSN_CRYPTO / PG_DSN env var.")

