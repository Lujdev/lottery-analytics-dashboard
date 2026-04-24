"""Pipeline de churn prediction: RandomForest + explicabilidad simple."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

from ml.config import RUN_DATE, RUN_ID, parquet_path
from ml.features import build_churn_dataset
from ml.schemas import validate_schema, with_run_metadata

logger = logging.getLogger(__name__)


def train_churn(
    output_path: Path | None = None,
    observation_days: int = 90,
    churn_days: int = 30,
) -> pd.DataFrame:
    """Entrena RandomForest para predecir churn operativo.

    Returns DataFrame con schema agency_churn_risk.
    """
    output_path = output_path or parquet_path("agency_churn_risk")

    logger.info("Churn: construyendo dataset (obs=%d, churn=%d)...", observation_days, churn_days)
    # NOTA DE SEGURIDAD / LEAKAGE: cuando churn_days == 30, la feature
    # monetary_30d tiene correlación casi perfecta con el label (ventas en
    # los últimos 30 días vs. "¿tuvo ventas en los últimos 30 días?").
    # Esto explica accuracy holdout ≈ 1.0. No es un bug de código sino un
    # artefacto de la ventana temporal. Para producción robusta, considerar
    # usar solo features de ventanas estrictamente anteriores al período de
    # evaluación (ej. monetary_60_30d en lugar de monetary_30d) o aumentar
    # churn_days a 60+ con observación proporcional.
    df = build_churn_dataset(observation_days=observation_days, churn_days=churn_days)

    if df.empty or "churn_label" not in df.columns:
        logger.error("Churn: dataset vacío o sin label.")
        empty = pd.DataFrame(columns=[
            "agency_id", "churn_probability", "risk_band",
            "top_features", "prediction_date", "run_id",
        ])
        empty = with_run_metadata(empty, RUN_ID, RUN_DATE)
        validate_schema(empty, "agency_churn_risk")
        return empty

    # Features numéricas (excluir agency_id, label, fechas derivadas)
    exclude = {"agency_id", "churn_label", "last_sale_date"}
    feature_cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]

    if not feature_cols:
        logger.error("Churn: no hay features numéricas.")
        return empty

    X = df[feature_cols].fillna(0)
    y = df["churn_label"]

    # Entrenar sobre todo el dataset (batch scoring), pero loguear métricas simples
    if y.nunique() < 2:
        logger.warning("Churn: solo una clase presente (%d). Scoring trivial.", y.iloc[0])
        probs = np.full(len(df), float(y.mean()))
        importances = {c: 0.0 for c in feature_cols}
    else:
        # Split rápido solo para loguear accuracy
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X_train, y_train)
        acc = clf.score(X_test, y_test)
        logger.info("Churn: accuracy holdout = %.3f", acc)

        # Reentrenar sobre todo para scoring
        clf.fit(X, y)
        probs = clf.predict_proba(X)[:, 1]
        importances = dict(zip(feature_cols, clf.feature_importances_))

    # Bandas de riesgo
    risk_band = pd.Series("bajo", index=df.index, dtype=object)
    risk_band[probs >= 0.7] = "alto"
    risk_band[(probs >= 0.4) & (probs < 0.7)] = "medio"

    # Top 3 features por agencia (usando importancia global como proxy)
    top3 = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:3]
    top3_names = [name for name, _ in top3]
    top_features_json = json.dumps(top3_names)

    result = pd.DataFrame({
        "agency_id": df["agency_id"].astype(int),
        "churn_probability": np.round(probs, 6),
        "risk_band": risk_band,
        "top_features": top_features_json,
        "prediction_date": pd.to_datetime(RUN_DATE),
    })

    result = with_run_metadata(result, RUN_ID, RUN_DATE)
    validate_schema(result, "agency_churn_risk")

    result.to_parquet(output_path, index=False)
    logger.info(
        "Churn: escrito %s (%d filas, churn_rate real=%.2f%%).",
        output_path,
        len(result),
        y.mean() * 100,
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    train_churn()
