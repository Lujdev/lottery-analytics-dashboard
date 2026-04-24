"""Contratos de storage para predicciones.

Define schemas exactos de salida y helpers para validar/ensamblar
DataFrames antes de persistir en data/predictions/*.parquet.
"""
from __future__ import annotations

import logging
from typing import Callable

import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_float_dtype, is_integer_dtype

logger = logging.getLogger(__name__)

# ── Schemas ─────────────────────────────────────────────────────────────────

AGENCY_CLUSTERS_SCHEMA: dict[str, str] = {
    "agency_id": "int64",
    "cluster_id": "int64",
    "pca_x": "float64",
    "pca_y": "float64",
    "centroid_distance": "float64",
    "run_id": "object",
    "run_date": "datetime64[ns]",
}

ANOMALY_SCORES_SCHEMA: dict[str, str] = {
    "agency_id": "int64",
    "period": "datetime64[ns]",
    "anomaly_score": "float64",
    "is_anomaly": "bool",
    "severity": "object",
    "exclusion_reason": "object",
    "run_id": "object",
    "run_date": "datetime64[ns]",
}

FORECAST_SALES_SCHEMA: dict[str, str] = {
    "entity_type": "object",
    "entity_id": "int64",
    "forecast_date": "datetime64[ns]",
    "yhat": "float64",
    "yhat_lower": "float64",
    "yhat_upper": "float64",
    "model": "object",
    "run_id": "object",
    "run_date": "datetime64[ns]",
}

AGENCY_CHURN_RISK_SCHEMA: dict[str, str] = {
    "agency_id": "int64",
    "churn_probability": "float64",
    "risk_band": "object",
    "top_features": "object",
    "prediction_date": "datetime64[ns]",
    "run_id": "object",
}

BASKET_RULES_SCHEMA: dict[str, str] = {
    "antecedent": "object",
    "consequent": "object",
    "support": "float64",
    "confidence": "float64",
    "lift": "float64",
    "period": "datetime64[ns]",
    "run_id": "object",
}

SCHEMAS: dict[str, dict[str, str]] = {
    "agency_clusters": AGENCY_CLUSTERS_SCHEMA,
    "anomaly_scores": ANOMALY_SCORES_SCHEMA,
    "forecast_sales": FORECAST_SALES_SCHEMA,
    "agency_churn_risk": AGENCY_CHURN_RISK_SCHEMA,
    "basket_rules": BASKET_RULES_SCHEMA,
}

# ── Validación ──────────────────────────────────────────────────────────────

def _check_column(df: pd.DataFrame, col: str, expected_dtype: str) -> list[str]:
    errors: list[str] = []
    if col not in df.columns:
        errors.append(f"Falta columna obligatoria: {col}")
        return errors

    actual = str(df[col].dtype)
    # Aceptar equivalencias amplias
    if expected_dtype == "int64" and not is_integer_dtype(df[col]):
        errors.append(f"{col}: esperado entero, got {actual}")
    if expected_dtype == "float64" and not is_float_dtype(df[col]):
        errors.append(f"{col}: esperado float, got {actual}")
    if expected_dtype == "bool" and not is_bool_dtype(df[col]):
        errors.append(f"{col}: esperado bool, got {actual}")
    if expected_dtype == "datetime64[ns]" and not is_datetime64_any_dtype(df[col]):
        errors.append(f"{col}: esperado datetime, got {actual}")
    return errors


def validate_schema(df: pd.DataFrame, schema_name: str) -> pd.DataFrame:
    """Valida que un DataFrame cumpla el schema; logea warnings y devuelve el df."""
    schema = SCHEMAS.get(schema_name)
    if schema is None:
        raise ValueError(f"Schema desconocido: {schema_name}")

    all_errors: list[str] = []
    for col, expected in schema.items():
        all_errors.extend(_check_column(df, col, expected))

    if all_errors:
        for err in all_errors:
            logger.warning("[schema:%s] %s", schema_name, err)
    else:
        logger.info("Schema '%s' validado OK (%d filas).", schema_name, len(df))
    return df


# ── Ensambladores (empty builders) ──────────────────────────────────────────

def empty_frame(schema_name: str) -> pd.DataFrame:
    """Devuelve un DataFrame vacío con las columnas y tipos del schema."""
    schema = SCHEMAS[schema_name]
    return pd.DataFrame({col: pd.Series(dtype=typ) for col, typ in schema.items()})


def with_run_metadata(df: pd.DataFrame, run_id: str, run_date) -> pd.DataFrame:
    """Asegura que existan run_id y run_date; los sobrescribe si ya existen."""
    df = df.copy()
    df["run_id"] = run_id
    df["run_date"] = pd.to_datetime(run_date)
    return df
