import pandas as pd
from sqlalchemy import create_engine, text
from .config import PG_DSN, START_DATE_UPLOAD, END_DATE

def get_engine():
    return create_engine(PG_DSN, pool_pre_ping=True)

def load_dataframes(start: str = START_DATE_UPLOAD, end: str = END_DATE):
    eng = get_engine()

    q1 = "select sname from timeseries order by sname;"
    snames = pd.read_sql(text(q1), eng)

    q2 = """
    select t.sname, o.*
    from ohlc o
    join timeseries t on t.id = o.timeseries_id
    where o.datetime >= :start and o.datetime <= :end
    order by o.datetime asc;
    """
    values = pd.read_sql(text(q2), eng, params={"start": start, "end": end})

    q3 = """
    select t.sname, s.*
    from strategies s
    join timeseries t on t.id = s.timeseries_id
    where s.use_in_analysis = true
    order by t.sname;
    """
    strategies = pd.read_sql(text(q3), eng)

    return snames, values, strategies

def insert_last_signal(summary_row: pd.Series):
    """
    Insert only the last row of a prepared 'summary' (Series with columns:
     datetime, sname, strategy, ma_signal).
    """

    if pd.isna(summary_row.get("ma_signal")):
        print("⚠️ Skipped: last ma_signal is NaN")
        return

    eng = get_engine()
    with eng.connect() as conn:
        if summary_row["ma_signal"] in ("buy", "sell"):
            ts_res = conn.execute(
                text("SELECT id FROM timeseries WHERE sname = :sname"),
                {"sname": summary_row["sname"]}
            ).fetchone()

            strat_res = conn.execute(
                text("SELECT id FROM strategies WHERE name = :name"),
                {"name": summary_row["strategy"]}
            ).fetchone()

            if ts_res and strat_res:
                sql = text("""
                    INSERT INTO strategies_signals (datetime, timeseries_id, strategy_id, signal)
                    VALUES (:dt, :ts_id, :strat_id, :sig)
                    ON CONFLICT (timeseries_id, strategy_id, datetime) DO NOTHING
                """)
                conn.execute(sql, {
                    "dt": summary_row["datetime"],
                    "ts_id": ts_res[0],
                    "strat_id": strat_res[0],
                    "sig": summary_row["ma_signal"]
                })
                print(f" Inserted {summary_row['sname']} {summary_row['strategy']} {summary_row['ma_signal']} at {summary_row['datetime']}")
            else:
                print(f" Skipped: unresolved IDs for {summary_row['sname']} / {summary_row['strategy']}")

        conn.commit()

