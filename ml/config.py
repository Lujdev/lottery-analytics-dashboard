"""Configuración central del pipeline predictivo."""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Paths ───────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.resolve()
DATA_DIR = REPO_ROOT / "data"
PREDICTIONS_DIR = DATA_DIR / "predictions"
REPORTS_DIR = DATA_DIR / "reports"
CACHE_DIR = DATA_DIR / "cache"
LOGS_DIR = REPO_ROOT / "logs"

for _d in (PREDICTIONS_DIR, REPORTS_DIR, CACHE_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Run metadata ────────────────────────────────────────────────────────────
RUN_ID = os.getenv("ML_RUN_ID") or uuid.uuid4().hex[:12]
RUN_DATE = date.today()

# ── Umbrales ────────────────────────────────────────────────────────────────
DEFAULT_FORECAST_HORIZON_MONTHS = 3
DEFAULT_K_CLUSTERS = 4
DEFAULT_ANOMALY_CONTAMINATION = 0.05
DEFAULT_CHURN_LABEL_DAYS = 30
DEFAULT_CHURN_OBSERVATION_DAYS = 90
DEFAULT_BASKET_MIN_SUPPORT = 0.01
DEFAULT_BASKET_MIN_CONFIDENCE = 0.30
DEFAULT_BASKET_MIN_LIFT = 1.0
MIN_AGENCIES_FOR_CLUSTERING = DEFAULT_K_CLUSTERS + 1
MIN_MONTHS_FOR_FORECAST = 3

# ── OpenRouter / LLM ────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-flash-1.5")
OPENROUTER_TIMEOUT_CONNECT = int(os.getenv("OPENROUTER_TIMEOUT_CONNECT", "10"))
OPENROUTER_TIMEOUT_READ = int(os.getenv("OPENROUTER_TIMEOUT_READ", "30"))
LLM_ENABLED = os.getenv("LLM_ENABLED", "false").lower() in ("true", "1", "yes")


def parquet_path(name: str) -> Path:
    """Ruta canónica para un parquet de predicciones."""
    return PREDICTIONS_DIR / f"{name}.parquet"
