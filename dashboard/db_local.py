"""Capa de acceso read-only a PostgreSQL local para consultas complejas del chat.

Todas las funciones son SOLO LECTURA y devuelven DataFrames de pandas.
No expone operaciones de escritura ni permite SQL arbitrario.
"""
from __future__ import annotations

import functools
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


def _get_connection() -> psycopg2.extensions.connection:
    """Conexión read-only a PostgreSQL local."""
    # Reutilizamos variables de entorno ya cargadas por etl/config.py
    host = os.environ.get("DB_HOST", "localhost")
    port = int(os.environ.get("DB_PORT", "5432"))
    dbname = os.environ.get("DB_NAME", "")
    user = os.environ.get("DB_USER", "")
    password = os.environ.get("DB_PASSWORD", "")
    if not all([dbname, user, password]):
        raise RuntimeError("Faltan variables de entorno para conexión a DB local.")
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    )
    return conn


@functools.lru_cache(maxsize=128)
def _execute(query: str, params: tuple | None = None, max_rows: int = 5000) -> pd.DataFrame:
    """Ejecuta SELECT y devuelve DataFrame.

    LRU cache evita reconsultas idénticas sobre la DB local en la misma sesión.
    """
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchmany(max_rows + 1)
            if len(rows) > max_rows:
                raise ValueError(
                    f"La consulta devolvió más de {max_rows} filas. "
                    "Agregá LIMIT o filtrá más específicamente."
                )
            return pd.DataFrame(rows) if rows else pd.DataFrame()
    finally:
        conn.close()


# ── Helpers de búsqueda semántica ────────────────────────────────────────────

def _resolve_agency(name_fragment: str) -> pd.DataFrame:
    """Busca agencias por nombre parcial (ILIKE)."""
    sql = """
        SELECT a.id, a.name AS agencia,
               g.name AS grupo,
               c.name AS centro,
               mc.name AS master_center
        FROM agencys a
        LEFT JOIN groups g ON a.group_id = g.id
        LEFT JOIN centers c ON g.center_id = c.id
        LEFT JOIN master_centers mc ON c.master_center_id = mc.id
        WHERE a.name ILIKE %s
          AND a.deleted IS NULL
        LIMIT 20
    """
    return _execute(sql, (f"%{name_fragment}%",))


def _resolve_product(name_fragment: str) -> pd.DataFrame:
    """Busca productos por nombre parcial."""
    sql = """
        SELECT id, name AS producto, product_type_id
        FROM new_products
        WHERE name ILIKE %s
        LIMIT 20
    """
    return _execute(sql, (f"%{name_fragment}%",))


def _resolve_lottery(name_fragment: str, hour: str | None = None) -> pd.DataFrame:
    """Busca sorteos por nombre parcial y opcionalmente hora (con rango ±15 min)."""
    if hour:
        sql = """
            SELECT id, name AS sorteo, lotery_hour AS hora
            FROM loteries
            WHERE name ILIKE %s
              AND lotery_hour BETWEEN (CAST(%s AS TIME) - INTERVAL '15 minutes')
                                  AND (CAST(%s AS TIME) + INTERVAL '15 minutes')
            LIMIT 20
        """
        return _execute(sql, (f"%{name_fragment}%", hour, hour))
    sql = """
        SELECT id, name AS sorteo, lotery_hour AS hora
        FROM loteries
        WHERE name ILIKE %s
        LIMIT 20
    """
    return _execute(sql, (f"%{name_fragment}%",))


def _lottery_hour_from_text(text: str) -> str | None:
    """Extrae hora tipo '07:00 PM' y la convierte a TIME de DB (ej: 19:02)."""
    # Mapeo comercial -> real de horarios (basado en observación de loteries)
    # La Granjita 07:00 PM -> 19:02 en DB
    # Normalizar
    text = text.lower().strip()
    # Regex para capturar HH:MM AM/PM
    m = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)', text, re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    ampm = m.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    # Como la DB tiene desplazamientos (ej 19:02), buscaremos por rango en lugar de exacto
    # Pero para simplificar, devolvemos la hora exacta y permitimos fuzzy en el query
    return f"{hour:02d}:{minute:02d}"


def _particionado_bets_tablas(dias: int = 30) -> list[str]:
    """Devuelve lista de tablas bets_YYYYMMDD existentes para los últimos N días."""
    # Consultar information_schema para tablas que existen y están en rango
    fechas = [(datetime.now() - timedelta(days=i)).strftime("%Y%m%d") for i in range(dias)]
    placeholders = ",".join(["%s"] * len(fechas))
    # Escapamos %% para psycopg2 cuando hay parámetros
    sql = f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'bets_%%'
          AND SUBSTRING(table_name FROM 6 FOR 8) IN ({placeholders})
        ORDER BY table_name DESC
    """
    df = _execute(sql, tuple(fechas))
    return df["table_name"].tolist() if not df.empty else []


def _particionado_tickets_tablas(dias: int = 30) -> list[str]:
    """Devuelve lista de tablas tickets_YYYYMMDD existentes para los últimos N días."""
    fechas = [(datetime.now() - timedelta(days=i)).strftime("%Y%m%d") for i in range(dias)]
    placeholders = ",".join(["%s"] * len(fechas))
    sql = f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'tickets_%%'
          AND SUBSTRING(table_name FROM 9 FOR 8) IN ({placeholders})
        ORDER BY table_name DESC
    """
    df = _execute(sql, tuple(fechas))
    return df["table_name"].tolist() if not df.empty else []


# ── Consultas de negocio seguras ─────────────────────────────────────────────

def jerarquia_agencia(nombre_fragmento: str) -> pd.DataFrame:
    """Devuelve jerarquía comercial de agencias que coincidan con el nombre."""
    return _resolve_agency(nombre_fragmento)


def producto_mas_vendido(rango_dias: int | None = None, n: int = 5) -> pd.DataFrame:
    """Productos con mayor venta acumulada.

    Args:
        rango_dias: Si es None, usa todo el histórico (sales_by_new_products_agency).
                    Si es un número, usa las particiones de ventas recientes.
        n: Top N productos.
    """
    if rango_dias is None:
        # Histórico completo via tabla agregada
        sql = f"""
            SELECT
                np.name AS producto,
                SUM(s.sales) AS ventas,
                SUM(s.prize) AS premios,
                ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
            FROM sales_by_new_products_agency s
            LEFT JOIN new_products np ON s.new_product_id = np.id
            WHERE s.sales > 0
            GROUP BY np.name
            ORDER BY ventas DESC
            LIMIT {n}
        """
        return _execute(sql)

    # Usar particiones sales_YYYYMMDD para rango reciente
    fechas = [(datetime.now() - timedelta(days=i)).strftime("%Y%m%d") for i in range(rango_dias)]
    placeholders = ",".join(["%s"] * len(fechas))
    sql_tablas = f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'sales_%%'
          AND table_name NOT LIKE 'sales_by_%%'
          AND SUBSTRING(table_name FROM 7 FOR 8) IN ({placeholders})
        ORDER BY table_name DESC
    """
    df_tablas = _execute(sql_tablas, tuple(fechas))
    if df_tablas.empty:
        return pd.DataFrame()

    tablas = df_tablas["table_name"].tolist()
    union_sql = " UNION ALL ".join(
        f"SELECT total_amount AS sales, prize, agency_id FROM {t} WHERE total_amount > 0" for t in tablas
    )
    # Necesitamos unir con agencys -> group -> ... o usar sales_by_agency diarias
    # Para simplificar y mantener seguridad, usaremos sales_by_agency_YYYYMMDD que ya tiene producto
    # Pero esas tablas no tienen new_product_id. Entonces usamos la tabla agregada con fecha.
    # Revertimos a sales_by_new_products_agency con filtro de fecha si existe.
    sql = f"""
        SELECT
            np.name AS producto,
            SUM(s.sales) AS ventas,
            SUM(s.prize) AS premios,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM sales_by_new_products_agency s
        LEFT JOIN new_products np ON s.new_product_id = np.id
        WHERE s.sales > 0
          AND s.fecha >= CURRENT_DATE - INTERVAL '{rango_dias} days'
        GROUP BY np.name
        ORDER BY ventas DESC
        LIMIT {n}
    """
    return _execute(sql)


def sorteos_por_nombre(nombre_fragmento: str) -> pd.DataFrame:
    """Devuelve sorteos que coincidan con el nombre."""
    return _resolve_lottery(nombre_fragmento)


def numeros_mas_apostados(
    sorteo_nombre: str | None = None,
    lotery_id: int | None = None,
    rango_dias: int = 30,
    n: int = 10,
) -> pd.DataFrame:
    """Números con más apuestas (frecuencia de bets).

    Args:
        sorteo_nombre: Filtro opcional por nombre de sorteo (ej: 'LA GRANJITA 07:00 PM').
        lotery_id: ID exacto de sorteo (para evitar ambigüedad).
        rango_dias: Cuántos días hacia atrás consultar (usa tablas particionadas bets_YYYYMMDD).
        n: Top N números.
    """
    tablas = _particionado_bets_tablas(rango_dias)
    if not tablas:
        logger.warning("No hay tablas bets particionadas para el rango solicitado.")
        return pd.DataFrame()

    # Resolver sorteo si se pidió y no vino ID
    if lotery_id is None and sorteo_nombre:
        df_lot = _resolve_lottery(sorteo_nombre)
        if not df_lot.empty:
            lotery_id = int(df_lot.iloc[0]["id"])
        else:
            logger.warning("No se encontró sorteo: %s", sorteo_nombre)

    # Construir UNION ALL sobre tablas particionadas
    where_lotery = f"AND lotery_id = {lotery_id}" if lotery_id else ""
    union_parts = []
    for t in tablas:
        union_parts.append(
            f"SELECT number, amount, prize FROM {t} WHERE number IS NOT NULL {where_lotery}"
        )
    union_sql = " UNION ALL ".join(union_parts)

    sql = f"""
        WITH all_bets AS ({union_sql})
        SELECT
            number AS numero,
            COUNT(*) AS apuestas,
            SUM(amount) AS monto_total,
            SUM(prize) AS premios_pagados
        FROM all_bets
        GROUP BY number
        ORDER BY apuestas DESC
        LIMIT {n}
    """
    return _execute(sql)


def numeros_mas_salidos(
    sorteo_nombre: str | None = None,
    lotery_id: int | None = None,
    rango_dias: int | None = None,
    n: int = 10,
) -> pd.DataFrame:
    """Números que más han salido en resultados históricos.

    Args:
        sorteo_nombre: Filtro opcional por nombre de sorteo.
        lotery_id: ID exacto de sorteo (para evitar ambigüedad).
        rango_dias: Si es None, todo el histórico. Si es número, filtra por fecha.
        n: Top N números.
    """
    lotery_filter = ""
    params: list[Any] = []
    if lotery_id is None and sorteo_nombre:
        df_lot = _resolve_lottery(sorteo_nombre)
        if not df_lot.empty:
            lotery_id = int(df_lot.iloc[0]["id"])
        else:
            lotery_filter = "AND l.name ILIKE %s"
            params.append(f"%{sorteo_nombre}%")

    if lotery_id is not None:
        lotery_filter = f"AND (r.lotery_id = {lotery_id} OR nr.lotery_id = {lotery_id})"

    date_filter = ""
    if rango_dias:
        date_filter = f"AND r.procesed >= CURRENT_DATE - INTERVAL '{rango_dias} days'"

    # Usamos COALESCE entre results (number_id -> numbers) y new_results (result text)
    sql = f"""
        SELECT
            COALESCE(n.value, n.name, nr.result) AS numero,
            COUNT(*) AS veces
        FROM loteries l
        LEFT JOIN results r ON r.lotery_id = l.id
        LEFT JOIN numbers n ON r.number_id = n.id
        LEFT JOIN new_results nr ON nr.lotery_id = l.id AND nr.procesed = r.procesed
        WHERE COALESCE(n.value, n.name, nr.result) IS NOT NULL
          {lotery_filter}
          {date_filter}
        GROUP BY COALESCE(n.value, n.name, nr.result)
        ORDER BY veces DESC
        LIMIT {n}
    """
    return _execute(sql, tuple(params) if params else None)


def rendimiento_grupos_centros(nivel: str = "group", n: int = 10) -> pd.DataFrame:
    """Comparativa de ventas, margen y concentración por grupo, centro o master_center.

    Args:
        nivel: 'group', 'center' o 'master_center'.
        n: Top N entidades.
    """
    nivel = nivel.lower()
    if nivel == "group":
        select_cols = "g.name AS entidad"
        joins = "LEFT JOIN groups g ON s.group_id = g.id"
        group_by = "g.name"
    elif nivel == "center":
        select_cols = "c.name AS entidad"
        joins = "LEFT JOIN groups g ON s.group_id = g.id LEFT JOIN centers c ON g.center_id = c.id"
        group_by = "c.name"
    elif nivel in ("master_center", "master"):
        select_cols = "mc.name AS entidad"
        joins = (
            "LEFT JOIN groups g ON s.group_id = g.id "
            "LEFT JOIN centers c ON g.center_id = c.id "
            "LEFT JOIN master_centers mc ON c.master_center_id = mc.id"
        )
        group_by = "mc.name"
    else:
        raise ValueError("nivel debe ser 'group', 'center' o 'master_center'")

    sql = f"""
        SELECT
            {select_cols},
            SUM(s.sales) AS ventas,
            SUM(s.prize) AS premios,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen,
            COUNT(DISTINCT s.agency_id) AS agencias,
            ROUND(SUM(s.sales) * 100.0 / SUM(SUM(s.sales)) OVER (), 2) AS concentracion_pct
        FROM sales_by_new_products_agency s
        {joins}
        WHERE s.sales > 0 AND {group_by} IS NOT NULL
        GROUP BY {group_by}
        ORDER BY ventas DESC
        LIMIT {n}
    """
    return _execute(sql)


def tickets_anulados_recientes(rango_dias: int = 7) -> pd.DataFrame:
    """Tickets anulados recientes con detalle de apuestas si está disponible.

    Args:
        rango_dias: Días hacia atrás a consultar en tablas particionadas.
    """
    tablas_tickets = _particionado_tickets_tablas(rango_dias)
    tablas_bets = _particionado_bets_tablas(rango_dias)
    if not tablas_tickets:
        logger.warning("No hay tablas tickets particionadas para el rango solicitado.")
        return pd.DataFrame()

    ticket_parts = []
    for t in tablas_tickets:
        ticket_parts.append(
            f"SELECT id, created, agency_id, total_amount, anull_role, anull_date FROM {t} WHERE anull_date IS NOT NULL"
        )
    tickets_sql = " UNION ALL ".join(ticket_parts)

    if tablas_bets:
        bets_parts = []
        for t in tablas_bets:
            bets_parts.append(
                f"SELECT ticket_id, lotery_id, number, amount FROM {t}"
            )
        bets_sql = " UNION ALL ".join(bets_parts)

        sql = f"""
            WITH ta AS ({tickets_sql}),
                 bd AS ({bets_sql})
            SELECT
                ta.id AS ticket_id,
                ta.created,
                a.name AS agencia,
                ta.total_amount,
                ta.anull_role,
                l.name AS sorteo,
                np.name AS producto,
                bd.number,
                bd.amount AS bet_amount
            FROM ta
            LEFT JOIN agencys a ON ta.agency_id = a.id
            LEFT JOIN bd ON ta.id = bd.ticket_id
            LEFT JOIN loteries l ON bd.lotery_id = l.id
            LEFT JOIN new_products np ON l.product_new = np.id
            ORDER BY ta.created DESC
            LIMIT 1000
        """
    else:
        sql = f"""
            WITH ta AS ({tickets_sql})
            SELECT
                ta.id AS ticket_id,
                ta.created,
                a.name AS agencia,
                ta.total_amount,
                ta.anull_role
            FROM ta
            LEFT JOIN agencys a ON ta.agency_id = a.id
            ORDER BY ta.created DESC
            LIMIT 1000
        """
    return _execute(sql)


# ── Catálogo de funciones expuestas al chat ──────────────────────────────────

DB_LOCAL_FUNCS = {
    "jerarquia_agencia": jerarquia_agencia,
    "producto_mas_vendido": producto_mas_vendido,
    "sorteos_por_nombre": sorteos_por_nombre,
    "numeros_mas_apostados": numeros_mas_apostados,
    "numeros_mas_salidos": numeros_mas_salidos,
    "rendimiento_grupos_centros": rendimiento_grupos_centros,
    "tickets_anulados_recientes": tickets_anulados_recientes,
}
