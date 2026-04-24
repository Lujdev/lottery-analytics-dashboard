"""Orquestador batch del pipeline predictivo.

Ejecuta pipelines en orden, registra errores y continúa/falla según criticidad.
Uso:
    python -m ml.run_all
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from ml.config import LOGS_DIR, RUN_DATE, RUN_ID, PREDICTIONS_DIR
from ml.schemas import empty_frame, validate_schema, with_run_metadata

logger = logging.getLogger(__name__)

# Resultados acumulados para resumen
STAGES: list[tuple[str, bool, str]] = []


def _log_stage(name: str, ok: bool, detail: str) -> None:
    STAGES.append((name, ok, detail))
    if ok:
        logger.info("[STAGE OK] %s: %s", name, detail)
    else:
        logger.error("[STAGE FAIL] %s: %s", name, detail)


def _run_clustering() -> bool:
    try:
        from ml.train_clustering import train_clustering

        df = train_clustering()
        if df.empty:
            _log_stage("clustering", False, "output vacío")
            return False
        _log_stage("clustering", True, f"{len(df)} agencias clusterizadas")
        return True
    except Exception as exc:
        _log_stage("clustering", False, str(exc))
        return False


def _run_anomaly() -> bool:
    try:
        from ml.train_anomaly import train_anomaly_detection

        df = train_anomaly_detection()
        if df.empty:
            _log_stage("anomaly", False, "output vacío")
            return False
        outliers = int(df["is_anomaly"].sum()) if "is_anomaly" in df.columns else 0
        _log_stage("anomaly", True, f"{len(df)} agencias puntuadas, {outliers} outliers")
        return True
    except Exception as exc:
        _log_stage("anomaly", False, str(exc))
        return False


def _run_forecast() -> bool:
    try:
        from ml.train_forecast import train_forecast

        df = train_forecast()
        if df.empty:
            _log_stage("forecast", False, "output vacío")
            return False
        models = df["model"].value_counts().to_dict() if "model" in df.columns else {}
        _log_stage("forecast", True, f"{len(df)} filas, models={models}")
        return True
    except Exception as exc:
        _log_stage("forecast", False, str(exc))
        return False


def _run_churn() -> bool:
    try:
        from ml.train_churn import train_churn

        df = train_churn()
        if df.empty:
            _log_stage("churn", False, "output vacío")
            return False
        high = int((df["risk_band"] == "alto").sum()) if "risk_band" in df.columns else 0
        _log_stage("churn", True, f"{len(df)} agencias, {high} riesgo alto")
        return True
    except Exception as exc:
        _log_stage("churn", False, str(exc))
        return False


def _run_basket() -> bool:
    try:
        from ml.train_basket import train_basket

        df = train_basket()
        if df.empty:
            _log_stage("basket", False, "output vacío")
            return False
        _log_stage("basket", True, f"{len(df)} reglas descubiertas")
        return True
    except Exception as exc:
        _log_stage("basket", False, str(exc))
        return False


def main() -> int:
    """Orquestador principal. Devuelve exit code 0 si todo OK, 1 si algún crítico falla."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOGS_DIR / f"ml_run_{RUN_ID}.log", encoding="utf-8"),
        ],
    )

    logger.info("=" * 60)
    logger.info("ML Batch Run start — run_id=%s date=%s", RUN_ID, RUN_DATE)
    logger.info("=" * 60)

    # Asegurar directorio de predicciones
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Orden de ejecución: no críticos entre sí, fallo individual no bloquea al resto
    # salvo que quieras detener.  Elegimos continuar para maximizar outputs útiles.
    results = {
        "clustering": _run_clustering(),
        "anomaly": _run_anomaly(),
        "forecast": _run_forecast(),
        "churn": _run_churn(),
        "basket": _run_basket(),
    }

    # Resumen
    logger.info("=" * 60)
    logger.info("ML Batch Run summary — run_id=%s", RUN_ID)
    for name, ok, detail in STAGES:
        status = "OK" if ok else "FAIL"
        logger.info("  %-12s %-4s %s", name, status, detail)
    logger.info("=" * 60)

    ok_count = sum(1 for v in results.values() if v)
    total = len(results)
    logger.info("Resultado: %d/%d pipelines exitosos.", ok_count, total)

    return 0 if ok_count == total else 1


if __name__ == "__main__":
    sys.exit(main())
