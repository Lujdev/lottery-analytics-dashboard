"""Pipeline de anomaly detection: IsolationForest por agencia-período."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from ml.config import (
    DEFAULT_ANOMALY_CONTAMINATION,
    MIN_AGENCIES_FOR_CLUSTERING,
    RUN_DATE,
    RUN_ID,
    parquet_path,
)
from ml.features import build_agency_features
from ml.schemas import validate_schema, with_run_metadata

logger = logging.getLogger(__name__)


def train_anomaly_detection(
    output_path: Path | None = None,
    window_days: int = 90,
    contamination: float = DEFAULT_ANOMALY_CONTAMINATION,
) -> pd.DataFrame:
    """Entrena IsolationForest sobre features agregadas por agencia.

    Como los datos disponibles son transversales (una fila por agencia en
    ventana corriente), se entrena un modelo global y se puntuarán todas las
    agencias.  El campo `period` se fija al primer día de la ventana.

    Returns DataFrame con schema anomaly_scores.
    """
    output_path = output_path or parquet_path("anomaly_scores")

    logger.info("Anomaly: cargando features (window=%d días)...", window_days)
    df = build_agency_features(window_days=window_days)

    if len(df) < MIN_AGENCIES_FOR_CLUSTERING:
        logger.error("Anomaly abortado: %d agencias < mínimo %d.", len(df), MIN_AGENCIES_FOR_CLUSTERING)
        empty = pd.DataFrame(columns=[
            "agency_id", "period", "anomaly_score", "is_anomaly",
            "severity", "exclusion_reason", "run_id", "run_date",
        ])
        empty = with_run_metadata(empty, RUN_ID, RUN_DATE)
        validate_schema(empty, "anomaly_scores")
        return empty

    feature_cols = [c for c in df.columns if c != "agency_id"]
    X = df[feature_cols].fillna(0).values

    logger.info("Anomaly: escalando %d agencias × %d features...", X.shape[0], X.shape[1])
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    logger.info("Anomaly: entrenando IsolationForest(contamination=%.3f)...", contamination)
    clf = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=200,
    )
    clf.fit(X_scaled)
    scores = clf.decision_function(X_scaled)
    outliers = clf.predict(X_scaled) == -1

    # Severidad basada en percentiles de score dentro de outliers
    severity = pd.Series("normal", index=df.index, dtype=object)
    if outliers.any():
        outlier_scores = scores[outliers]
        q25, q75 = np.percentile(outlier_scores, [25, 75])
        severity.loc[outliers] = np.where(
            scores[outliers] <= q25, "critical",
            np.where(scores[outliers] <= q75, "warning", "normal")
        )

    # Period = primer día del mes de RUN_DATE (mensual por convención)
    period = pd.to_datetime(RUN_DATE).replace(day=1)

    result = pd.DataFrame({
        "agency_id": df["agency_id"].astype(int),
        "period": period,
        "anomaly_score": scores,
        "is_anomaly": outliers,
        "severity": severity,
        "exclusion_reason": pd.NA,
    })

    result = with_run_metadata(result, RUN_ID, RUN_DATE)
    validate_schema(result, "anomaly_scores")

    result.to_parquet(output_path, index=False)
    logger.info("Anomaly: escrito %s (%d filas, %d outliers).", output_path, len(result), outliers.sum())
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    train_anomaly_detection()
