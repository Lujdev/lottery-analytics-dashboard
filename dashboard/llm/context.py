"""Recuperación de contexto sanitizado para LLM.

Nunca expone PII ni filas raw. Solo agregados controlados.
"""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd

from dashboard.data import (
    DATA_DIR,
    prediccion_anomalias,
    prediccion_churn,
    prediccion_clusters,
    prediccion_forecast,
    prediccion_basket,
)

logger = logging.getLogger(__name__)

PII_COLUMNS = {"name", "user_id", "ticket_id", "anull_by", "transaction_id", "phone", "email"}


def _conn():
    return duckdb.connect()


def sanitizar_df(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina columnas con PII antes de serializar a prompt."""
    drop_cols = [c for c in df.columns if c.lower() in PII_COLUMNS]
    return df.drop(columns=drop_cols, errors="ignore")


def metricas_agencia(agency_id: int) -> dict:
    """Devuelve métricas agregadas de una agencia para contexto LLM."""
    agency_id = int(agency_id)
    sql = f"""
        SELECT
            SUM(s.sales) AS ventas,
            SUM(s.prize) AS premios,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen,
            COUNT(DISTINCT s.fecha) AS dias_activos,
            COUNT(DISTINCT s.new_product_id) AS productos_distintos
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        WHERE s.agency_id = {agency_id}
    """
    with _conn() as conn:
        row = conn.execute(sql).fetchone()
    if not row or row[0] is None:
        return {}
    return {
        "agency_id": agency_id,
        "ventas": float(row[0]),
        "premios": float(row[1]),
        "pct_margen": float(row[2]) if row[2] is not None else None,
        "dias_activos": int(row[3]),
        "productos_distintos": int(row[4]),
    }


def contexto_anomalia_agencia(agency_id: int) -> dict:
    """Contexto combinado: anomalía + métricas de negocio."""
    df_anom = prediccion_anomalias()
    row_anom = df_anom[df_anom["agency_id"] == agency_id]
    anomalia = {}
    if not row_anom.empty:
        r = row_anom.iloc[0]
        anomalia = {
            "anomaly_score": float(r["anomaly_score"]),
            "severity": str(r["severity"]),
            "period": str(r["period"]),
        }
    metricas = metricas_agencia(agency_id)
    return {"anomalia": anomalia, "metricas": metricas}


def contexto_kpis_predictivos() -> dict:
    """Resumen de todos los modelos predictivos para reportes/chat."""
    out = {}
    for name, fn in [
        ("clusters", prediccion_clusters),
        ("anomalies", prediccion_anomalias),
        ("forecast", prediccion_forecast),
        ("churn", prediccion_churn),
        ("basket", prediccion_basket),
    ]:
        try:
            df = fn()
            out[name] = {
                "registros": len(df),
                "columnas": list(df.columns),
            }
            if "severity" in df.columns:
                out[name]["criticos"] = int((df["severity"] == "critical").sum())
            if "risk_band" in df.columns:
                out[name]["riesgo_alto"] = int((df["risk_band"] == "alto").sum())
            if "yhat" in df.columns:
                out[name]["ultimo_yhat"] = float(df["yhat"].iloc[-1]) if not df.empty else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error cargando %s para contexto: %s", name, exc)
            out[name] = {"error": str(exc)}
    return out
