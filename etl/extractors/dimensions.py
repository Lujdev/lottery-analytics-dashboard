"""Extrae tablas de dimensiones (pequeñas, extracción completa)."""
import pandas as pd
from sqlalchemy import create_engine, text
from etl.config import DB_URL, DATA_DIR
from etl.logger import get_logger

log = get_logger("etl.dimensions")

DIMENSIONS = {
    "agencys": "SELECT id, name, group_id, enable, created, comision_ventas, participacion, ganancias FROM agencys",
    "groups": "SELECT id, name, center_id, enable, created FROM groups",
    "centers": "SELECT id, name, master_center_id, enable, created FROM centers",
    "master_centers": "SELECT id, name, created, enable FROM master_centers",
    "new_products": "SELECT id, name, product_type_id, enable FROM new_products",
    "loteries": "SELECT id, name, product_new, lotery_hour, enable, monday, tuesday, wednesday, thursday, friday, saturday, sunday FROM loteries",
    "numbers": "SELECT id, name, value, product_id, enable, product_type_id FROM numbers",
}


def extract_dimensions():
    engine = create_engine(DB_URL)
    out = DATA_DIR / "dimensions"

    with engine.connect() as conn:
        for table, query in DIMENSIONS.items():
            log.info("Extrayendo %s...", table)
            try:
                df = pd.read_sql(text(query), conn)
                path = out / f"{table}.parquet"
                df.to_parquet(path, index=False)
                log.info("  → %s filas → %s", f"{len(df):,}", path)
            except Exception:
                log.exception("Error extrayendo %s", table)

    engine.dispose()
    log.info("Dimensiones extraídas.")


if __name__ == "__main__":
    extract_dimensions()
