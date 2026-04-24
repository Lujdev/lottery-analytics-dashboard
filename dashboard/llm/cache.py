"""Cache simple en disco para respuestas LLM.

Usa pickle local en data/cache/llm_cache.pkl sin infra adicional.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path

from ml.config import CACHE_DIR

logger = logging.getLogger(__name__)

_CACHE_PATH = CACHE_DIR / "llm_cache.pkl"
_cache: dict[str, str] = {}
_loaded = False


def _load() -> None:
    global _loaded, _cache
    if _loaded:
        return
    if _CACHE_PATH.exists():
        try:
            with open(_CACHE_PATH, "rb") as f:
                _cache = pickle.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo cargar cache LLM: %s", exc)
            _cache = {}
    _loaded = True


def _save() -> None:
    try:
        with open(_CACHE_PATH, "wb") as f:
            pickle.dump(_cache, f)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo guardar cache LLM: %s", exc)


def get(key: str) -> str | None:
    _load()
    return _cache.get(key)


def set(key: str, value: str) -> None:
    _load()
    _cache[key] = value
    _save()
