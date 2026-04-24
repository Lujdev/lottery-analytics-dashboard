"""Generador de reporte ejecutivo mensual CEO."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from dashboard.llm.audit import log_interaction
from dashboard.llm.cache import get as cache_get, set as cache_set
from dashboard.llm.openrouter_client import chat_completion, is_configured
from ml.config import PREDICTIONS_DIR, REPORTS_DIR, RUN_ID

logger = logging.getLogger(__name__)

REQUIRED_FILES = [
    "agency_clusters.parquet",
    "anomaly_scores.parquet",
    "forecast_sales.parquet",
    "agency_churn_risk.parquet",
    "basket_rules.parquet",
]

SYSTEM_PROMPT = (
    "Sos un analista senior de PremierPluss redactando un reporte mensual CEO. "
    "Usá SOLO los datos del contexto. Estructurá el reporte en: "
    "1) Resumen Ejecutivo, 2) Desempeño, 3) Riesgos, 4) Próximos Pasos. "
    "Incluí el período y al menos 3 métricas verificables."
)


def _validate_month_files(month: str, predictions_dir: Path) -> list[str]:
    missing: list[str] = []
    for fname in REQUIRED_FILES:
        if not (predictions_dir / fname).exists():
            missing.append(fname)
    return missing


def generate_executive_report(month: str, predictions_dir: Path | None = None) -> Path:
    """Genera y persiste el reporte ejecutivo mensual en markdown.

    Args:
        month: formato 'YYYY-MM'.
        predictions_dir: ruta base con parquets de predicciones.

    Returns:
        Ruta al archivo markdown generado.

    Raises:
        RuntimeError: si faltan archivos obligatorios o el mes es inválido.
    """
    import re
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise RuntimeError(f"Formato de mes inválido: '{month}'. Use YYYY-MM.")

    predictions_dir = predictions_dir or PREDICTIONS_DIR
    missing = _validate_month_files(month, predictions_dir)
    if missing:
        raise RuntimeError(f"Reporte bloqueado para {month}: faltan {missing}")

    cache_key = f"exec_report:{month}:{RUN_ID}"
    cached = cache_get(cache_key)

    # Cargar contexto resumido (nunca filas raw)
    lines = [f"Período: {month}", f"Run ID: {RUN_ID}", ""]
    for fname in REQUIRED_FILES:
        df = pd.read_parquet(predictions_dir / fname)
        name = fname.replace(".parquet", "")
        lines.append(f"## {name}")
        lines.append(f"Registros: {len(df)}")
        if "severity" in df.columns:
            crit = len(df[df["severity"] == "critical"])
            lines.append(f"Críticos: {crit}")
        if "risk_band" in df.columns:
            high = len(df[df["risk_band"] == "alto"])
            lines.append(f"Riesgo alto: {high}")
        if "yhat" in df.columns:
            lines.append(f"Forecast último: {df['yhat'].iloc[-1]:,.0f}")
        lines.append("")

    context = "\n".join(lines)

    if cached:
        text = cached
    elif not is_configured():
        text = (
            f"# Reporte Ejecutivo — {month}\n\n"
            f"**Run ID:** {RUN_ID}\n\n"
            f"> 🔒 *Modo offline:* OpenRouter no está configurado. "
            f"A continuación se presenta el resumen estructurado de datos sin narrativa LLM.\n\n"
            f"{context}"
        )
    else:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Contexto:\n{context}\n\nGenerá el reporte ejecutivo en markdown."},
        ]
        try:
            start = time.time()
            resp = chat_completion(messages, temperature=0.3, max_tokens=2048)
            latency = (time.time() - start) * 1000
            text = resp["choices"][0]["message"]["content"]
            log_interaction(
                prompt=f"exec_report:{month}",
                response_text=text,
                model=resp.get("model", "unknown"),
                input_tokens=resp.get("usage", {}).get("prompt_tokens"),
                output_tokens=resp.get("usage", {}).get("completion_tokens"),
                latency_ms=latency,
            )
            cache_set(cache_key, text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error generando reporte ejecutivo: %s", exc)
            text = (
                f"# Reporte Ejecutivo — {month}\n\n"
                f"**Run ID:** {RUN_ID}\n\n"
                f"> ⚠️ *Error al contactar al modelo:* {exc}\n\n"
                f"{context}"
            )

    out_path = REPORTS_DIR / f"executive_{month}.md"
    out_path.write_text(text, encoding="utf-8")
    logger.info("Reporte ejecutivo guardado en %s", out_path)
    return out_path
