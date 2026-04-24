"""Loaders base sobre DuckDB/Parquet.

Todas las funciones devuelven pandas DataFrames y usan DuckDB ephemeral
para evitar cargar parquets enteros en memoria cuando no es necesario.
"""
from __future__ import annotations

import duckdb
import pandas as pd
from pathlib import Path

from ml.config import DATA_DIR


def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


# ── Tablas agregadas ────────────────────────────────────────────────────────

def load_sales_by_agency() -> pd.DataFrame:
    path = DATA_DIR / "aggregated" / "sales_by_agency.parquet"
    if not path.exists():
        return pd.DataFrame()
    sql = f"SELECT * FROM '{path}'"
    with _conn() as conn:
        return conn.execute(sql).df()


def load_sales_by_loteries() -> pd.DataFrame:
    path = DATA_DIR / "aggregated" / "sales_by_loteries.parquet"
    if not path.exists():
        return pd.DataFrame()
    sql = f"SELECT * FROM '{path}'"
    with _conn() as conn:
        return conn.execute(sql).df()


# ── Tablas de hechos (glob mensual) ─────────────────────────────────────────

def load_tickets() -> pd.DataFrame:
    pattern = DATA_DIR / "facts" / "tickets_*.parquet"
    with _conn() as conn:
        return conn.execute(f"SELECT * FROM '{pattern}'").df()


def load_bets() -> pd.DataFrame:
    pattern = DATA_DIR / "facts" / "bets_*.parquet"
    with _conn() as conn:
        return conn.execute(f"SELECT * FROM '{pattern}'").df()


# ── Dimensiones ─────────────────────────────────────────────────────────────

def load_dimension(name: str) -> pd.DataFrame:
    path = DATA_DIR / "dimensions" / f"{name}.parquet"
    if not path.exists():
        return pd.DataFrame()
    sql = f"SELECT * FROM '{path}'"
    with _conn() as conn:
        return conn.execute(sql).df()


def load_agencys() -> pd.DataFrame:
    return load_dimension("agencys")


def load_new_products() -> pd.DataFrame:
    return load_dimension("new_products")


def load_loteries() -> pd.DataFrame:
    return load_dimension("loteries")


# ── Utilidades ──────────────────────────────────────────────────────────────

def list_fact_months(prefix: str = "tickets") -> list[str]:
    """Devuelve lista de archivos facts ordenados (ej. tickets_2025-10.parquet)."""
    facts_dir = DATA_DIR / "facts"
    files = sorted(facts_dir.glob(f"{prefix}_*.parquet"))
    return [f.name for f in files]


def load_parquet(path: Path | str) -> pd.DataFrame:
    """Loader genérico para cualquier parquet."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    with _conn() as conn:
        return conn.execute(f"SELECT * FROM '{path}'").df()
