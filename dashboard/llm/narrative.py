"""Generación de narrativa ejecutiva sobre predicciones."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from dashboard.llm.audit import log_interaction
from dashboard.llm.cache import get as cache_get, set as cache_set
from dashboard.llm.context import contexto_anomalia_agencia
from dashboard.llm.openrouter_client import chat_completion, is_configured, prompt_hash
from ml.config import PREDICTIONS_DIR, RUN_ID

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Sos un analista senior de PremierPluss. "
    "Respondé solo con datos del contexto proporcionado. No inventés cifras. "
    "Usá lenguaje de negocio claro y estructurado."
)


def _load_predictions(predictions_dir: Path) -> dict[str, pd.DataFrame]:
    """Carga los 5 parquets de predicciones si existen."""
    files = {
        "clusters": predictions_dir / "agency_clusters.parquet",
        "anomalies": predictions_dir / "anomaly_scores.parquet",
        "forecast": predictions_dir / "forecast_sales.parquet",
        "churn": predictions_dir / "agency_churn_risk.parquet",
        "basket": predictions_dir / "basket_rules.parquet",
    }
    out = {}
    for key, path in files.items():
        if path.exists():
            out[key] = pd.read_parquet(path)
        else:
            out[key] = pd.DataFrame()
    return out


def generate_narrative(period: str, predictions_dir: Path | None = None) -> str:
    """Genera narrativa ejecutiva para un período dado.

    Args:
        period: formato 'YYYY-MM'.
        predictions_dir: ruta a data/predictions/.

    Returns:
        Texto markdown con la narrativa o mensaje de error si faltan datos.
    """
    predictions_dir = predictions_dir or PREDICTIONS_DIR
    cache_key = f"narrative:{period}:{RUN_ID}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    preds = _load_predictions(predictions_dir)
    missing = [k for k, df in preds.items() if df.empty]
    if missing:
        msg = f"Narrativa bloqueada: faltan datasets {', '.join(missing)} para {period}."
        logger.warning(msg)
        return msg

    # Resumir contexto estructurado (top-K, promedios) — nunca filas raw
    context_lines = [f"Período: {period}", f"Run ID: {RUN_ID}", ""]
    if not preds["clusters"].empty:
        n = len(preds["clusters"])
        context_lines.append(f"Clusters: {n} agencias segmentadas.")
    if not preds["anomalies"].empty:
        crit = preds["anomalies"][preds["anomalies"]["severity"] == "critical"]
        context_lines.append(f"Anomalías críticas: {len(crit)}.")
    if not preds["forecast"].empty:
        latest = preds["forecast"]["forecast_date"].max()
        context_lines.append(f"Forecast hasta: {latest}.")
    if not preds["churn"].empty:
        high = preds["churn"][preds["churn"]["risk_band"] == "alto"]
        context_lines.append(f"Churn alto: {len(high)} agencias.")
    if not preds["basket"].empty:
        top_rule = preds["basket"].sort_values("lift", ascending=False).head(1)
        if not top_rule.empty:
            ant = top_rule.iloc[0]["antecedent"]
            cons = top_rule.iloc[0]["consequent"]
            context_lines.append(f"Regla top basket: {ant} → {cons}.")

    context = "\n".join(context_lines)
    if not is_configured():
        text = (
            f"# Resumen de predicciones — {period}\n\n"
            f"> 🔒 *Modo offline:* OpenRouter no está configurado.\n\n"
            f"{context}"
        )
        cache_set(cache_key, text)
        return text

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Contexto de predicciones:\n{context}\n\nGenerá un resumen ejecutivo en español."},
    ]

    try:
        start = time.time()
        resp = chat_completion(messages, temperature=0.3, max_tokens=1024)
        latency = (time.time() - start) * 1000
        text = resp["choices"][0]["message"]["content"]
        log_interaction(
            prompt=f"narrative:{period}",
            response_text=text,
            model=resp.get("model", "unknown"),
            input_tokens=resp.get("usage", {}).get("prompt_tokens"),
            output_tokens=resp.get("usage", {}).get("completion_tokens"),
            latency_ms=latency,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error generando narrativa: %s", exc)
        text = (
            f"# Resumen de predicciones — {period}\n\n"
            f"> ⚠️ *Error al contactar al modelo:* {exc}\n\n"
            f"{context}"
        )

    cache_set(cache_key, text)
    return text


def generate_anomaly_narrative(agency_id: int) -> str:
    """Genera narrativa explicativa para una agencia outlier específica.

    Args:
        agency_id: ID de la agencia a narrar.

    Returns:
        Texto markdown con la explicación o mensaje de error/control.
    """
    cache_key = f"anomaly_narrative:{agency_id}:{RUN_ID}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    ctx = contexto_anomalia_agencia(agency_id)
    if not ctx.get("anomalia"):
        return "Esta agencia no tiene registro de anomalías en la última corrida."

    lines = [
        f"Agencia ID: {agency_id}",
        f"Período: {ctx['anomalia'].get('period', 'N/A')}",
        f"Score de anomalía: {ctx['anomalia']['anomaly_score']:.3f}",
        f"Severidad: {ctx['anomalia']['severity']}",
    ]
    m = ctx.get("metricas", {})
    if m:
        lines.extend([
            f"Ventas históricas: {m.get('ventas', 0):,.0f}",
            f"% Margen: {m.get('pct_margen', 'N/A')}",
            f"Días activos: {m.get('dias_activos', 'N/A')}",
            f"Productos distintos: {m.get('productos_distintos', 'N/A')}",
        ])

    context = "\n".join(lines)

    if not is_configured():
        text = (
            f"# Análisis de anomalía — Agencia {agency_id}\n\n"
            f"> 🔒 *Modo offline:* OpenRouter no está configurado.\n\n"
            f"{context}"
        )
        cache_set(cache_key, text)
        return text

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Contexto de agencia anómala:\n{context}\n\n"
            "Generá una explicación ejecutiva breve (máx 200 palabras) de por qué esta agencia "
            "podría ser anómala y qué acciones sugerirías. Respondé solo con el texto, sin listas numeradas."
        )},
    ]

    try:
        start = time.time()
        resp = chat_completion(messages, temperature=0.3, max_tokens=512)
        latency = (time.time() - start) * 1000
        text = resp["choices"][0]["message"]["content"]
        log_interaction(
            prompt=f"anomaly_narrative:{agency_id}",
            response_text=text,
            model=resp.get("model", "unknown"),
            input_tokens=resp.get("usage", {}).get("prompt_tokens"),
            output_tokens=resp.get("usage", {}).get("completion_tokens"),
            latency_ms=latency,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error generando narrativa de anomalía: %s", exc)
        text = f"⚠️ No se pudo generar la narrativa: {exc}"

    cache_set(cache_key, text)
    return text
