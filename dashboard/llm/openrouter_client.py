"""Cliente thin HTTP para OpenRouter.

No depende de LangChain ni abstracciones pesadas.
Control total de timeouts, retries y headers.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from ml.config import (
    LLM_ENABLED,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_TIMEOUT_CONNECT,
    OPENROUTER_TIMEOUT_READ,
)

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def is_configured() -> bool:
    """Devuelve True si la API key de OpenRouter está presente y LLM_ENABLED es true."""
    return bool(OPENROUTER_API_KEY) and LLM_ENABLED


def chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    retries: int = 3,
) -> dict[str, Any]:
    """Envía un chat completion a OpenRouter con retries y backoff.

    Retorna el dict JSON de respuesta cruda o lanza excepción tras agotar retries.
    """
    try:
        import httpx
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Dependencia 'httpx' no instalada. Instalá con: uv sync --extra llm") from exc

    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY no configurada.")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://premierpluss.com",
        "X-Title": "PremierPluss Analytics",
    }

    payload = {
        "model": model or OPENROUTER_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(
                timeout=httpx.Timeout(OPENROUTER_TIMEOUT_READ, connect=OPENROUTER_TIMEOUT_CONNECT)
            ) as client:
                resp = client.post(OPENROUTER_URL, headers=headers, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = 2 ** attempt
            logger.warning("OpenRouter intento %d/%d falló: %s. Esperando %ds...", attempt, retries, exc, wait)
            time.sleep(wait)

    raise RuntimeError(f"OpenRouter falló tras {retries} intentos: {last_err}")


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
