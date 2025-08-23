import os

from datetime import datetime, timedelta, timezone

# Current UTC time
now_utc = datetime.now(timezone.utc)

# 1h ago
one_hour_ago = now_utc - timedelta(hours=1)

# Date window for loading OHLC and iterating
#ARG_START_DATE     = os.getenv("ARG_START_DATE", "2024-01-01 00:00:00")  # None for full history
ARG_START_DATE    = os.getenv("ARG_START_DATE", now_utc.strftime("%Y-%m-%d %H:%M:%S"))
START_DATE_UPLOAD  = os.getenv("START_DATE_UPLOAD", "2023-01-01 00:00:00")
#END_DATE           = os.getenv("END_DATE", "2025-08-24 16:00:00")
END_DATE          = os.getenv("END_DATE", now_utc.strftime("%Y-%m-%d %H:%M:%S"))


# DB
PG_DSN = os.getenv("PG_DSN_CRYPTO") or os.getenv("PG_DSN")

if not PG_DSN:
    raise SystemExit("Missing PG_DSN_CRYPTO / PG_DSN env var.")

