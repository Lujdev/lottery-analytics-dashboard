"""Auditoría de interacciones LLM.

Registra cada llamada en logs/llm_YYYY-MM-DD.jsonl con trazabilidad completa.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from ml.config import LOGS_DIR, RUN_ID

logger = logging.getLogger(__name__)


def _today_log_path() -> Path:
    return LOGS_DIR / f"llm_{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def log_interaction(
    prompt: str,
    response_text: str,
    model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: float | None = None,
) -> None:
    """Persiste una interacción LLM en el log diario JSONL."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "run_id": RUN_ID,
        "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
        "response_hash": hashlib.sha256(response_text.encode()).hexdigest()[:16],
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
    }
    path = _today_log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo escribir auditoría LLM: %s", exc)
