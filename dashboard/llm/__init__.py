"""Capa LLM del dashboard de PremierPluss Analytics."""
from dashboard.llm.audit import log_interaction
from dashboard.llm.cache import get, set
from dashboard.llm.chat_assistant import answer, render_chat_ui
from dashboard.llm.context import contexto_anomalia_agencia, contexto_kpis_predictivos, sanitizar_df
from dashboard.llm.executive_report import generate_executive_report
from dashboard.llm.narrative import generate_anomaly_narrative, generate_narrative
from dashboard.llm.openrouter_client import chat_completion, is_configured, prompt_hash

__all__ = [
    "log_interaction",
    "get",
    "set",
    "answer",
    "render_chat_ui",
    "generate_executive_report",
    "generate_narrative",
    "generate_anomaly_narrative",
    "chat_completion",
    "is_configured",
    "prompt_hash",
    "contexto_anomalia_agencia",
    "contexto_kpis_predictivos",
    "sanitizar_df",
]
