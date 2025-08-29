import os

from datetime import datetime, timedelta, timezone

# Current UTC time
now_utc = datetime.now(timezone.utc)

# Date window for loading OHLC and iterating
#ARG_START_DATE     = os.getenv("ARG_START_DATE", "2025-08-22 05:00:00")  # None for full history
RAW_ARG_START_DATE    = os.getenv("ARG_START_DATE", now_utc.strftime("%Y-%m-%d %H:%M:%S"))
START_DATE_UPLOAD  = os.getenv("START_DATE_UPLOAD", "2025-08-01 00:00:00")
#END_DATE           = os.getenv("END_DATE", "2025-08-22 10:00:00")
RAW_END_DATE          = os.getenv("END_DATE", now_utc.strftime("%Y-%m-%d %H:%M:%S"))

# Parse to datetime
start_dt = datetime.strptime(RAW_ARG_START_DATE, "%Y-%m-%d %H:%M:%S")
ARG_START_DATE = start_dt + timedelta(hours=1)

end_dt = datetime.strptime(RAW_END_DATE, "%Y-%m-%d %H:%M:%S")
END_DATE = end_dt + timedelta(hours=1)

# DB
PG_DSN = os.getenv("PG_DSN_CRYPTO") or os.getenv("PG_DSN")

if not PG_DSN:
    raise SystemExit("Missing PG_DSN_CRYPTO / PG_DSN env var.")

