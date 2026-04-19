"""Extrae tablas de hechos (bets/tickets) iterando particiones diarias → Parquet mensual."""
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from etl.config import DB_URL, DATA_DIR
from etl.logger import get_logger

log = get_logger("etl.facts")

START = date(2025, 10, 1)
END = date(2026, 3, 31)

BETS_COLS = "id, created, amount, prize, payed, ticket_id, bet_statu_id, lotery_id, number, tripleta_count"
TICKETS_COLS = (
    "id, created, total_amount, cant_bets, user_id, ticket_status_id, "
    "prize, payed, center_id, agency_id, group_id, master_center_id, "
    "anull_by, anull_date, anull_role, moneda_id, transacction_id"
)


def _days(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _months(start: date, end: date):
    cur = start.replace(day=1)
    while cur <= end:
        yield cur
        cur += relativedelta(months=1)


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
        {"t": table},
    )
    return result.fetchone() is not None


def _extract_month(engine, month: date, prefix: str, cols: str) -> pd.DataFrame:
    """Conexión nueva por día para evitar timeouts en meses grandes."""
    next_month = month + relativedelta(months=1)
    last_day = next_month - timedelta(days=1)
    frames = []

    for day in _days(month, last_day):
        table = f"{prefix}_{day.strftime('%Y%m%d')}"
        try:
            with engine.connect() as conn:
                if not _table_exists(conn, table):
                    continue
                df = pd.read_sql(text(f"SELECT {cols} FROM {table}"), conn)
                if not df.empty:
                    frames.append(df)
                    log.debug("  %s → %s filas", table, f"{len(df):,}")
        except Exception:
            log.exception("  Error en partición %s", table)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def extract_facts():
    engine = create_engine(DB_URL, pool_pre_ping=True)
    out = DATA_DIR / "facts"

    for month in _months(START, END):
        month_str = month.strftime("%Y-%m")

        for prefix, cols in [("tickets", TICKETS_COLS), ("bets", BETS_COLS)]:
            path = out / f"{prefix}_{month_str}.parquet"

            if path.exists():
                log.info("[%s] %s ya existe — skip", month_str, prefix)
                continue

            log.info("[%s] Extrayendo %s...", month_str, prefix)
            try:
                df = _extract_month(engine, month, prefix, cols)
                if not df.empty:
                    df.to_parquet(path, index=False)
                    log.info("  → %s %s", f"{len(df):,}", prefix)
                else:
                    log.warning("  → sin datos para %s %s", prefix, month_str)
            except Exception:
                log.exception("Error extrayendo %s %s", prefix, month_str)

    engine.dispose()
    log.info("Hechos extraídos.")


if __name__ == "__main__":
    extract_facts()
