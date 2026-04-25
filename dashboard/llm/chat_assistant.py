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
    ventas_por_producto_y_mes,
    ventas_por_agencia_y_mes,
    ventas_por_agencia_y_producto,
    ventas_por_hora,
    ventas_por_sorteo_y_mes,
    ventas_por_sorteo_y_hora,
    prediccion_anomalias,
    prediccion_churn,
    prediccion_clusters,
    prediccion_forecast,
    prediccion_basket,
    pronostico_ejecutivo_mes,
    agencias_en_deterioro,
    rendimiento_grupos_centros,
    tendencia_productos,
    tendencia_sorteos,
    tickets_anulados_detalle,
)
from dashboard.db_local import (
    jerarquia_agencia,
    producto_mas_vendido,
    sorteos_por_nombre,
    numeros_mas_apostados,
    numeros_mas_salidos,
    rendimiento_grupos_centros as db_rendimiento_grupos_centros,
    tickets_anulados_recientes as db_tickets_anulados_recientes,
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
    "Vistas disponibles (catálogo curado DuckDB):\n"
    "- v_ventas_mes(mes TIMESTAMP, ventas DOUBLE, premios DOUBLE, margen_bruto DOUBLE, pct_margen DOUBLE)\n"
    "- v_top_agencias(agencia VARCHAR, ventas DOUBLE, premios DOUBLE, ganancias DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_producto(producto VARCHAR, tipo BIGINT, ventas DOUBLE, premios DOUBLE, margen_bruto DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_producto_mes(mes TIMESTAMP, producto VARCHAR, ventas DOUBLE, premios DOUBLE, margen_bruto DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_agencia_mes(mes TIMESTAMP, agencia VARCHAR, ventas DOUBLE, premios DOUBLE, margen_bruto DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_agencia_producto(agencia VARCHAR, producto VARCHAR, ventas DOUBLE, premios DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_sorteo_mes(mes TIMESTAMP, sorteo VARCHAR, hora VARCHAR, ventas DOUBLE, premios DOUBLE, margen_bruto DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_hora(hora VARCHAR, ventas DOUBLE, pct_margen DOUBLE)\n"
    "- v_ventas_sorteo_hora(sorteo VARCHAR, hora VARCHAR, ventas DOUBLE, premios DOUBLE, pct_margen DOUBLE)\n"
    "- v_anomalias(agency_id BIGINT, anomaly_score DOUBLE, severity VARCHAR, period DATE)\n"
    "- v_churn(agency_id BIGINT, churn_probability DOUBLE, risk_band VARCHAR, top_features VARCHAR)\n"
    "- v_clusters(agency_id BIGINT, cluster_id BIGINT, pca_x DOUBLE, pca_y DOUBLE, centroid_distance DOUBLE)\n"
    "- v_forecast(entity_type VARCHAR, entity_id BIGINT, forecast_date DATE, yhat DOUBLE, yhat_lower DOUBLE, yhat_upper DOUBLE)\n"
    "- v_basket(antecedent VARCHAR, consequent VARCHAR, support DOUBLE, confidence DOUBLE, lift DOUBLE)\n"
    "\n"
    "Para consultas complejas que requieren la base de datos local (PostgreSQL), "
    "el sistema usa funciones seguras predefinidas en lugar de SQL libre. "
    "No generés SQL para tablas como agencys, groups, centers, master_centers, "
    "loteries, results, new_results, bets_YYYYMMDD, sales_by_new_products_agency. "
    "Esas tablas están encapsuladas.\n"
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

MONTHS_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

VALID_LOTTERY_TOKENS = (
    "GRANJITA", "RICACHONA", "GUACHARO", "GUACHARITO", "SELVA",
    "LOTTO", "TRIPLE", "TRIPLETA", "CHANCE", "RULETA", "ACTIVO",
    "ANIMAL", "TERMINAL", "CARACAS", "TACHIRA", "ZULIA", "ZAMORANO",
)


def _month_name_es(month_num: int) -> str:
    for name, num in MONTHS_ES.items():
        if num == month_num:
            return name.title()
    return str(month_num)


def _normalize_text(text: str) -> str:
    return re.sub(r"[^A-Z0-9 ]+", " ", text.upper()).strip()


def _match_named_entity(question: str, values: list[str]) -> str | None:
    qn = _normalize_text(question)
    best: tuple[int, str] | None = None
    for value in values:
        vn = _normalize_text(value)
        if not vn:
            continue
        if vn in qn:
            score = len(vn)
        else:
            tokens = [t for t in vn.split() if len(t) >= 3]
            if not tokens:
                continue
            matched = sum(1 for t in tokens if t in qn)
            if matched == 0:
                continue
            score = matched * 10 + len(vn)
        if best is None or score > best[0]:
            best = (score, value)
    return best[1] if best else None


def _exact_match_named_entity(hint: str, values: list[str]) -> str | None:
    hn = _normalize_text(hint)
    if not hn:
        return None
    candidates = []
    for value in values:
        vn = _normalize_text(value)
        if hn == vn:
            return value
        if hn in vn or vn in hn:
            candidates.append(value)
    return max(candidates, key=len) if candidates else None


def _build_month_entity_comparison(
    df: pd.DataFrame,
    entity_col: str,
    entity_value: str,
    month_nums: list[int],
    label: str,
) -> str | None:
    sub = df[df[entity_col].str.upper() == entity_value.upper()].copy()
    if sub.empty:
        return None
    sub["mes_dt"] = pd.to_datetime(sub["mes"], errors="coerce")

    year_candidates = []
    for year, g in sub.groupby(sub["mes_dt"].dt.year):
        months_available = set(g["mes_dt"].dt.month.dropna().astype(int).tolist())
        if all(m in months_available for m in month_nums):
            year_candidates.append(int(year))
    if not year_candidates:
        return None

    target_year = max(year_candidates)
    sub = sub[(sub["mes_dt"].dt.year == target_year) & (sub["mes_dt"].dt.month.isin(month_nums))].copy()
    sub = sub.sort_values("mes_dt")

    if len(month_nums) >= 2:
        first_m, second_m = month_nums[0], month_nums[1]
        a = sub[sub["mes_dt"].dt.month == first_m]
        b = sub[sub["mes_dt"].dt.month == second_m]
        if not a.empty and not b.empty:
            ventas_a = float(a.iloc[0]["ventas"])
            ventas_b = float(b.iloc[0]["ventas"])
            diff = ventas_b - ventas_a
            pct = (diff / ventas_a * 100) if ventas_a else None
            pct_line = f"- Diferencia porcentual: {pct:.2f}%" if pct is not None else "- Diferencia porcentual: n/d"
            return (
                f"Comparación mensual por {label}:\n"
                f"- {label.title()}: {entity_value}\n"
                f"- {_month_name_es(first_m)} {target_year}: {ventas_a:,.0f} Bs.\n"
                f"- {_month_name_es(second_m)} {target_year}: {ventas_b:,.0f} Bs.\n"
                f"- Diferencia absoluta: {diff:,.0f} Bs.\n"
                f"{pct_line}"
            )

    return f"Ventas por {label} y mes:\n" + sub[["mes", entity_col, "ventas", "premios", "pct_margen"]].to_string(index=False)

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
    conn.register("v_ventas_producto_mes", ventas_por_producto_y_mes())
    conn.register("v_ventas_agencia_mes", ventas_por_agencia_y_mes())
    conn.register("v_ventas_agencia_producto", ventas_por_agencia_y_producto(n=100))
    conn.register("v_ventas_hora", ventas_por_hora())
    conn.register("v_ventas_sorteo_mes", ventas_por_sorteo_y_mes())
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


# ── Memoria conversacional estructurada ──────────────────────────────────────

def _extract_entities(question: str) -> dict:
    """Extrae entidades estructuradas de una pregunta."""
    q = question.lower()
    entities: dict = {}

    # Agencia
    agencia = _extraer_nombre_agencia(question)
    if agencia:
        primera = agencia.split()[0].lower() if agencia else ""
        if primera not in ("que", "de", "en", "por", "para", "con", "del", "al", "y", "o", "a"):
            entities["entity_type"] = "agency"
            entities["entity_name"] = agencia

    # Producto
    productos = ("granjita", "ricachona", "guacharo", "guacharito", "lotto activo", "selva", "tripleta", "animalitos")
    for p in productos:
        if p in q:
            entities["entity_type"] = "product"
            entities["entity_name"] = p.title()
            break

    # Sorteo (solo si no ya detectamos una agencia con nombre válido)
    sorteo, hora = _extraer_sorteo(question)
    sorteo_upper = sorteo.upper() if sorteo else ""
    sorteo_es_valido = any(tok in sorteo_upper for tok in VALID_LOTTERY_TOKENS)
    if sorteo and sorteo_es_valido and entities.get("entity_type") != "agency" and "AGENCIA" not in sorteo_upper:
        entities["entity_type"] = "lottery"
        entities["entity_name"] = sorteo
        if hora:
            entities["lottery_hour"] = hora

    # Meses
    month_hits = [(name, num) for name, num in MONTHS_ES.items() if name in q]
    if month_hits:
        entities["months"] = sorted({num for _, num in month_hits})

    # Métrica
    if any(w in q for w in ("diferencia", "compar", "vs", "versus", "contra")):
        entities["metric"] = "comparación"
    elif any(w in q for w in ("pronóstico", "forecast", "proximo mes", "próximo mes", "mes que viene")):
        entities["metric"] = "pronóstico"
    elif any(w in q for w in ("número más apostado", "numero mas apostado", "apuestan más", "apuestan mas", "números apostados", "numeros apostados")):
        entities["metric"] = "números_apostados"
    elif any(w in q for w in ("número que más salió", "numero que mas salio", "han salido", "números salidos", "numeros salidos")):
        entities["metric"] = "números_salidos"
    elif any(w in q for w in ("ventas", "vendio", "vendió", "vende", "mueve")):
        entities["metric"] = "ventas"
    elif any(w in q for w in ("margen", "rentabilidad", "pct_margen")):
        entities["metric"] = "margen"

    # Filtros adicionales
    dias = _extraer_rango_dias(question)
    if dias:
        entities["rango_dias"] = dias

    return entities


def _is_follow_up_question(question: str) -> bool:
    """Heurística para detectar si una pregunta es seguimiento de la anterior."""
    q_lower = question.lower().strip()
    words = q_lower.split()

    if len(words) <= 4:
        return True

    follow_starts = ("y ", "de ", "a ", "en ", "su ", "el ", "la ", "lo ", "los ", "las ")
    if any(q_lower.startswith(p) for p in follow_starts):
        return True

    pronouns = ("esa", "ese", "esos", "esas", "aquel", "aquella", "aquellos", "aquellas")
    if any(f" {p} " in q_lower or q_lower.startswith(f"{p} ") for p in pronouns):
        return True

    return False


def _is_ambiguous(question: str, memory: dict | None = None) -> bool:
    """Heurística mejorada para detectar preguntas ambiguas."""
    q_lower = question.lower().strip()
    words = q_lower.split()

    if len(words) <= 4:
        has_entity = any(w in q_lower for w in (
            "agencia", "producto", "mes", "año", "churn", "anomalía",
            "forecast", "pronóstico", "granja", "granjita", "triple",
            "lotto", "sorteo", "lotería", "grupo", "centro", "banca",
        ))
        if not has_entity:
            return True

    pronouns = ("esa ", "ese ", "aquel ", "aquella ", "esos ", "esas ", "de esa ", "de ese ", "a esa ", "a ese ")
    if any(q_lower.startswith(p) or f" {p}" in q_lower for p in pronouns):
        return True

    if memory:
        has_metric = any(w in q_lower for w in (
            "ventas", "vendio", "vendió", "vende", "diferencia",
            "compar", "pronóstico", "forecast", "mueve", "cuanto", "cuánto", "vs", "versus",
        ))
        has_entity = any(w in q_lower for w in (
            "agencia", "producto", "sorteo", "lotería", "grupo", "centro", "banca",
        ))
        has_months = any(m in q_lower for m in MONTHS_ES)
        if (has_metric or has_months) and not has_entity and memory.get("entity_type"):
            return True

    return False


def _resolve_question(question: str, memory: dict) -> str:
    """Resuelve referencias ambiguas usando memoria estructurada."""
    if not memory or not _is_ambiguous(question, memory):
        return question

    q_lower = question.lower()
    et = memory.get("entity_type")
    en = memory.get("entity_name")
    lh = memory.get("lottery_hour")
    months = memory.get("months")

    if en and en.lower() in q_lower:
        return question

    additions: list[str] = []

    if et == "agency" and en and "agencia" not in q_lower:
        additions.append(f"agencia {en}")
    elif et == "product" and en and "producto" not in q_lower:
        additions.append(f"producto {en}")
    elif et == "lottery" and en and "sorteo" not in q_lower and "lotería" not in q_lower:
        additions.append(f"sorteo {en}")
        if lh and lh.lower() not in q_lower:
            additions.append(f"horario {lh}")
    elif et == "group" and en and "grupo" not in q_lower:
        additions.append(f"grupo {en}")
    elif et == "center" and en and "centro" not in q_lower:
        additions.append(f"centro {en}")

    if months and not any(m in q_lower for m in MONTHS_ES):
        month_names = [_month_name_es(m) for m in months]
        additions.append(f"meses {', '.join(month_names)}")

    if additions:
        context_str = ", ".join(additions)
        return f"{question} (refiriéndose a: {context_str})"

    return question


def _merge_memory(
    old_memory: dict,
    current_explicit: dict,
    resolved_entities: dict,
    context_entities: dict,
    question: str,
) -> dict:
    """Fusiona entidades nuevas con memoria previa."""
    new_memory: dict = {}
    is_follow_up = _is_follow_up_question(question)

    for key in ("entity_type", "entity_name", "lottery_hour"):
        if key in current_explicit:
            new_memory[key] = current_explicit[key]
        elif key in resolved_entities:
            new_memory[key] = resolved_entities[key]
        elif key in context_entities:
            new_memory[key] = context_entities[key]
        elif key in old_memory:
            new_memory[key] = old_memory[key]

    for key in ("months", "metric", "rango_dias"):
        if key in current_explicit:
            new_memory[key] = current_explicit[key]
        elif key in resolved_entities:
            new_memory[key] = resolved_entities[key]
        elif is_follow_up and key in old_memory:
            new_memory[key] = old_memory[key]

    return new_memory


def _enrich_with_history(question: str, history: list[dict], memory: dict | None = None) -> str:
    """Si la pregunta es ambigua, enriquecerla con contexto del historial.

    Prioriza memoria estructurada; fallback conservador a texto libre solo
    cuando no hay memoria disponible.
    """
    if not history:
        return question

    if memory and memory.get("entity_type") and _is_ambiguous(question, memory):
        return question

    q_lower = question.lower().strip()

    ambiguous_starts = ("y ", "su ", "el ", "la ", "lo ", "los ", "las ", "cuántas ", "cuántos ", "cuánta ", "cuánto ", "cuantas ", "cuantos ", "cuanta ", "cuanto ")
    is_short = len(q_lower.split()) <= 4
    has_entity = any(w in q_lower for w in ("agencia", "producto", "mes", "año", "churn", "anomalía", "forecast", "pronóstico", "granja", "granjita", "triple", "lotto", "sorteo", "lotería", "grupo", "centro", "banca"))

    if not (is_short and not has_entity or q_lower.startswith(ambiguous_starts)):
        return question

    context_parts = []
    for msg in reversed(history[-6:]):
        if msg.get("role") == "assistant" and msg.get("content"):
            content = msg["content"]
            if "GANALOTERIAS" in content or "INT" in content or "agencia" in content.lower():
                context_parts.append(content[:200])
            elif "LA GRANJITA" in content.upper() or "producto" in content.lower():
                context_parts.append(content[:200])
            if len(context_parts) >= 2:
                break

    if not context_parts:
        return question

    context_summary = " | ".join(reversed(context_parts))
    return f"{question} (contexto previo: {context_summary})"


# ── Contexto catálogo (modo offline / fallback) ──────────────────────────────

def _extraer_nombre_agencia(question: str) -> str | None:
    """Extrae un nombre de agencia de la pregunta usando heurísticas simples."""
    q = question
    # Patrón 1: AG. NOMBRE o AG NOMBRE (nombre en mayúsculas/números, 1-4 palabras)
    # Usamos (?-i:...) para forzar case-sensitive dentro del grupo
    m = re.search(
        r'\b(?:ag\.?|agencia)\s+((?-i:[A-Z])[A-Z0-9\.\-]*(?:\s+(?-i:[A-Z0-9\.\-]+)){0,3})\b',
        q, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    # Patrón 2: "agencia X" donde X es cualquier cosa hasta preposición común o puntuación
    m = re.search(
        r'\bagencia\s+([^\?\.,;!\n]{2,30}?)\s+(?:a|de|en|por|para|con|que|del|al|y|o)\b',
        q, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    # Patrón 3: fallback simple
    m = re.search(r'\bagencia\s+([A-Z][^\?\.,;!]{2,25})', q, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _extraer_sorteo(question: str) -> tuple[str | None, str | None]:
    """Extrae nombre de sorteo y hora opcional de la pregunta.

    Devuelve (nombre_sorteo, hora_opcional).
    Maneja variantes como 'La Granjita', 'Tripleta La Granjita', 'Granjita 07:00 PM'.
    """
    q = question
    # 1. Buscar hora primero
    m_hora = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM))', q, re.IGNORECASE)
    hora = m_hora.group(1).strip().upper() if m_hora else None

    # 2. Si hay hora, tomar el nombre justo antes
    if m_hora:
        before = q[:m_hora.start()].strip()
        matches = re.findall(
            r'\b((?:LA|EL|TRIPLE|TRIPLETA|LOTTO)\s+(?:\w+\s+){0,2}\w+)', before, re.IGNORECASE
        )
        if matches:
            return matches[-1].strip().upper(), hora

    # 3. Buscar el match más largo entre patrones conocidos (conservar hora si existe)
    pattern = (
        r'\b((?:LA|EL|TRIPLE|TRIPLETA|LOTTO)\s+(?:\w+\s+){0,2}\w+'
        r'|GRANJITA|RICACHONA|GUACHARO|GUACHARITO|SELVA)\b'
    )
    matches = re.findall(pattern, q, re.IGNORECASE)
    if matches:
        return max(matches, key=len).strip().upper(), hora
    return None, None


def _resolver_ambiguo(
    df: pd.DataFrame,
    nombre_col: str,
    history: list[dict],
    tipo_entidad: str,
    extra_cols: list[str] | None = None,
) -> tuple[int | None, str | None]:
    """Resuelve ambigüedad usando historial. Devuelve (id, None) o (None, mensaje)."""
    if df.empty:
        return None, f"No encontré {tipo_entidad} con ese nombre."

    if len(df) == 1:
        return int(df.iloc[0]["id"]), None

    # Buscar en historial menciones de los candidatos
    history_text = " ".join(
        msg.get("content", "") for msg in history[-6:]
    ).lower()

    matches = []
    for _, row in df.iterrows():
        nombre = str(row[nombre_col]).lower()
        if nombre in history_text:
            matches.append(row)

    if len(matches) == 1:
        return int(matches[0]["id"]), None

    # Construir mensaje de clarificación
    lines = [f"Encontré {len(df)} coincidencias para '{tipo_entidad}'. ¿A cuál te referís?"]
    for _, row in df.head(5).iterrows():
        extras = []
        if extra_cols:
            for col in extra_cols:
                if col in row and pd.notna(row[col]):
                    extras.append(str(row[col]))
        extra_txt = f" ({', '.join(extras)})" if extras else ""
        lines.append(f"- {row[nombre_col]}{extra_txt}")

    return None, "\n".join(lines)


def _extraer_rango_dias(question: str) -> int | None:
    """Extrae rango de días de la pregunta si lo hay."""
    q = question.lower()
    # "últimos 30 días", "últimos 7 días", "últimos 3 meses"
    m = re.search(r'(?:últimos?|ultimos?)\s+(\d+)\s+d[ií]as?', q)
    if m:
        return int(m.group(1))
    m = re.search(r'(?:últimos?|ultimos?)\s+(\d+)\s+mes(?:es)?', q)
    if m:
        return int(m.group(1)) * 30
    if any(w in q for w in ("este mes", "mes actual", "mes corriente")):
        return 30
    if any(w in q for w in ("esta semana", "semana actual")):
        return 7
    if any(w in q for w in ("hoy", "el día de hoy")):
        return 1
    return None


def _build_context_db_local(question: str, history: list[dict]) -> tuple[str, list[str], str | None, dict]:
    """Recupera contexto desde PostgreSQL local para preguntas complejas.

    Devuelve (contexto_texto, sources, clarificación, entities). Si no aplica, devuelve ("", [], None, {})."""
    sources: list[str] = []
    lines: list[str] = []
    entities: dict = {}
    q = question.lower()
    clarification: str | None = None

    # ── Jerarquía de agencia ────────────────────────────────────────────────
    if any(w in q for w in ("grupo", "pertenece", "centro", "master", "jerarquía", "banca", "a qué")) and any(w in q for w in ("agencia", "ag.", "ag ")):
        nombre = _extraer_nombre_agencia(question)
        if nombre:
            nombre_limpio = re.sub(r'^(?:ag\.?|agencia)\s+', '', nombre, flags=re.IGNORECASE).strip()
            if not nombre_limpio:
                nombre_limpio = nombre
            try:
                df = jerarquia_agencia(nombre_limpio)
                if not df.empty:
                    lines.append(f"Agencias que coinciden con '{nombre_limpio}':\n" + df.head(5).to_string(index=False))
                    sources.append("dashboard/db_local::jerarquia_agencia")
                    entities = {"entity_type": "agency", "entity_name": str(df.iloc[0]["agencia"])}
                else:
                    lines.append(f"No encontré agencias que coincidan con '{nombre_limpio}'.")
                    sources.append("dashboard/db_local::jerarquia_agencia")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error consultando jerarquía de agencia: %s", exc)

    # ── Producto más vendido ────────────────────────────────────────────────
    if any(w in q for w in ("producto vendió más", "producto mas vendido", "producto mas vendio", "producto vendio mas", "qué producto vende más", "que producto vende mas")):
        dias = _extraer_rango_dias(question)
        try:
            df = producto_mas_vendido(rango_dias=dias, n=5)
            if not df.empty:
                rango_txt = f" (últimos {dias} días)" if dias else " (histórico completo)"
                lines.append(f"Top productos por ventas{rango_txt}:\n" + df.to_string(index=False))
                sources.append("dashboard/db_local::producto_mas_vendido")
                entities = {"entity_type": "product", "entity_name": str(df.iloc[0]["producto"])}
            else:
                lines.append("No encontré datos de ventas por producto para el rango solicitado.")
                sources.append("dashboard/db_local::producto_mas_vendido")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando producto más vendido: %s", exc)

    # ── Números más apostados ───────────────────────────────────────────────
    if any(w in q for w in (
        "número más apostado", "numero mas apostado",
        "apuestan más", "apuestan mas", "apuestan mucho",
        "números apuestan", "numeros apuestan",
        "mas apostado", "más apostado",
    )):
        sorteo_raw, hora = _extraer_sorteo(question)
        dias = _extraer_rango_dias(question) or 30
        lotery_id: int | None = None
        if sorteo_raw:
            from dashboard.db_local import _resolve_lottery
            df_lot = _resolve_lottery(sorteo_raw, hour=hora)
            lotery_id, clarification = _resolver_ambiguo(
                df_lot, "sorteo", history, "sorteo", extra_cols=["hora"]
            )
            if clarification:
                return "", [], clarification, entities
        if sorteo_raw:
            entities = {"entity_type": "lottery", "entity_name": sorteo_raw}
            if hora:
                entities["lottery_hour"] = hora
        try:
            df = numeros_mas_apostados(lotery_id=lotery_id, rango_dias=dias, n=10)
            if not df.empty:
                sorteo_txt = f" en {sorteo_raw}" if sorteo_raw else ""
                lines.append(f"Números más apostados{sorteo_txt} (últimos {dias} días):\n" + df.to_string(index=False))
                sources.append("dashboard/db_local::numeros_mas_apostados")
            else:
                lines.append("No encontré datos de apuestas para el rango/sorteo solicitado.")
                sources.append("dashboard/db_local::numeros_mas_apostados")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando números más apostados: %s", exc)

    # ── Números que más han salido ──────────────────────────────────────────
    if any(w in q for w in (
        "número que más salió", "numero que mas salio",
        "más han salido", "mas han salido",
        "han salido más", "han salido mas",
        "salen más", "salen mas",
        "ha salido más", "ha salido mas",
        "mas salido", "más salido",
    )):
        sorteo_raw, hora = _extraer_sorteo(question)
        dias = _extraer_rango_dias(question)
        lotery_id = None
        if sorteo_raw:
            from dashboard.db_local import _resolve_lottery
            df_lot = _resolve_lottery(sorteo_raw, hour=hora)
            lotery_id, clarification = _resolver_ambiguo(
                df_lot, "sorteo", history, "sorteo", extra_cols=["hora"]
            )
            if clarification:
                return "", [], clarification, entities
        if sorteo_raw:
            entities = {"entity_type": "lottery", "entity_name": sorteo_raw}
            if hora:
                entities["lottery_hour"] = hora
        try:
            df = numeros_mas_salidos(lotery_id=lotery_id, rango_dias=dias, n=10)
            if not df.empty:
                sorteo_txt = f" en {sorteo_raw}" if sorteo_raw else ""
                rango_txt = f" (últimos {dias} días)" if dias else " (histórico completo)"
                lines.append(f"Números que más han salido{sorteo_txt}{rango_txt}:\n" + df.to_string(index=False))
                sources.append("dashboard/db_local::numeros_mas_salidos")
            else:
                lines.append("No encontré resultados históricos para el sorteo/rango solicitado.")
                sources.append("dashboard/db_local::numeros_mas_salidos")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando números más salidos: %s", exc)

    # ── Rendimiento grupos / centros / bancas ───────────────────────────────
    if any(w in q for w in ("grupo", "grupos", "banca", "bancas", "centro", "centros", "master")) and any(w in q for w in ("rendimiento", "rinde", "mejor", "peor", "cayendo", "desempeño")):
        nivel = "group"
        if any(w in q for w in ("centro", "centros", "banca", "bancas")):
            nivel = "center"
        if any(w in q for w in ("master", "master center")):
            nivel = "master_center"
        try:
            df = db_rendimiento_grupos_centros(nivel=nivel, n=10)
            if not df.empty:
                lines.append(f"Rendimiento por {nivel}:\n" + df.to_string(index=False))
                sources.append("dashboard/db_local::rendimiento_grupos_centros")
            # Si está vacío, dejamos que el catálogo DuckDB intente responder
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando rendimiento grupos/centros: %s", exc)

    # ── Tickets anulados recientes (PostgreSQL) ─────────────────────────────
    if any(w in q for w in ("anulado", "anulados", "anulación", "anulacion", "cancelado", "cancelados")):
        dias = _extraer_rango_dias(question) or 7
        try:
            df = db_tickets_anulados_recientes(rango_dias=dias)
            if not df.empty:
                lines.append(f"Tickets anulados recientes (últimos {dias} días):\n" + df.head(20).to_string(index=False))
                sources.append("dashboard/db_local::tickets_anulados_recientes")
            # Si está vacío, dejamos que el catálogo DuckDB intente responder
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando tickets anulados: %s", exc)

    return "\n\n".join(lines), sources, clarification, entities


def _build_context_catalog(question: str, memory: dict | None = None) -> tuple[str, list[str], dict]:
    """Recupera contexto según palabras clave de la pregunta (modo catálogo)."""
    sources: list[str] = []
    lines: list[str] = []
    entities: dict = {}
    q = question.lower()
    memory = memory or {}

    # ── Comparaciones directas producto vs meses ────────────────────────────
    month_hits = [(name, num) for name, num in MONTHS_ES.items() if name in q]
    if not month_hits and memory.get("months"):
        month_hits = [(_month_name_es(num).lower(), num) for num in memory["months"]]
    producto_hits = []
    for producto in ("granjita", "ricachona", "guacharo", "guacharito", "lotto activo", "selva"):
        if producto in q:
            producto_hits.append(producto)

    if producto_hits and month_hits:
        try:
            df = ventas_por_producto_y_mes()
            producto_token = producto_hits[0].upper()
            df = df[df["producto"].str.upper().str.contains(producto_token, na=False)].copy()
            if not df.empty:
                df["mes_dt"] = pd.to_datetime(df["mes"], errors="coerce")
                month_nums = sorted({num for _, num in month_hits})

                # Tomar el año más reciente que tenga datos para todos los meses pedidos
                year_candidates = []
                for year, g in df.groupby(df["mes_dt"].dt.year):
                    months_available = set(g["mes_dt"].dt.month.dropna().astype(int).tolist())
                    if all(m in months_available for m in month_nums):
                        year_candidates.append(int(year))

                if year_candidates:
                    target_year = max(year_candidates)
                    sub = df[(df["mes_dt"].dt.year == target_year) & (df["mes_dt"].dt.month.isin(month_nums))].copy()
                    sub = sub.sort_values("mes_dt")

                    if len(month_nums) >= 2 and any(w in q for w in ("diferencia", "compar", "vs", "versus")):
                        first_m, second_m = month_nums[0], month_nums[1]
                        a = sub[sub["mes_dt"].dt.month == first_m]
                        b = sub[sub["mes_dt"].dt.month == second_m]
                        if not a.empty and not b.empty:
                            ventas_a = float(a.iloc[0]["ventas"])
                            ventas_b = float(b.iloc[0]["ventas"])
                            diff = ventas_b - ventas_a
                            pct = (diff / ventas_a * 100) if ventas_a else None
                            lines.append(
                                "Comparación mensual por producto:\n"
                                f"- Producto: {a.iloc[0]['producto']}\n"
                                f"- {list(MONTHS_ES.keys())[list(MONTHS_ES.values()).index(first_m)].title()} {target_year}: {ventas_a:,.0f} Bs.\n"
                                f"- {list(MONTHS_ES.keys())[list(MONTHS_ES.values()).index(second_m)].title()} {target_year}: {ventas_b:,.0f} Bs.\n"
                                f"- Diferencia absoluta: {diff:,.0f} Bs.\n"
                                f"- Diferencia porcentual: {pct:.2f}%" if pct is not None else "- Diferencia porcentual: n/d"
                            )
                            sources.append("dashboard/data::ventas_por_producto_y_mes")
                            entities = {"entity_type": "product", "entity_name": str(a.iloc[0]["producto"])}
                    else:
                        lines.append("Ventas por producto y mes:\n" + sub[["mes", "producto", "ventas", "premios", "pct_margen"]].to_string(index=False))
                        sources.append("dashboard/data::ventas_por_producto_y_mes")
                        entities = {"entity_type": "product", "entity_name": str(sub.iloc[0]["producto"])}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando ventas por producto y mes: %s", exc)

    if month_hits and any(w in q for w in ("agencia", "ag.", "ag ")):
        try:
            df = ventas_por_agencia_y_mes()
            agencia_hint = _extraer_nombre_agencia(question)
            if memory.get("entity_type") == "agency" and memory.get("entity_name"):
                agencia_match = memory["entity_name"]
            elif agencia_hint:
                agencia_match = _exact_match_named_entity(agencia_hint, df["agencia"].dropna().unique().tolist()) or _match_named_entity(agencia_hint, df["agencia"].dropna().unique().tolist())
            else:
                agencia_match = _match_named_entity(question, df["agencia"].dropna().unique().tolist())
            if agencia_match:
                month_nums = sorted({num for _, num in month_hits})
                text = _build_month_entity_comparison(df, "agencia", agencia_match, month_nums, "agencia")
                if text:
                    lines.append(text)
                    sources.append("dashboard/data::ventas_por_agencia_y_mes")
                    entities = {"entity_type": "agency", "entity_name": agencia_match}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando ventas por agencia y mes: %s", exc)

    if month_hits and any(w in q for w in ("sorteo", "lotería", "loteria", "granjita", "ricachona", "guacharo", "tripleta", "lotto")):
        try:
            df = ventas_por_sorteo_y_mes()
            sorteo_nombre, sorteo_hora = _extraer_sorteo(question)
            if memory.get("entity_type") == "lottery" and memory.get("entity_name"):
                sorteo_match = memory["entity_name"]
            elif sorteo_nombre and sorteo_hora:
                target = f"{sorteo_nombre} {sorteo_hora}"
                sorteo_match = _exact_match_named_entity(target, df["sorteo"].dropna().unique().tolist()) or _match_named_entity(target, df["sorteo"].dropna().unique().tolist())
            elif sorteo_nombre:
                sorteo_match = _exact_match_named_entity(sorteo_nombre, df["sorteo"].dropna().unique().tolist()) or _match_named_entity(sorteo_nombre, df["sorteo"].dropna().unique().tolist())
            else:
                sorteo_match = _match_named_entity(question, df["sorteo"].dropna().unique().tolist())
            if sorteo_match:
                month_nums = sorted({num for _, num in month_hits})
                text = _build_month_entity_comparison(df, "sorteo", sorteo_match, month_nums, "sorteo")
                if text:
                    lines.append(text)
                    sources.append("dashboard/data::ventas_por_sorteo_y_mes")
                    entities = {"entity_type": "lottery", "entity_name": sorteo_match}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando ventas por sorteo y mes: %s", exc)

    if any(w in q for w in ("kpi", "global", "totales", "resumen")):
        data = kpis_globales()
        lines.append("KPIs globales: " + ", ".join(f"{k}={v}" for k, v in data.items()))
        sources.append("dashboard/data::kpis_globales")

    if any(w in q for w in ("agencia", "top", "mejores")):
        data = top_agencias(n=10)
        lines.append("Top agencias:\n" + data.head(5).to_string(index=False))
        sources.append("dashboard/data::top_agencias")
        if any(w in q for w in ("lider", "líder", "mejor", "primera", "primero")) and not data.empty:
            entities = {"entity_type": "agency", "entity_name": str(data.iloc[0]["agencia"])}

    if any(w in q for w in ("mes", "mensual", "evolución")):
        data = ventas_por_mes()
        lines.append("Ventas por mes:\n" + data.tail(6).to_string(index=False))
        sources.append("dashboard/data::ventas_por_mes")

    if any(w in q for w in ("producto", "juego", "jugada")):
        data = ventas_por_producto()
        lines.append("Ventas por producto:\n" + data.head(5).to_string(index=False))
        sources.append("dashboard/data::ventas_por_producto")
        if any(w in q for w in ("lider", "líder", "mejor", "primero")) and not data.empty:
            entities = {"entity_type": "product", "entity_name": str(data.iloc[0]["producto"])}

    # ── Producto + Mes (comparaciones mensuales por producto) ───────────────
    if any(w in q for w in ("producto", "juego", "jugada", "granja", "granjita", "lotto", "triple", "triples", "animalitos", "ricachona")) and any(w in q for w in ("mes", "mensual", "febrero", "marzo", "enero", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")):
        try:
            data = ventas_por_producto_y_mes()
            if not data.empty:
                lines.append("Ventas por producto y mes:\n" + data.head(10).to_string(index=False))
                sources.append("dashboard/data::ventas_por_producto_y_mes")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando ventas por producto y mes: %s", exc)

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
        if any(w in q for w in ("lider", "líder", "mejor", "primero")) and not data.empty:
            entities = {"entity_type": "lottery", "entity_name": str(data.iloc[0]["sorteo"])}
            if "hora" in data.columns:
                entities["lottery_hour"] = str(data.iloc[0]["hora"])

    # Si la pregunta menciona sorteos específicos, traer sorteos por hora también
    sorteos_populares = ("granjita", "ricachona", "guacharo", "lotto activo", "tripleta", "selva", "guacharito")
    if any(s in q for s in sorteos_populares) and any(w in q for w in ("hora", "horario", "horarios", "cuando", "cuándo")):
        data = ventas_por_sorteo_y_hora(n=30)
        lines.append("Sorteos populares por hora:\n" + data.head(15).to_string(index=False))
        sources.append("dashboard/data::ventas_por_sorteo_y_hora")

    # ── Premium: pronóstico ejecutivo próximo mes ───────────────────────────
    if any(w in q for w in ("pronóstico", "pronostico", "forecast", "próximo mes", "proximo mes", "mes que viene", "próximo periodo")):
        try:
            data = pronostico_ejecutivo_mes()
            parts = ["Pronóstico ejecutivo:"]
            parts.append(f"- Próximo mes: {data.get('proximo_mes')}")

            if data.get("forecast_confiable"):
                parts.append(
                    f"- Pronóstico de ventas estimado: {data.get('pronostico'):,.0f} Bs. "
                    f"(rango probable: {data.get('pronostico_min'):,.0f} - {data.get('pronostico_max'):,.0f} Bs.)"
                )
            else:
                parts.append(
                    f"- Estimación referencial de ventas (sin modelo confiable): {data.get('pronostico'):,.0f} Bs. "
                    f"(rango aproximado: {data.get('pronostico_min'):,.0f} - {data.get('pronostico_max'):,.0f} Bs.)"
                )
                if data.get("warning"):
                    parts.append(f"- Nota: {data['warning']}")

            base_mes = data.get("base_historica_mes")
            if base_mes:
                parts.append(f"- Ventas del último mes completo ({base_mes}): {data.get('ventas_ultimo_mes'):,.0f} Bs.")
            else:
                parts.append(f"- Ventas del último mes: {data.get('ventas_ultimo_mes'):,.0f} Bs.")

            parts.append(f"- Variación mes a mes: {data.get('variacion_mom_pct')}%")
            parts.append(f"- Tendencia últimos 3 meses: {data.get('tendencia_3m_pct')}%")
            parts.append(f"- Meses históricamente más fuertes: {data.get('mejores_meses')}")
            parts.append(f"- Meses históricamente más débiles: {data.get('peores_meses')}")

            lines.append("\n".join(parts))
            sources.append("dashboard/data::pronostico_ejecutivo_mes")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error generando pronóstico ejecutivo: %s", exc)

    # ── Premium: agencias en deterioro ──────────────────────────────────────
    if any(w in q for w in ("empeoran", "deterioro", "degradan", "bajando", "caída", "peor", "decaen", "deterioran")):
        try:
            df = agencias_en_deterioro(n=10)
            if not df.empty:
                lines.append("Agencias en deterioro (ventas recientes vs previo):\n" + df.to_string(index=False))
                sources.append("dashboard/data::agencias_en_deterioro")
            else:
                lines.append("No encontré agencias en deterioro significativo.")
                sources.append("dashboard/data::agencias_en_deterioro")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando agencias en deterioro: %s", exc)

    # ── Premium: grupos/centros rendimiento (DuckDB fallback) ───────────────
    if any(w in q for w in ("grupo", "grupos", "banca", "bancas", "centro", "centros", "master")) and any(w in q for w in ("rendimiento", "rinde", "mejor", "peor", "cayendo", "desempeño")):
        nivel = "group"
        if any(w in q for w in ("centro", "centros", "banca", "bancas")):
            nivel = "center"
        if any(w in q for w in ("master", "master center")):
            nivel = "master_center"
        try:
            df = rendimiento_grupos_centros(nivel=nivel, n=10)
            if not df.empty:
                lines.append(f"Rendimiento por {nivel} (DuckDB):\n" + df.to_string(index=False))
                sources.append("dashboard/data::rendimiento_grupos_centros")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando rendimiento grupos/centros DuckDB: %s", exc)

    # ── Premium: tendencia productos / sorteos ──────────────────────────────
    if any(w in q for w in ("creciendo", "enfriando", "crecen", "caen", "tendencia", "crecimiento", "enfriándose")):
        try:
            if any(w in q for w in ("producto", "productos", "juego", "juegos")):
                df = tendencia_productos(reciente_dias=30, previo_dias=30, n=10)
                if not df.empty:
                    lines.append("Tendencia de productos (reciente vs previo):\n" + df.to_string(index=False))
                    sources.append("dashboard/data::tendencia_productos")
            if any(w in q for w in ("sorteo", "sorteos", "lotería", "loteria")):
                df = tendencia_sorteos(reciente_dias=30, previo_dias=30, n=10)
                if not df.empty:
                    lines.append("Tendencia de sorteos (reciente vs previo):\n" + df.to_string(index=False))
                    sources.append("dashboard/data::tendencia_sorteos")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando tendencias: %s", exc)

    # ── Premium: tickets anulados detalle ───────────────────────────────────
    if any(w in q for w in ("anulado", "anulados", "anulación", "anulacion", "cancelado", "cancelados")):
        dias = _extraer_rango_dias(question) or 7
        try:
            df = tickets_anulados_detalle(rango_dias=dias)
            if not df.empty:
                lines.append(f"Detalle tickets anulados (últimos {dias} días):\n" + df.head(20).to_string(index=False))
                sources.append("dashboard/data::tickets_anulados_detalle")
            else:
                lines.append("No encontré detalle de tickets anulados.")
                sources.append("dashboard/data::tickets_anulados_detalle")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error consultando tickets anulados detalle: %s", exc)

    # Fallback: si hay contexto previo con agencia+producto pero la pregunta es ambigua
    if not lines and "contexto previo:" in q:
        if any(p in q for p in ("granja", "granjita", "lotto", "triple", "triples", "animalitos")):
            data = ventas_por_agencia_y_producto(n=20)
            lines.append("Top ventas por agencia y producto:\n" + data.head(10).to_string(index=False))
            sources.append("dashboard/data::ventas_por_agencia_y_producto")

    if not lines:
        lines.append("No se encontró contexto relevante en el catálogo de funciones autorizadas.")

    return "\n\n".join(lines), sources, entities


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
        "diferencia", "compará", "compara", "versus", "vs",
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

def answer(question: str, history: list[dict] | None = None, memory: dict | None = None) -> dict:
    """Responde una pregunta usando LLM + contexto recuperado.

    Args:
        question: Pregunta del usuario.
        history: Lista de mensajes previos [{"role": "user"/"assistant", "content": str}].
        memory: Memoria conversacional estructurada acumulada.

    Retorna dict con keys: answer, sources, cached, sql (opcional), memory.
    """
    history = history or []
    memory = memory or {}

    def _update_memory(catalog_entities: dict | None = None, db_entities: dict | None = None) -> dict:
        current_explicit = _extract_entities(question)
        resolved_entities = _extract_entities(resolved_question)
        context_entities = db_entities or catalog_entities or {}
        return _merge_memory(memory, current_explicit, resolved_entities, context_entities, question)

    cache_key = f"chat:{prompt_hash(question)}:{RUN_ID}"
    cached = cache_get(cache_key)
    if cached:
        return {"answer": cached, "sources": [], "cached": True, "sql": None, "memory": memory}

    # Resolver ambigüedades con memoria estructurada
    resolved_question = _resolve_question(question, memory)

    # Enriquecer pregunta con contexto del historial si es ambigua
    enriched_question = _enrich_with_history(resolved_question, history, memory)

    if not is_configured():
        context, sources, catalog_entities = _build_context_catalog(enriched_question, memory=memory)
        if "No se encontró" in context:
            return {
                "answer": "🔒 Modo offline: OpenRouter no está configurado y no tengo esa información en el catálogo local.",
                "sources": [],
                "cached": False,
                "sql": None,
                "memory": _update_memory(catalog_entities=catalog_entities),
            }
        return {
            "answer": f"🔒 Modo offline (sin LLM):\n\n{context}",
            "sources": sources,
            "cached": False,
            "sql": None,
            "memory": _update_memory(catalog_entities=catalog_entities),
        }

    # ── Capa híbrida: DB local PostgreSQL read-only ─────────────────────────
    db_context, db_sources, clarification, db_entities = _build_context_db_local(enriched_question, history)
    if clarification:
        return {"answer": clarification, "sources": [], "cached": False, "sql": None, "memory": _update_memory(db_entities=db_entities)}
    if db_context and db_sources:
        # Tenemos datos de DB local; pasarlos al LLM para redactar respuesta
        try:
            start = time.time()
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
            ]
            if history:
                for msg in history[-4:]:
                    if msg.get("role") in ("user", "assistant"):
                        messages.append({"role": msg["role"], "content": msg["content"][:500]})
            messages.append({"role": "user", "content": (
                f"Pregunta: {enriched_question}\n\n"
                f"Datos obtenidos de la base local:\n{db_context}\n\n"
                "Respondé de forma natural y conversacional, como si hablaras con un colega de negocios. "
                "Presentá los montos en millones o billones de Bs. cuando sea apropiado, nunca en notación científica."
            )})
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
            cache_set(cache_key, text)
            return {
                "answer": text,
                "sources": db_sources,
                "cached": False,
                "sql": None,
                "memory": _update_memory(db_entities=db_entities),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error redactando respuesta con datos de DB local (%s), cayendo a flujo SQL/catálogo.", exc)

    # ── Capa premium: catálogo enriquecido (prioridad sobre SQL genérico) ───
    catalog_context, catalog_sources, catalog_entities = _build_context_catalog(enriched_question, memory=memory)
    premium_sources = {
        "dashboard/data::pronostico_ejecutivo_mes",
        "dashboard/data::agencias_en_deterioro",
        "dashboard/data::rendimiento_grupos_centros",
        "dashboard/data::tendencia_productos",
        "dashboard/data::tendencia_sorteos",
        "dashboard/data::tickets_anulados_detalle",
        "dashboard/data::ventas_por_producto_y_mes",
        "dashboard/data::ventas_por_agencia_y_mes",
        "dashboard/data::ventas_por_sorteo_y_mes",
    }
    if any(s in premium_sources for s in catalog_sources):
        try:
            start = time.time()
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
            ]
            if history:
                for msg in history[-4:]:
                    if msg.get("role") in ("user", "assistant"):
                        messages.append({"role": msg["role"], "content": msg["content"][:500]})
            messages.append({"role": "user", "content": (
                f"Pregunta: {enriched_question}\n\n"
                f"Contexto:\n{catalog_context}\n\n"
                "Respondé de forma natural y conversacional, como si hablaras con un colega de negocios. "
                "Presentá los montos en millones o billones de Bs. cuando sea apropiado, nunca en notación científica."
            )})
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
            cache_set(cache_key, text)
            return {
                "answer": text,
                "sources": catalog_sources,
                "cached": False,
                "sql": None,
                "memory": _update_memory(catalog_entities=catalog_entities),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error redactando respuesta premium (%s), probando SQL/catálogo.", exc)

    # Decidir flujo SQL (catálogo curado DuckDB)
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
                    "memory": _update_memory(catalog_entities=catalog_entities if 'catalog_entities' in locals() else None, db_entities=db_entities if 'db_entities' in locals() else None),
                }
            else:
                logger.warning("SQL devolvió vacío, probando catálogo.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Flujo SQL falló (%s), cayendo a catálogo de funciones.", exc)

    # Modo catálogo fallback (funciones Python seguras)
    # Reutilizar contexto premium si ya fue calculado, sino llamar al catálogo
    if 'catalog_context' in locals() and 'catalog_sources' in locals():
        context, sources = catalog_context, catalog_sources
    else:
        context, sources, catalog_entities = _build_context_catalog(enriched_question, memory=memory)
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

    memory = _update_memory(catalog_entities=catalog_entities if 'catalog_entities' in locals() else None, db_entities=db_entities if 'db_entities' in locals() else None)

    return {"answer": text, "sources": sources, "cached": False, "sql": None, "memory": memory}


# ── UI Streamlit ─────────────────────────────────────────────────────────────

def render_chat_ui() -> None:
    """Componente Streamlit conversacional."""
    st.subheader("💬 Asistente de Negocios")

    if not is_configured():
        st.info("Modo estándar: consultá sobre ventas, agencias, productos y pronósticos.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "chat_memory" not in st.session_state:
        st.session_state.chat_memory = {}

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

        result = answer(pending, history=st.session_state.messages, memory=st.session_state.chat_memory)
        reply = result["answer"]
        st.session_state.chat_memory = result.get("memory", {})
        reply_time = datetime.now().strftime("%H:%M")
        with st.chat_message("assistant"):
            st.caption(reply_time)
            st.markdown(reply)
        st.session_state.messages.append({
            "role": "assistant",
            "content": reply,
            "timestamp": reply_time,
        })
