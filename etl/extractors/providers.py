"""Extrae tablas de proveedores externos."""
import pandas as pd
from sqlalchemy import create_engine, text
from etl.config import DB_URL, DATA_DIR
from etl.logger import get_logger

log = get_logger("etl.providers")

PROVIDER_TABLES = {
    "tickets_provider": "SELECT ticket_id, provider, created FROM tickets_provider",
    "log_api_provider": "SELECT id, provider, status, created FROM log_api_provider",
    "external_providers": "SELECT id, name, code, enable FROM external_providers",
}


def extract_providers():
    engine = create_engine(DB_URL)
    out = DATA_DIR / "aggregated"

    with engine.connect() as conn:
        for name, query in PROVIDER_TABLES.items():
            path = out / f"{name}.parquet"
            if path.exists():
                log.info("%s ya existe — skip", name)
                continue
            log.info("Extrayendo %s...", name)
            try:
                df = pd.read_sql(text(query), conn)
                df.to_parquet(path, index=False)
                log.info("  → %s filas", f"{len(df):,}")
            except Exception:
                log.exception("Error extrayendo %s", name)

    engine.dispose()
    log.info("Proveedores extraídos.")


if __name__ == "__main__":
    extract_providers()
