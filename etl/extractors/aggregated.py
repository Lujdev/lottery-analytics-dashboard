"""Extrae tablas pre-agregadas (extracción completa, son manejables)."""
import pandas as pd
from sqlalchemy import create_engine, text
from etl.config import DB_URL, DATA_DIR
from etl.logger import get_logger

log = get_logger("etl.aggregated")

AGGREGATED = {
    "sales_by_loteries": "SELECT * FROM sales_by_loteries",
    "sales_by_agency": "SELECT * FROM sales_by_new_products_agency",
    "sales_by_group": "SELECT * FROM sales_by_new_products_group",
    "sales_by_center": "SELECT * FROM sales_by_new_products_center",
    "sales_by_master_center": "SELECT * FROM sales_by_new_products_master_center",
}


def extract_aggregated():
    engine = create_engine(DB_URL)
    out = DATA_DIR / "aggregated"

    with engine.connect() as conn:
        for name, query in AGGREGATED.items():
            log.info("Extrayendo %s...", name)
            try:
                df = pd.read_sql(text(query), conn)
                path = out / f"{name}.parquet"
                df.to_parquet(path, index=False)
                log.info("  → %s filas → %s", f"{len(df):,}", path)
            except Exception:
                log.exception("Error extrayendo %s", name)

    engine.dispose()
    log.info("Tablas agregadas extraídas.")


if __name__ == "__main__":
    extract_aggregated()
