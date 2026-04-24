"""Motor del chat asistente con datos.

Flujo dual:
1. Catálogo cerrado de funciones Python (respuestas rápidas, 100% seguro).
2. SQL asistido por LLM con guardrails y ejecución en DuckDB sandboxed.

Nunca genera SQL libre sin validación.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Callable

import duckdb
import pandas as pd
import streamlit as st

from dashboard.data import (
    kpis_globales,
    top_agencias,
    ventas_por_mes,
    ventas_por_producto,
    ventas_por_agencia_y_producto,
    ventas_por_hora,
    ventas_por_sorteo_y_hora,
    prediccion_anomalias,
    prediccion_churn,
    prediccion_clusters,
    prediccion_forecast,
    prediccion_basket,
)
from dashboard.llm.audit import log_interaction
from dashboard.llm.cache import get as cache_get, set as cache_set
from dashboard.llm.openrouter_client import chat_completion, is_configured, prompt_hash
from ml.config import RUN_ID

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Sos un analista comercial senior de PremierPluss. "
    "Respondé con naturalidad, como en una conversación de negocios. "
    "NUNCA uses términos técnicos como 'yhat', 'yhat_lower', 'yhat_upper', 'entity_type', "
    "'anomaly_score', 'centroid_distance', 'pca', o 'cluster_id'. "
    "En su lugar usá lenguaje de negocio: 'pronóstico de ventas', 'proyección estimada', "
    "'rango esperado (mejor y peor escenario)', 'puntuación de riesgo', 'grupo de comportamiento'. "
    "Si no tenés datos para responder, decí claramente que no tenés esa información "
    "y explicá por qué (por ejemplo: 'No tengo pronóstico para esa agencia específica porque "
    "solo genero pronósticos para el top 50 de agencias por volumen'). "
    "NUNCA inventés datos ni afirmes tendencias sin evidencia en los resultados. "
    "Presentá los montos en millones o billones de Bs. cuando sea apropiado, no en notación científica."
)

SQL_SYSTEM_PROMPT = (
    "Sos un analista de datos. Generá UNA sola consulta SQL SELECT para responder la pregunta. "
    "Usá SOLO estas vistas. No inventés tablas ni columnas. "
    "Respondé SOLO con la consulta SQL, sin explicaciones.\n\n"
    "IMPORTANTE sobre forecast (v_forecast):\n"
    "- Solo contiene pronósticos para: (1) nivel nacional (entity_type='nacional') y "
    "(2) el top 50 de agencias individuales por volumen (entity_type='agency').\n"
    "- Si la pregunta es sobre una agencia específica que no está en el top 50, "
    "la consulta devolverá vacío. Eso es correcto.\n\n"
    "Vistas disponibles:\n"
    "- v_ventas_mes(mes TIMESTAMP, ventas DOUBLE, premios DOUBLE, margen_bruto DOUBLE, pct_margen DOUBLE)\n"
    "- v_top_agencias(agencia VARCHAR, ventas DOUBLE, premios DOUBLE, ganancias DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_producto(producto VARCHAR, tipo BIGINT, ventas DOUBLE, premios DOUBLE, margen_bruto DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_agencia_producto(agencia VARCHAR, producto VARCHAR, ventas DOUBLE, premios DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_hora(hora VARCHAR, ventas DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_sorteo_hora(sorteo VARCHAR, hora VARCHAR, ventas DOUBLE, premios DOUBLE, pct_margen DOUBLE)\n"
    "- v_anomalias(agency_id BIGINT, anomaly_score DOUBLE, severity VARCHAR, period DATE)\n"
    "- v_churn(agency_id BIGINT, churn_probability DOUBLE, risk_band VARCHAR, top_features VARCHAR)\n"
    "- v_clusters(agency_id BIGINT, cluster_id BIGINT, pca_x DOUBLE, pca_y DOUBLE, centroid_distance DOUBLE)\n"
    "- v_forecast(entity_type VARCHAR, entity_id BIGINT, forecast_date DATE, yhat DOUBLE, yhat_lower DOUBLE, yhat_upper DOUBLE)\n"
    "- v_basket(antecedent VARCHAR, consequent VARCHAR, support DOUBLE, confidence DOUBLE, lift DOUBLE)\n"
)

FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "REPLACE", "ATTACH", "DETACH", "COPY", "LOAD",
    "PRAGMA", "VACUUM", "CHECKPOINT", "EXECUTE", "CALL",
]

FORBIDDEN_FUNCTIONS = [
    "read_parquet", "read_csv", "read_csv_auto", "read_json",
    "read_json_auto", "read_xlsx", "read_sql", "read_file",
    "glob", "fsync", "mkdir", "remove", "rename", "fetch",
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"ignore (all )?previous (prompt|instruction)",
    r"system prompt",
    r"you are now",
    r"new role:",
    r"disregard (all )?above",
    r"\broot\b.*\binstructions\b",
]

MAX_SQL_LENGTH = 2000

# Catálogo cerrado de funciones (path seguro rápido)
CONTEXT_FUNCS: dict[str, Callable[..., pd.DataFrame | dict]] = {
    "kpis_globales": kpis_globales,
    "top_agencias": top_agencias,
    "ventas_por_mes": ventas_por_mes,
    "ventas_por_producto": ventas_por_producto,
    "ventas_por_agencia_y_producto": ventas_por_agencia_y_producto,
    "ventas_por_hora": ventas_por_hora,
    "ventas_por_sorteo_y_hora": ventas_por_sorteo_y_hora,
}


# ── Guardrails SQL ───────────────────────────────────────────────────────────

def validate_sql(sql: str) -> tuple[bool, str]:
    """Valida que el SQL sea seguro: solo SELECT, sin DDL/DML, sin múltiples sentencias."""
    if len(sql) > MAX_SQL_LENGTH:
        return False, f"Consulta demasiado larga (máx {MAX_SQL_LENGTH} caracteres)."

    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return False, "Solo se permiten consultas SELECT."

    if ";" in sql:
        return False, "No se permiten múltiples sentencias."

    sql_upper = sql.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", sql_upper):
            return False, f"Palabra clave prohibida detectada: {keyword}"

    for func in FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{func}\b", sql_lower := sql.lower()):
            return False, f"Función prohibida detectada: {func}"

    # No permitir string literals que parezcan rutas de archivo (evita path traversal)
    path_like = re.findall(r"'[^']*\.parquet[^']*'", sql.lower())
    if path_like:
        return False, "No se permiten referencias directas a archivos en el SQL."

    return True, ""


def _register_safe_views(conn: duckdb.DuckDBPyConnection) -> None:
    """Registra DataFrames como vistas en una conexión DuckDB limpia."""
    conn.register("v_ventas_mes", ventas_por_mes())
    conn.register("v_top_agencias", top_agencias(n=50))
    conn.register("v_ventas_producto", ventas_por_producto())
    conn.register("v_ventas_agencia_producto", ventas_por_agencia_y_producto(n=100))
    conn.register("v_ventas_hora", ventas_por_hora())
    conn.register("v_ventas_sorteo_hora", ventas_por_sorteo_y_hora(n=50))

    safe_register = [
        ("v_anomalias", prediccion_anomalias),
        ("v_churn", prediccion_churn),
        ("v_clusters", prediccion_clusters),
        ("v_forecast", prediccion_forecast),
        ("v_basket", prediccion_basket),
    ]
    for view_name, fn in safe_register:
        try:
            df = fn()
            if df.empty:
                conn.execute(f"CREATE VIEW {view_name} AS SELECT NULL WHERE 1=0")
            else:
                conn.register(view_name, df)
        except Exception:  # noqa: BLE001
            conn.execute(f"CREATE VIEW {view_name} AS SELECT NULL WHERE 1=0")


def ejecutar_sql_seguro(sql: str, max_rows: int = 5000) -> pd.DataFrame:
    """Ejecuta SQL validado en un DuckDB sandboxed con solo vistas registradas."""
    valid, msg = validate_sql(sql)
    if not valid:
        raise ValueError(msg)

    conn = duckdb.connect()
    try:
        _register_safe_views(conn)
        df = conn.execute(sql).df()
        if len(df) > max_rows:
            raise ValueError(
                f"La consulta devolvió {len(df)} filas (máx permitido: {max_rows}). "
                "Agregá LIMIT o filtrá más específicamente."
            )
        return df
    finally:
        conn.close()


# ── Memoria de conversación ──────────────────────────────────────────────────

def _enrich_with_history(question: str, history: list[dict]) -> str:
    """Si la pregunta es ambigua, enriquecerla con contexto del historial."""
    if not history:
        return question

    q_lower = question.lower().strip()

    # Detectar preguntas ambiguas (sin sujeto claro)
    ambiguous_starts = ("y ", "su ", "el ", "la ", "lo ", "los ", "las ", "cuántas ", "cuántos ", "cuánta ", "cuánto ", "cuantas ", "cuantos ", "cuanta ", "cuanto ")
    is_short = len(q_lower.split()) <= 4
    has_entity = any(w in q_lower for w in ("agencia", "producto", "mes", "año", "churn", "anomalía", "forecast", "pronóstico", "granja", "granjita", "triple", "lotto"))

    if not (is_short and not has_entity or q_lower.startswith(ambiguous_starts)):
        return question

    # Buscar contexto en últimos mensajes del asistente (de atrás hacia adelante)
    context_parts = []
    for msg in reversed(history[-6:]):
        if msg.get("role") == "assistant" and msg.get("content"):
            content = msg["content"]
            # Extraer posibles entidades mencionadas
            if "GANALOTERIAS" in content or "INT" in content or "agencia" in content.lower():
                context_parts.append(content[:200])
            elif "LA GRANJITA" in content.upper() or "producto" in content.lower():
                context_parts.append(content[:200])
            if len(context_parts) >= 2:
                break

    if not context_parts:
        return question

    # Inyectar contexto
    context_summary = " | ".join(reversed(context_parts))
    return f"{question} (contexto previo: {context_summary})"


# ── Contexto catálogo (modo offline / fallback) ──────────────────────────────

def _build_context_catalog(question: str) -> tuple[str, list[str]]:
    """Recupera contexto según palabras clave de la pregunta (modo catálogo)."""
    sources: list[str] = []
    lines: list[str] = []
    q = question.lower()

    if any(w in q for w in ("kpi", "global", "totales", "resumen")):
        data = kpis_globales()
        lines.append("KPIs globales: " + ", ".join(f"{k}={v}" for k, v in data.items()))
        sources.append("dashboard/data::kpis_globales")

    if any(w in q for w in ("agencia", "top", "mejores")):
        data = top_agencias(n=10)
        lines.append("Top agencias:\n" + data.head(5).to_string(index=False))
        sources.append("dashboard/data::top_agencias")

    if any(w in q for w in ("mes", "mensual", "evolución")):
        data = ventas_por_mes()
        lines.append("Ventas por mes:\n" + data.tail(6).to_string(index=False))
        sources.append("dashboard/data::ventas_por_mes")

    if any(w in q for w in ("producto", "juego", "jugada")):
        data = ventas_por_producto()
        lines.append("Ventas por producto:\n" + data.head(5).to_string(index=False))
        sources.append("dashboard/data::ventas_por_producto")

    if any(w in q for w in ("agencia", "vendio", "vendió", "vendedora", "vendedor", "vende")) and any(w in q for w in ("producto", "juego", "jugada", "granja", "granjita", "lotto", "triple", "triples", "animalitos")):
        data = ventas_por_agencia_y_producto(n=20)
        lines.append("Top ventas por agencia y producto:\n" + data.head(10).to_string(index=False))
        sources.append("dashboard/data::ventas_por_agencia_y_producto")

    if any(w in q for w in ("hora", "horario", "horarios", "momento", "cuando", "cuándo", "se mueven", "pico", "picos")):
        data = ventas_por_hora()
        lines.append("Ventas por hora del día:\n" + data.to_string(index=False))
        sources.append("dashboard/data::ventas_por_hora")

    if any(w in q for w in ("sorteo", "sorteos", "lotería", "loteria", "draw")) and any(w in q for w in ("hora", "horario", "horarios")):
        data = ventas_por_sorteo_y_hora(n=20)
        lines.append("Top sorteos por hora:\n" + data.head(10).to_string(index=False))
        sources.append("dashboard/data::ventas_por_sorteo_y_hora")

    # Si la pregunta menciona sorteos específicos, traer sorteos por hora también
    sorteos_populares = ("granjita", "ricachona", "guacharo", "lotto activo", "tripleta", "selva", "guacharito")
    if any(s in q for s in sorteos_populares) and any(w in q for w in ("hora", "horario", "horarios", "cuando", "cuándo")):
        data = ventas_por_sorteo_y_hora(n=30)
        lines.append("Sorteos populares por hora:\n" + data.head(15).to_string(index=False))
        sources.append("dashboard/data::ventas_por_sorteo_y_hora")

    # Fallback: si hay contexto previo con agencia+producto pero la pregunta es ambigua
    if not lines and "contexto previo:" in q:
        # Intentar extraer entidades del contexto previo
        if any(p in q for p in ("granja", "granjita", "lotto", "triple", "triples", "animalitos")):
            data = ventas_por_agencia_y_producto(n=20)
            lines.append("Top ventas por agencia y producto:\n" + data.head(10).to_string(index=False))
            sources.append("dashboard/data::ventas_por_agencia_y_producto")

    if not lines:
        lines.append("No se encontró contexto relevante en el catálogo de funciones autorizadas.")

    return "\n\n".join(lines), sources


def _detectar_prompt_injection(text: str) -> tuple[bool, str]:
    """Heurística básica contra prompt injection en preguntas de usuario."""
    lower = text.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, lower):
            return True, "Patrón de seguridad detectado en la pregunta."
    return False, ""


# ── Flujo SQL asistido ───────────────────────────────────────────────────────

def _es_consulta_sql(question: str) -> bool:
    """Heurística simple: si la pregunta parece pedir datos/tablas, usamos SQL."""
    q = question.lower()
    data_words = (
        "cuántas", "cuántos", "listado", "tabla", "sql", "query", "consulta",
        "ventas", "agencias", "productos", "top", "promedio", "total", "suma",
        "dame", "mostrá", "mostrar", "cuales", "cuáles", "qué", "que", "cuanto",
        "cuánto", "forecast", "pronóstico", "anomalía", "churn", "riesgo",
        "vendio", "vendió", "vendedora", "granja", "granjita", "lotto", "triple",
        "hora", "horario", "horarios", "momento", "cuando", "cuándo", "pico",
        "sorteo", "sorteos",
    )
    return any(w in q for w in data_words)


def _generar_sql(question: str, history: list[dict] | None = None) -> str:
    """Pide al LLM que genere SQL candidata.

    Nota: no pasamos el historial completo al prompt de SQL para evitar
    que el LLM genere múltiples sentencias o se confunda con contexto previo.
    Usamos solo la pregunta enriquecida.
    """
    messages = [
        {"role": "system", "content": SQL_SYSTEM_PROMPT},
        {"role": "user", "content": f"Pregunta: {question}\n\nGenerá UNA sola consulta SQL SELECT. Sin punto y coma."},
    ]
    resp = chat_completion(messages, temperature=0.1, max_tokens=256)
    sql = resp["choices"][0]["message"]["content"].strip()
    # Limpiar markdown ```sql ... ```
    sql = re.sub(r"^```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```$", "", sql)
    # Forzar eliminación de punto y coma para evitar múltiples sentencias
    sql = sql.replace(";", " ").strip()
    return sql.strip()


def _resumir_resultado(question: str, df: pd.DataFrame, history: list[dict] | None = None) -> str:
    """Resume un DataFrame en español usando LLM o fallback directo."""
    if df.empty:
        context = f"Pregunta: {question}\n\nLa consulta no devolvió resultados. " \
                  f"Explicá por qué podría ser (por ejemplo: la agencia no está en el top 50 de forecast, " \
                  f"o no hay datos para ese período)."
    else:
        try:
            preview = df.head(20).to_markdown(index=False)
        except Exception:  # noqa: BLE001
            preview = df.head(20).to_string(index=False)
        context = f"Pregunta: {question}\n\nResultados:\n{preview}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    # Incluir historial para contexto conversacional
    if history:
        for msg in history[-4:]:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"][:500]})
    messages.append({"role": "user", "content": (
        f"{context}\n\n"
        "Respondé la pregunta en español de forma natural y conversacional, como si hablaras con un colega de negocios. "
        "Si los resultados incluyen columnas técnicas como 'yhat', 'yhat_lower', 'yhat_upper', traducilas a: "
        "'pronóstico estimado', 'escenario conservador (mínimo esperado)', 'escenario optimista (máximo esperado)'. "
        "Presentá los montos en millones o billones de Bs., nunca en notación científica (ej: 1.2B en vez de 1.2e9)."
    )})
    try:
        resp = chat_completion(messages, temperature=0.2, max_tokens=512)
        return resp["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error resumiendo resultado con LLM: %s", exc)
        if df.empty:
            return "No encontré datos para responder esa pregunta. Es posible que la agencia o período que mencionás no esté en los registros disponibles."
        return f"Resultados de la consulta:\n\n{preview}"


# ── Motor principal ──────────────────────────────────────────────────────────

def answer(question: str, history: list[dict] | None = None) -> dict:
    """Responde una pregunta usando LLM + contexto recuperado.

    Args:
        question: Pregunta del usuario.
        history: Lista de mensajes previos [{"role": "user"/"assistant", "content": str}].

    Retorna dict con keys: answer, sources, cached, sql (opcional).
    """
    history = history or []
    cache_key = f"chat:{prompt_hash(question)}:{RUN_ID}"
    cached = cache_get(cache_key)
    if cached:
        return {"answer": cached, "sources": [], "cached": True, "sql": None}

    # Enriquecer pregunta con contexto del historial si es ambigua
    enriched_question = _enrich_with_history(question, history)

    if not is_configured():
        context, sources = _build_context_catalog(enriched_question)
        if "No se encontró" in context:
            return {
                "answer": "🔒 Modo offline: OpenRouter no está configurado y no tengo esa información en el catálogo local.",
                "sources": [],
                "cached": False,
                "sql": None,
            }
        return {
            "answer": f"🔒 Modo offline (sin LLM):\n\n{context}",
            "sources": sources,
            "cached": False,
            "sql": None,
        }

    # Decidir flujo
    if _es_consulta_sql(enriched_question):
        try:
            start = time.time()
            sql = _generar_sql(enriched_question, history)
            df = ejecutar_sql_seguro(sql)
            latency = (time.time() - start) * 1000

            if not df.empty:
                text = _resumir_resultado(enriched_question, df, history)

                log_interaction(
                    prompt=question,
                    response_text=text,
                    model="unknown",
                    input_tokens=None,
                    output_tokens=None,
                    latency_ms=latency,
                )
                cache_set(cache_key, text)
                return {
                    "answer": text,
                    "sources": ["SQL sandboxed"],
                    "cached": False,
                    "sql": sql,
                }
            else:
                logger.warning("SQL devolvió vacío, probando catálogo.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Flujo SQL falló (%s), cayendo a catálogo de funciones.", exc)

    # Modo catálogo (funciones Python seguras)
    context, sources = _build_context_catalog(enriched_question)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    # Incluir historial para contexto conversacional
    if history:
        for msg in history[-4:]:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"][:500]})
    messages.append({"role": "user", "content": f"Pregunta: {enriched_question}\n\nContexto:\n{context}\n\nRespondé de forma concisa en español."})

    try:
        start = time.time()
        resp = chat_completion(messages, temperature=0.2, max_tokens=512)
        latency = (time.time() - start) * 1000
        text = resp["choices"][0]["message"]["content"]
        model = resp.get("model", "unknown")
        usage = resp.get("usage", {})
        log_interaction(
            prompt=question,
            response_text=text,
            model=model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=latency,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat error: %s", exc)
        text = f"⚠️ No pude procesar la consulta: {exc}"

    cache_set(cache_key, text)
    return {"answer": text, "sources": sources, "cached": False, "sql": None}


# ── UI Streamlit ─────────────────────────────────────────────────────────────

def render_chat_ui() -> None:
    """Componente Streamlit conversacional."""
    st.subheader("💬 Asistente de Negocios")

    if not is_configured():
        st.info("Modo estándar: consultá sobre ventas, agencias, productos y pronósticos.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            # Mostrar timestamp si existe
            if msg.get("timestamp"):
                st.caption(msg["timestamp"])
            st.markdown(msg["content"])

    sugerencias = [
        "¿Cuáles son las ventas por mes?",
        "¿Cuántas agencias tienen riesgo de churn alto?",
        "¿Cuál es el top 5 de productos por ventas?",
        "Muestra las anomalías críticas.",
    ]
    cols = st.columns(len(sugerencias))
    for i, sug in enumerate(sugerencias):
        with cols[i]:
            if st.button(sug, key=f"sug_{i}"):
                st.session_state["_chat_input_value"] = sug
                st.rerun()

    # Procesar input pendiente de sugerencia
    pending = st.session_state.pop("_chat_input_value", None)

    prompt = st.chat_input("¿Qué querés saber?")
    if prompt:
        pending = prompt

    if pending:
        from datetime import datetime
        now = datetime.now().strftime("%H:%M")
        st.session_state.messages.append({"role": "user", "content": pending, "timestamp": now})
        with st.chat_message("user"):
            st.caption(now)
            st.markdown(pending)

        result = answer(pending, history=st.session_state.messages)
        reply = result["answer"]
        reply_time = datetime.now().strftime("%H:%M")
        with st.chat_message("assistant"):
            st.caption(reply_time)
            st.markdown(reply)
        st.session_state.messages.append({
            "role": "assistant",
            "content": reply,
            "timestamp": reply_time,
        })
