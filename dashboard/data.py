"""Capa de acceso a datos via DuckDB sobre Parquet."""
from typing import Any

import duckdb
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

MONEDAS = {1: "Bs.", 2: "USD", 3: "BRL", 4: "PEN", 5: "COP"}


def _conn():
    return duckdb.connect()


def _cases(col: str, amount_col: str, rates: dict) -> str:
    parts = " ".join(f"WHEN {col} = {cid} THEN {amount_col} * {rate}" for cid, rate in rates.items())
    return f"CASE {parts} ELSE {amount_col} END"


def ventas_por_mes(currency_id: int | None = None) -> pd.DataFrame:
    where = f"WHERE moneda_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            DATE_TRUNC('month', fecha) AS mes,
            SUM(sales)  AS ventas,
            SUM(prize)  AS premios,
            SUM(sales) - SUM(prize) AS margen_bruto,
            ROUND((SUM(sales) - SUM(prize)) / NULLIF(SUM(sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_loteries.parquet'
        {where}
        GROUP BY 1
        ORDER BY 1
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def ventas_por_producto(currency_id: int | None = None) -> pd.DataFrame:
    where = f"WHERE s.currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            p.name AS producto,
            p.product_type_id AS tipo,
            SUM(s.sales)  AS ventas,
            SUM(s.prize)  AS premios,
            SUM(s.sales) - SUM(s.prize) AS margen_bruto,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/new_products.parquet' p
            ON s.new_product_id = p.id
        {where}
        GROUP BY 1, 2
        ORDER BY ventas DESC
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def ventas_por_producto_y_mes(currency_id: int | None = None) -> pd.DataFrame:
    where = f"WHERE s.currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            DATE_TRUNC('month', s.fecha) AS mes,
            p.name AS producto,
            SUM(s.sales)  AS ventas,
            SUM(s.prize)  AS premios,
            SUM(s.sales) - SUM(s.prize) AS margen_bruto,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/new_products.parquet' p
            ON s.new_product_id = p.id
        {where}
        GROUP BY 1, 2
        ORDER BY 1, ventas DESC
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["mes"] = df["mes"].astype(str)
    return df


def ventas_por_agencia_y_mes(currency_id: int | None = None) -> pd.DataFrame:
    where = f"WHERE s.currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            DATE_TRUNC('month', s.fecha) AS mes,
            a.name AS agencia,
            SUM(s.sales)  AS ventas,
            SUM(s.prize)  AS premios,
            SUM(s.sales) - SUM(s.prize) AS margen_bruto,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/agencys.parquet' a ON s.agency_id = a.id
        {where}
        GROUP BY 1, 2
        ORDER BY 1, ventas DESC
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["mes"] = df["mes"].astype(str)
    return df


def ventas_por_sorteo_y_mes(currency_id: int | None = None) -> pd.DataFrame:
    where = f"WHERE s.moneda_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            DATE_TRUNC('month', s.fecha) AS mes,
            l.name AS sorteo,
            l.lotery_hour AS hora,
            SUM(s.sales)  AS ventas,
            SUM(s.prize)  AS premios,
            SUM(s.sales) - SUM(s.prize) AS margen_bruto,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_loteries.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/loteries.parquet' l ON s.lotery_id = l.id
        {where}
        GROUP BY 1, 2, 3
        ORDER BY 1, ventas DESC
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["mes"] = df["mes"].astype(str)
    return df


def ventas_por_agencia_y_producto(n: int = 50) -> pd.DataFrame:
    """Ventas desagregadas por agencia y producto (para queries cruzadas)."""
    sql = f"""
        SELECT
            a.name  AS agencia,
            p.name  AS producto,
            SUM(s.sales)    AS ventas,
            SUM(s.prize)    AS premios,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/agencys.parquet' a ON s.agency_id = a.id
        LEFT JOIN '{DATA_DIR}/dimensions/new_products.parquet' p ON s.new_product_id = p.id
        WHERE s.sales > 0
        GROUP BY 1, 2
        ORDER BY ventas DESC
        LIMIT {n}
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def top_agencias(n: int = 20, currency_id: int | None = None) -> pd.DataFrame:
    where = f"WHERE s.currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            a.name  AS agencia,
            SUM(s.sales)    AS ventas,
            SUM(s.prize)    AS premios,
            SUM(s.ganancias) AS ganancias,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/agencys.parquet' a ON s.agency_id = a.id
        {where}
        GROUP BY 1
        ORDER BY ventas DESC
        LIMIT {n}
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def anulaciones_por_mes() -> pd.DataFrame:
    sql = f"""
        SELECT
            DATE_TRUNC('month', created) AS mes,
            COUNT(*)                              AS total_tickets,
            COUNT(*) FILTER (WHERE anull_date IS NOT NULL) AS anulados,
            ROUND(
                COUNT(*) FILTER (WHERE anull_date IS NOT NULL) * 100.0
                / NULLIF(COUNT(*), 0), 2
            ) AS pct_anulacion
        FROM '{DATA_DIR}/facts/tickets_*.parquet'
        GROUP BY 1
        ORDER BY 1
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def top_agencias_anulacion(n: int = 25) -> pd.DataFrame:
    sql = f"""
        SELECT
            a.name AS agencia,
            COUNT(*) AS total_tickets,
            COUNT(*) FILTER (WHERE t.anull_date IS NOT NULL) AS anulados,
            ROUND(
                COUNT(*) FILTER (WHERE t.anull_date IS NOT NULL) * 100.0
                / NULLIF(COUNT(*), 0), 2
            ) AS pct_anulacion
        FROM '{DATA_DIR}/facts/tickets_*.parquet' t
        LEFT JOIN '{DATA_DIR}/dimensions/agencys.parquet' a ON t.agency_id = a.id
        GROUP BY a.name
        HAVING COUNT(*) > 100
        ORDER BY pct_anulacion DESC
        LIMIT {n}
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def anulaciones_por_rol() -> pd.DataFrame:
    sql = f"""
        SELECT
            COALESCE(anull_role, 'sin_rol') AS rol,
            COUNT(*) AS anulaciones
        FROM '{DATA_DIR}/facts/tickets_*.parquet'
        WHERE anull_date IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def kpis_anulaciones() -> dict:
    sql = f"""
        SELECT
            COUNT(*)                                                        AS total_tickets,
            COUNT(*) FILTER (WHERE anull_date IS NOT NULL)                  AS anulados,
            ROUND(
                COUNT(*) FILTER (WHERE anull_date IS NOT NULL) * 100.0
                / NULLIF(COUNT(*), 0), 2
            )                                                               AS pct_anulacion
        FROM '{DATA_DIR}/facts/tickets_*.parquet'
    """
    with _conn() as conn:
        row = conn.execute(sql).fetchone()
    return {
        "total_tickets": row[0] or 0,
        "anulados": row[1] or 0,
        "pct_anulacion": row[2] or 0,
    }


def health_score_agencias(currency_id: int | None = None) -> pd.DataFrame:
    """Health score por agencia: ventas, margen, anulaciones, actividad."""
    where_sales = f"AND s.currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        WITH ventas AS (
            SELECT
                s.agency_id,
                a.name                                      AS agencia,
                SUM(s.sales)                                AS ventas,
                SUM(s.prize)                                AS premios,
                ROUND((SUM(s.sales) - SUM(s.prize))
                    / NULLIF(SUM(s.sales), 0) * 100, 2)    AS pct_margen,
                COUNT(DISTINCT s.fecha)                     AS dias_activos
            FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
            LEFT JOIN '{DATA_DIR}/dimensions/agencys.parquet' a ON s.agency_id = a.id
            WHERE s.sales > 0 {where_sales}
            GROUP BY s.agency_id, a.name
        ),
        anulaciones AS (
            SELECT
                agency_id,
                COUNT(*)                                                    AS total_tickets,
                ROUND(COUNT(*) FILTER (WHERE anull_date IS NOT NULL) * 100.0
                    / NULLIF(COUNT(*), 0), 2)                               AS pct_anulacion
            FROM '{DATA_DIR}/facts/tickets_*.parquet'
            GROUP BY agency_id
        )
        SELECT
            v.agencia,
            v.ventas,
            v.premios,
            v.pct_margen,
            v.dias_activos,
            COALESCE(a.total_tickets, 0)    AS total_tickets,
            COALESCE(a.pct_anulacion, 0)    AS pct_anulacion,
            ROUND(
                LEAST(v.ventas / NULLIF(MAX(v.ventas) OVER (), 0) * 40, 40)
                + GREATEST(LEAST(v.pct_margen / 40.0 * 30, 30), 0)
                + LEAST(v.dias_activos / 180.0 * 20, 20)
                + GREATEST(10 - COALESCE(a.pct_anulacion, 0) / 5.0, 0)
            , 1) AS health_score
        FROM ventas v
        LEFT JOIN anulaciones a ON v.agency_id = a.agency_id
        ORDER BY health_score DESC
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def distribucion_agencias(currency_id: int | None = None) -> pd.DataFrame:
    """Scatter: ventas vs % margen por agencia — para segmentación visual."""
    where = f"AND currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            a.name AS agencia,
            SUM(s.sales)    AS ventas,
            SUM(s.prize)    AS premios,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen,
            COUNT(DISTINCT s.fecha) AS dias_activos
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/agencys.parquet' a ON s.agency_id = a.id
        WHERE s.sales > 0 {where}
        GROUP BY a.name
        HAVING SUM(s.sales) > 1000
            AND ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) BETWEEN -100 AND 100
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def kpis_globales(currency_id: int | None = None) -> dict:
    where = f"WHERE currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            SUM(sales)                                                          AS ventas,
            SUM(prize)                                                          AS premios,
            SUM(sales) - SUM(prize)                                             AS margen_bruto,
            ROUND((SUM(sales) - SUM(prize)) / NULLIF(SUM(sales), 0) * 100, 2)  AS pct_margen,
            COUNT(DISTINCT agency_id)                                           AS agencias_activas
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet'
        {where}
    """
    with _conn() as conn:
        row = conn.execute(sql).fetchone()
    return {
        "ventas": row[0] or 0,
        "premios": row[1] or 0,
        "margen_bruto": row[2] or 0,
        "pct_margen": row[3] or 0,
        "agencias_activas": row[4] or 0,
    }


def ventas_por_mes_unificado(rates: dict) -> pd.DataFrame:
    """Todas las monedas convertidas a VES usando tasas de cambio."""
    cases = " ".join(
        f"WHEN moneda_id = {cid} THEN sales * {rate}"
        for cid, rate in rates.items()
    )
    prize_cases = " ".join(
        f"WHEN moneda_id = {cid} THEN prize * {rate}"
        for cid, rate in rates.items()
    )
    sql = f"""
        SELECT
            DATE_TRUNC('month', fecha) AS mes,
            SUM(CASE {cases} ELSE sales END)  AS ventas,
            SUM(CASE {prize_cases} ELSE prize END) AS premios,
            SUM(CASE {cases} ELSE sales END) - SUM(CASE {prize_cases} ELSE prize END) AS margen_bruto,
            ROUND(
                (SUM(CASE {cases} ELSE sales END) - SUM(CASE {prize_cases} ELSE prize END))
                / NULLIF(SUM(CASE {cases} ELSE sales END), 0) * 100, 2
            ) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_loteries.parquet'
        GROUP BY 1
        ORDER BY 1
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["mes"] = df["mes"].astype(str)
    return df


def kpis_globales_unificado(rates: dict) -> dict:
    """KPIs con todas las monedas convertidas a VES."""
    cases = " ".join(
        f"WHEN currency_id = {cid} THEN sales * {rate}"
        for cid, rate in rates.items()
    )
    prize_cases = " ".join(
        f"WHEN currency_id = {cid} THEN prize * {rate}"
        for cid, rate in rates.items()
    )
    sql = f"""
        SELECT
            SUM(CASE {cases} ELSE sales END)   AS ventas,
            SUM(CASE {prize_cases} ELSE prize END) AS premios,
            COUNT(DISTINCT agency_id)           AS agencias_activas
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet'
    """
    with _conn() as conn:
        row = conn.execute(sql).fetchone()
    ventas = row[0] or 0
    premios = row[1] or 0
    margen = ventas - premios
    return {
        "ventas": ventas,
        "premios": premios,
        "margen_bruto": margen,
        "pct_margen": round(margen / ventas * 100, 2) if ventas else 0,
        "agencias_activas": row[2] or 0,
    }


def health_score_agencias_unificado(rates: dict) -> pd.DataFrame:
    cs = _cases("s.currency_id", "s.sales", rates)
    cp = _cases("s.currency_id", "s.prize", rates)
    sql = f"""
        WITH ventas AS (
            SELECT
                s.agency_id,
                a.name                                                          AS agencia,
                SUM({cs})                                                       AS ventas,
                SUM({cp})                                                       AS premios,
                ROUND((SUM({cs}) - SUM({cp})) / NULLIF(SUM({cs}), 0) * 100, 2) AS pct_margen,
                COUNT(DISTINCT s.fecha)                                         AS dias_activos
            FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
            LEFT JOIN '{DATA_DIR}/dimensions/agencys.parquet' a ON s.agency_id = a.id
            WHERE s.sales > 0
            GROUP BY s.agency_id, a.name
        ),
        anulaciones AS (
            SELECT
                agency_id,
                COUNT(*) AS total_tickets,
                ROUND(COUNT(*) FILTER (WHERE anull_date IS NOT NULL) * 100.0
                    / NULLIF(COUNT(*), 0), 2) AS pct_anulacion
            FROM '{DATA_DIR}/facts/tickets_*.parquet'
            GROUP BY agency_id
        )
        SELECT
            v.agencia, v.ventas, v.premios, v.pct_margen, v.dias_activos,
            COALESCE(a.total_tickets, 0) AS total_tickets,
            COALESCE(a.pct_anulacion, 0) AS pct_anulacion,
            ROUND(
                LEAST(v.ventas / NULLIF(MAX(v.ventas) OVER (), 0) * 40, 40)
                + GREATEST(LEAST(v.pct_margen / 40.0 * 30, 30), 0)
                + LEAST(v.dias_activos / 180.0 * 20, 20)
                + GREATEST(10 - COALESCE(a.pct_anulacion, 0) / 5.0, 0)
            , 1) AS health_score
        FROM ventas v
        LEFT JOIN anulaciones a ON v.agency_id = a.agency_id
        ORDER BY health_score DESC
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def distribucion_agencias_unificado(rates: dict) -> pd.DataFrame:
    cs = _cases("s.currency_id", "s.sales", rates)
    cp = _cases("s.currency_id", "s.prize", rates)
    sql = f"""
        SELECT
            a.name AS agencia,
            SUM({cs}) AS ventas,
            SUM({cp}) AS premios,
            ROUND((SUM({cs}) - SUM({cp})) / NULLIF(SUM({cs}), 0) * 100, 2) AS pct_margen,
            COUNT(DISTINCT s.fecha) AS dias_activos
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/agencys.parquet' a ON s.agency_id = a.id
        WHERE s.sales > 0
        GROUP BY a.name
        HAVING SUM({cs}) > 1000
            AND ROUND((SUM({cs}) - SUM({cp})) / NULLIF(SUM({cs}), 0) * 100, 2) BETWEEN -100 AND 100
    """
    with _conn() as conn:
        return conn.execute(sql).df()


PRODUCT_TYPES = {1: "Animalitos", 2: "Triples", 3: "Terminales", 4: "Tripletas", 5: "Centenas/Zoo"}


def ventas_por_tipo_producto(currency_id: int | None = None) -> pd.DataFrame:
    where = f"AND s.currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            COALESCE(p.product_type_id, 0)  AS tipo_id,
            SUM(s.sales)                     AS ventas,
            SUM(s.prize)                     AS premios,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/new_products.parquet' p ON s.new_product_id = p.id
        WHERE s.sales > 0 {where}
        GROUP BY 1
        ORDER BY ventas DESC
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["tipo"] = df["tipo_id"].map(PRODUCT_TYPES).fillna("Otro")
    return df


def evolucion_productos(currency_id: int | None = None) -> pd.DataFrame:
    where = f"AND s.currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            DATE_TRUNC('month', s.fecha)     AS mes,
            COALESCE(p.product_type_id, 0)   AS tipo_id,
            SUM(s.sales)                      AS ventas
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/new_products.parquet' p ON s.new_product_id = p.id
        WHERE s.sales > 0 {where}
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["mes"] = df["mes"].astype(str)
    df["tipo"] = df["tipo_id"].map(PRODUCT_TYPES).fillna("Otro")
    return df


def top_sorteos(currency_id: int | None = None, n: int = 20) -> pd.DataFrame:
    where = f"AND s.moneda_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            l.name                           AS sorteo,
            l.lotery_hour                    AS hora,
            SUM(s.sales)                     AS ventas,
            SUM(s.prize)                     AS premios,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen,
            COUNT(DISTINCT s.fecha)          AS dias_activos
        FROM '{DATA_DIR}/aggregated/sales_by_loteries.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/loteries.parquet' l ON s.lotery_id = l.id
        WHERE s.sales > 0 {where}
        GROUP BY 1, 2
        ORDER BY ventas DESC
        LIMIT {n}
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def ventas_por_sorteo_y_hora(n: int = 50) -> pd.DataFrame:
    """Ventas por sorteo específico y hora del día."""
    sql = f"""
        SELECT
            l.name                           AS sorteo,
            l.lotery_hour                    AS hora,
            SUM(s.sales)                     AS ventas,
            SUM(s.prize)                     AS premios,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_loteries.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/loteries.parquet' l ON s.lotery_id = l.id
        WHERE s.sales > 0 AND l.lotery_hour IS NOT NULL
        GROUP BY 1, 2
        ORDER BY ventas DESC
        LIMIT {n}
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def ventas_por_hora(currency_id: int | None = None) -> pd.DataFrame:
    where = f"AND s.moneda_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            l.lotery_hour                    AS hora,
            SUM(s.sales)                     AS ventas,
            ROUND((SUM(s.sales) - SUM(s.prize)) / NULLIF(SUM(s.sales), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_loteries.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/loteries.parquet' l ON s.lotery_id = l.id
        WHERE s.sales > 0 AND l.lotery_hour IS NOT NULL {where}
        GROUP BY 1
        ORDER BY 1
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def ventas_por_tipo_producto_unificado(rates: dict) -> pd.DataFrame:
    cs = _cases("s.currency_id", "s.sales", rates)
    cp = _cases("s.currency_id", "s.prize", rates)
    sql = f"""
        SELECT
            COALESCE(p.product_type_id, 0) AS tipo_id,
            SUM({cs}) AS ventas,
            SUM({cp}) AS premios,
            ROUND((SUM({cs}) - SUM({cp})) / NULLIF(SUM({cs}), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/new_products.parquet' p ON s.new_product_id = p.id
        WHERE s.sales > 0
        GROUP BY 1
        ORDER BY ventas DESC
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["tipo"] = df["tipo_id"].map(PRODUCT_TYPES).fillna("Otro")
    return df


def evolucion_productos_unificado(rates: dict) -> pd.DataFrame:
    cs = _cases("s.currency_id", "s.sales", rates)
    sql = f"""
        SELECT
            DATE_TRUNC('month', s.fecha) AS mes,
            COALESCE(p.product_type_id, 0) AS tipo_id,
            SUM({cs}) AS ventas
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/new_products.parquet' p ON s.new_product_id = p.id
        WHERE s.sales > 0
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["mes"] = df["mes"].astype(str)
    df["tipo"] = df["tipo_id"].map(PRODUCT_TYPES).fillna("Otro")
    return df


def top_sorteos_unificado(rates: dict, n: int = 20) -> pd.DataFrame:
    cs = _cases("s.moneda_id", "s.sales", rates)
    cp = _cases("s.moneda_id", "s.prize", rates)
    sql = f"""
        SELECT
            l.name AS sorteo,
            l.lotery_hour AS hora,
            SUM({cs}) AS ventas,
            SUM({cp}) AS premios,
            ROUND((SUM({cs}) - SUM({cp})) / NULLIF(SUM({cs}), 0) * 100, 2) AS pct_margen,
            COUNT(DISTINCT s.fecha) AS dias_activos
        FROM '{DATA_DIR}/aggregated/sales_by_loteries.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/loteries.parquet' l ON s.lotery_id = l.id
        WHERE s.sales > 0
        GROUP BY 1, 2
        ORDER BY ventas DESC
        LIMIT {n}
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def ventas_por_hora_unificado(rates: dict) -> pd.DataFrame:
    cs = _cases("s.moneda_id", "s.sales", rates)
    cp = _cases("s.moneda_id", "s.prize", rates)
    sql = f"""
        SELECT
            l.lotery_hour AS hora,
            SUM({cs}) AS ventas,
            ROUND((SUM({cs}) - SUM({cp})) / NULLIF(SUM({cs}), 0) * 100, 2) AS pct_margen
        FROM '{DATA_DIR}/aggregated/sales_by_loteries.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/loteries.parquet' l ON s.lotery_id = l.id
        WHERE s.sales > 0 AND l.lotery_hour IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """
    with _conn() as conn:
        return conn.execute(sql).df()


# ── Eje 5: Riesgo ──────────────────────────────────────────────────────────

def payout_ratio_por_producto(currency_id: int | None = None) -> pd.DataFrame:
    where = f"AND s.currency_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            p.name                          AS producto,
            SUM(s.sales)                    AS ventas,
            SUM(s.prize)                    AS premios,
            ROUND(SUM(s.prize) / NULLIF(SUM(s.sales), 0) * 100, 2) AS payout_ratio
        FROM '{DATA_DIR}/aggregated/sales_by_agency.parquet' s
        LEFT JOIN '{DATA_DIR}/dimensions/new_products.parquet' p ON s.new_product_id = p.id
        WHERE s.sales > 0 {where}
        GROUP BY 1
        ORDER BY payout_ratio DESC
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def payout_ratio_por_mes(currency_id: int | None = None) -> pd.DataFrame:
    where = f"WHERE moneda_id = {currency_id}" if currency_id else ""
    sql = f"""
        SELECT
            DATE_TRUNC('month', fecha)      AS mes,
            SUM(sales)                      AS ventas,
            SUM(prize)                      AS premios,
            ROUND(SUM(prize) / NULLIF(SUM(sales), 0) * 100, 2) AS payout_ratio
        FROM '{DATA_DIR}/aggregated/sales_by_loteries.parquet'
        {where}
        GROUP BY 1
        ORDER BY 1
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["mes"] = df["mes"].astype(str)
    return df


def numeros_mas_apostados(n: int = 30) -> pd.DataFrame:
    sql = f"""
        SELECT
            number,
            COUNT(*)        AS apuestas,
            SUM(amount)     AS monto_total,
            SUM(prize)      AS premios_pagados,
            ROUND(SUM(prize) / NULLIF(SUM(amount), 0) * 100, 2) AS payout_ratio
        FROM '{DATA_DIR}/facts/bets_*.parquet'
        WHERE number IS NOT NULL
        GROUP BY 1
        ORDER BY apuestas DESC
        LIMIT {n}
    """
    with _conn() as conn:
        return conn.execute(sql).df()


# ── Eje 6: Proveedores ─────────────────────────────────────────────────────

def _provider_parquet_exists() -> bool:
    return (DATA_DIR / "aggregated" / "tickets_provider.parquet").exists()


def volumen_por_proveedor() -> pd.DataFrame:
    if not _provider_parquet_exists():
        return pd.DataFrame()
    sql = f"""
        SELECT
            tp.provider,
            COUNT(*)                        AS tickets,
            COUNT(DISTINCT DATE(tp.created)) AS dias_activos
        FROM '{DATA_DIR}/aggregated/tickets_provider.parquet' tp
        GROUP BY 1
        ORDER BY tickets DESC
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def evolucion_proveedor_mes() -> pd.DataFrame:
    if not _provider_parquet_exists():
        return pd.DataFrame()
    sql = f"""
        SELECT
            DATE_TRUNC('month', created)    AS mes,
            provider,
            COUNT(*)                        AS tickets
        FROM '{DATA_DIR}/aggregated/tickets_provider.parquet'
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    with _conn() as conn:
        df = conn.execute(sql).df()
    df["mes"] = df["mes"].astype(str)
    return df


# ── Eje 7: Predicciones ML ─────────────────────────────────────────────────

PREDICTIONS_DIR = DATA_DIR / "predictions"


def _pred_parquet_path(name: str) -> Path:
    return PREDICTIONS_DIR / f"{name}.parquet"


def _read_prediction(name: str, columns: list[str]) -> pd.DataFrame:
    """Lee un parquet de predicciones; devuelve DataFrame vacío si no existe."""
    path = _pred_parquet_path(name)
    if not path.exists():
        return pd.DataFrame({col: pd.Series(dtype=object) for col in columns})
    with _conn() as conn:
        return conn.execute(f"SELECT * FROM '{path}'").df()


def prediccion_clusters() -> pd.DataFrame:
    """Segmentación de agencias vía KMeans + PCA."""
    cols = [
        "agency_id", "cluster_id", "pca_x", "pca_y",
        "centroid_distance", "run_id", "run_date",
    ]
    return _read_prediction("agency_clusters", cols)


def prediccion_anomalias() -> pd.DataFrame:
    """Scores de anomalías por agencia-período."""
    cols = [
        "agency_id", "period", "anomaly_score", "is_anomaly",
        "severity", "exclusion_reason", "run_id", "run_date",
    ]
    return _read_prediction("anomaly_scores", cols)


def prediccion_forecast() -> pd.DataFrame:
    """Pronósticos de ventas por entidad y fecha futura."""
    cols = [
        "entity_type", "entity_id", "forecast_date", "yhat",
        "yhat_lower", "yhat_upper", "model", "run_id", "run_date",
    ]
    return _read_prediction("forecast_sales", cols)


def prediccion_churn() -> pd.DataFrame:
    """Riesgo de abandono por agencia."""
    cols = [
        "agency_id", "churn_probability", "risk_band",
        "top_features", "prediction_date", "run_id",
    ]
    return _read_prediction("agency_churn_risk", cols)


def prediccion_basket() -> pd.DataFrame:
    """Reglas de asociación de market basket."""
    cols = [
        "antecedent", "consequent", "support",
        "confidence", "lift", "period", "run_id",
    ]
    return _read_prediction("basket_rules", cols)


def predicciones_disponibles() -> dict[str, bool]:
    """Devuelve un mapa de qué predicciones existen en disco."""
    return {
        "clusters": _pred_parquet_path("agency_clusters").exists(),
        "anomalies": _pred_parquet_path("anomaly_scores").exists(),
        "forecast": _pred_parquet_path("forecast_sales").exists(),
        "churn": _pred_parquet_path("agency_churn_risk").exists(),
        "basket": _pred_parquet_path("basket_rules").exists(),
    }


def fallos_por_proveedor() -> pd.DataFrame:
    path = DATA_DIR / "aggregated" / "log_api_provider.parquet"
    if not path.exists():
        return pd.DataFrame()
    sql = f"""
        SELECT
            provider,
            COUNT(*)                                                        AS total_calls,
            COUNT(*) FILTER (WHERE status != 'success')                     AS fallos,
            ROUND(COUNT(*) FILTER (WHERE status != 'success') * 100.0
                / NULLIF(COUNT(*), 0), 2)                                   AS pct_fallo
        FROM '{path}'
        GROUP BY 1
        ORDER BY pct_fallo DESC
    """
    with _conn() as conn:
        return conn.execute(sql).df()


# ── Capacidades premium de negocio ───────────────────────────────────────────

def _detectar_mes_parcial(df_mes: pd.DataFrame) -> tuple[pd.DataFrame, dict | None]:
    """Detecta si el último mes del histórico es parcial comparando contra la mediana reciente."""
    if len(df_mes) < 2:
        return df_mes.copy(), None
    ultimo = df_mes.iloc[-1]
    n = min(6, len(df_mes) - 1)
    mediana_reciente = df_mes.iloc[-(n + 1) : -1]["ventas"].median()
    if mediana_reciente and mediana_reciente > 0:
        if ultimo["ventas"] < mediana_reciente * 0.4:
            return df_mes.iloc[:-1].copy(), {
                "mes": str(ultimo["mes"]),
                "ventas": float(ultimo["ventas"]),
                "motivo": "ventas muy inferiores al promedio reciente (mes probablemente incompleto)",
            }
    return df_mes.copy(), None


def _forecast_es_implausible(yhat: float, mediana_hist: float) -> bool:
    """Devuelve True si el forecast es claramente inválido respecto al histórico."""
    if pd.isna(yhat) or yhat <= 0:
        return True
    if mediana_hist and mediana_hist > 0:
        if yhat < mediana_hist * 0.1 or yhat > mediana_hist * 10:
            return True
    return False


def _estimar_proximo_mes_heuristico(df_completo: pd.DataFrame, prox_mes_dt: pd.Timestamp) -> dict:
    """Construye fallback basado en tendencia reciente + estacionalidad histórica."""
    if df_completo.empty or pd.isna(prox_mes_dt):
        return {"mes": None, "pronostico": None, "pronostico_min": None, "pronostico_max": None}

    df = df_completo.copy()
    df["mes_dt"] = pd.to_datetime(df["mes"], errors="coerce")
    mes_num_obj = prox_mes_dt.month

    ult_3_mean = df.tail(3)["ventas"].mean()
    avg_mes_obj = df[df["mes_dt"].dt.month == mes_num_obj]["ventas"].mean()

    if pd.notna(avg_mes_obj) and avg_mes_obj > 0:
        pronostico = round(ult_3_mean * 0.7 + avg_mes_obj * 0.3, 2)
    else:
        pronostico = round(ult_3_mean, 2)

    return {
        "mes": prox_mes_dt.strftime("%Y-%m-%d"),
        "pronostico": pronostico,
        "pronostico_min": round(pronostico * 0.85, 2),
        "pronostico_max": round(pronostico * 1.15, 2),
    }


def pronostico_ejecutivo_mes() -> dict:
    """Devuelve pronóstico nacional + contexto histórico para narrativa ejecutiva."""
    df_forecast = prediccion_forecast()
    df_mes = ventas_por_mes()

    result: dict[str, Any] = {
        "proximo_mes": None,
        "pronostico": None,
        "pronostico_min": None,
        "pronostico_max": None,
        "ventas_ultimo_mes": None,
        "variacion_mom_pct": None,
        "tendencia_3m_pct": None,
        "mejores_meses": [],
        "peores_meses": [],
        "metodo": None,
        "base_historica_mes": None,
        "forecast_confiable": False,
        "warning": None,
    }

    if not df_mes.empty and "mes" in df_mes.columns and "ventas" in df_mes.columns:
        df_mes = df_mes.sort_values("mes").reset_index(drop=True)
        df_mes["ventas"] = pd.to_numeric(df_mes["ventas"], errors="coerce")

        # Detectar y excluir mes parcial
        df_mes_completo, info_parcial = _detectar_mes_parcial(df_mes)
        if info_parcial:
            result["warning"] = (
                f"Se excluyó el mes {info_parcial['mes']} del cierre base porque "
                f"presenta ventas de {info_parcial['ventas']:,.0f}, muy por debajo del histórico reciente."
            )

        if not df_mes_completo.empty:
            ultimo = df_mes_completo.iloc[-1]
            result["ventas_ultimo_mes"] = float(ultimo["ventas"]) if pd.notna(ultimo["ventas"]) else None
            result["base_historica_mes"] = str(ultimo["mes"])

            if len(df_mes_completo) >= 2:
                penultimo = df_mes_completo.iloc[-2]
                if penultimo["ventas"] and penultimo["ventas"] != 0:
                    result["variacion_mom_pct"] = round(
                        (ultimo["ventas"] - penultimo["ventas"]) / penultimo["ventas"] * 100, 2
                    )

            if len(df_mes_completo) >= 6:
                ult_3 = df_mes_completo.tail(3)["ventas"].mean()
                prev_3 = df_mes_completo.iloc[-6:-3]["ventas"].mean()
                if prev_3 and prev_3 != 0:
                    result["tendencia_3m_pct"] = round((ult_3 - prev_3) / prev_3 * 100, 2)

            # Estacionalidad sobre meses completos
            df_mes_completo["mes_dt"] = pd.to_datetime(df_mes_completo["mes"], errors="coerce")
            df_mes_completo["mes_num"] = df_mes_completo["mes_dt"].dt.month
            mes_avg = df_mes_completo.groupby("mes_num")["ventas"].mean().sort_values(ascending=False)
            result["mejores_meses"] = [int(m) for m in mes_avg.head(3).index.tolist()]
            result["peores_meses"] = [int(m) for m in mes_avg.tail(3).index.tolist()]

            # Forecast
            mediana_hist = df_mes_completo.tail(6)["ventas"].median()
            forecast_encontrado = False

            if not df_forecast.empty and "entity_type" in df_forecast.columns:
                nacional = df_forecast[df_forecast["entity_type"] == "nacional"]
                if not nacional.empty and "forecast_date" in nacional.columns:
                    nacional = nacional.sort_values("forecast_date")
                    for _, row in nacional.iterrows():
                        fecha = row.get("forecast_date")
                        if pd.isna(fecha) or str(fecha) <= str(result["base_historica_mes"]):
                            continue
                        yhat = row.get("yhat")
                        if _forecast_es_implausible(yhat, mediana_hist):
                            continue
                        result["proximo_mes"] = str(fecha)
                        result["pronostico"] = float(yhat)
                        result["pronostico_min"] = (
                            float(row["yhat_lower"])
                            if pd.notna(row.get("yhat_lower"))
                            else round(float(yhat) * 0.85, 2)
                        )
                        result["pronostico_max"] = (
                            float(row["yhat_upper"])
                            if pd.notna(row.get("yhat_upper"))
                            else round(float(yhat) * 1.15, 2)
                        )
                        result["metodo"] = "modelo_ml"
                        result["forecast_confiable"] = True
                        forecast_encontrado = True
                        break

            if not forecast_encontrado:
                # El próximo mes se calcula sobre el histórico original (incluye parcial)
                # para que "próximo mes" sea siempre el mes siguiente al último conocido
                ultimo_dt_global = pd.to_datetime(df_mes.iloc[-1]["mes"], errors="coerce")
                prox_mes_dt = ultimo_dt_global + pd.DateOffset(months=1)
                fallback = _estimar_proximo_mes_heuristico(df_mes_completo, prox_mes_dt)
                result["proximo_mes"] = fallback["mes"]
                result["pronostico"] = fallback["pronostico"]
                result["pronostico_min"] = fallback["pronostico_min"]
                result["pronostico_max"] = fallback["pronostico_max"]
                result["metodo"] = "heuristico"
                result["forecast_confiable"] = False
                if not result["warning"]:
                    result["warning"] = (
                        "No hay pronóstico del modelo disponible. "
                        "Se usa una estimación referencial basada en tendencia y estacionalidad histórica."
                    )
                else:
                    result["warning"] += (
                        " Además, no hay pronóstico del modelo disponible; "
                        "se usa una estimación referencial basada en tendencia y estacionalidad histórica."
                    )

    return result


def agencias_en_deterioro(n: int = 10) -> pd.DataFrame:
    """Agencias con ventas recientes menores al histórico, aunque aún activas."""
    sales_path = DATA_DIR / "aggregated" / "sales_by_agency.parquet"
    agencys_path = DATA_DIR / "dimensions" / "agencys.parquet"
    if not sales_path.exists():
        return pd.DataFrame()

    sql = f"""
    WITH params AS (SELECT MAX(fecha) AS max_f FROM '{sales_path}'),
         reciente AS (
             SELECT agency_id,
                    SUM(sales) AS ventas_reciente,
                    SUM(prize) AS premios_reciente,
                    COUNT(DISTINCT fecha) AS dias_activos
             FROM '{sales_path}', params
             WHERE fecha >= max_f - INTERVAL '30 days'
             GROUP BY agency_id
         ),
         previo AS (
             SELECT agency_id,
                    SUM(sales) AS ventas_previo,
                    COUNT(DISTINCT fecha) AS dias_previo
             FROM '{sales_path}', params
             WHERE fecha >= max_f - INTERVAL '60 days'
               AND fecha < max_f - INTERVAL '30 days'
             GROUP BY agency_id
         )
    SELECT a.name AS agencia,
           r.agency_id,
           r.ventas_reciente,
           p.ventas_previo,
           ROUND((r.ventas_reciente - p.ventas_previo)
                 / NULLIF(p.ventas_previo, 0) * 100, 2) AS cambio_pct,
           ROUND((r.ventas_reciente - r.premios_reciente)
                 / NULLIF(r.ventas_reciente, 0) * 100, 2) AS pct_margen,
           r.dias_activos
    FROM reciente r
    LEFT JOIN previo p ON r.agency_id = p.agency_id
    LEFT JOIN '{agencys_path}' a ON r.agency_id = a.id
    WHERE p.ventas_previo > 0 AND r.ventas_reciente > 0
    ORDER BY cambio_pct ASC
    LIMIT {n}
    """
    with _conn() as conn:
        df = conn.execute(sql).df()

    # Enriquecer con anomalías y churn si existen
    try:
        df_anom = prediccion_anomalias()
        if not df_anom.empty and {"agency_id", "severity"}.issubset(df_anom.columns):
            df_anom = df_anom.sort_values("period", ascending=False).drop_duplicates("agency_id")
            df = df.merge(df_anom[["agency_id", "severity"]], on="agency_id", how="left")
    except Exception:
        pass

    try:
        df_churn = prediccion_churn()
        if not df_churn.empty and {"agency_id", "churn_probability", "risk_band"}.issubset(df_churn.columns):
            df = df.merge(df_churn[["agency_id", "churn_probability", "risk_band"]], on="agency_id", how="left")
    except Exception:
        pass

    return df


def rendimiento_grupos_centros(nivel: str = "group", n: int = 10) -> pd.DataFrame:
    """Comparativa de grupos, centros o master_centers por ventas y concentración."""
    nivel = nivel.lower()
    sales_path = DATA_DIR / "aggregated" / "sales_by_agency.parquet"
    agencys_path = DATA_DIR / "dimensions" / "agencys.parquet"
    groups_path = DATA_DIR / "dimensions" / "groups.parquet"
    centers_path = DATA_DIR / "dimensions" / "centers.parquet"
    master_centers_path = DATA_DIR / "dimensions" / "master_centers.parquet"

    if not sales_path.exists() or not agencys_path.exists():
        return pd.DataFrame()

    if nivel == "group":
        if not groups_path.exists():
            return pd.DataFrame()
        sql = f"""
            SELECT g.name AS entidad,
                   SUM(s.sales) AS ventas,
                   SUM(s.prize) AS premios,
                   ROUND((SUM(s.sales)-SUM(s.prize))/NULLIF(SUM(s.sales),0)*100,2) AS pct_margen,
                   COUNT(DISTINCT s.agency_id) AS agencias,
                   ROUND(SUM(s.sales)*100.0/SUM(SUM(s.sales)) OVER(),2) AS concentracion_pct
            FROM '{sales_path}' s
            LEFT JOIN '{agencys_path}' a ON s.agency_id = a.id
            LEFT JOIN '{groups_path}' g ON a.group_id = g.id
            WHERE s.sales > 0 AND g.name IS NOT NULL
            GROUP BY g.name
            ORDER BY ventas DESC
            LIMIT {n}
        """
    elif nivel == "center":
        if not groups_path.exists() or not centers_path.exists():
            return pd.DataFrame()
        sql = f"""
            SELECT c.name AS entidad,
                   SUM(s.sales) AS ventas,
                   SUM(s.prize) AS premios,
                   ROUND((SUM(s.sales)-SUM(s.prize))/NULLIF(SUM(s.sales),0)*100,2) AS pct_margen,
                   COUNT(DISTINCT s.agency_id) AS agencias,
                   ROUND(SUM(s.sales)*100.0/SUM(SUM(s.sales)) OVER(),2) AS concentracion_pct
            FROM '{sales_path}' s
            LEFT JOIN '{agencys_path}' a ON s.agency_id = a.id
            LEFT JOIN '{groups_path}' g ON a.group_id = g.id
            LEFT JOIN '{centers_path}' c ON g.center_id = c.id
            WHERE s.sales > 0 AND c.name IS NOT NULL
            GROUP BY c.name
            ORDER BY ventas DESC
            LIMIT {n}
        """
    elif nivel in ("master_center", "master"):
        if not groups_path.exists() or not centers_path.exists() or not master_centers_path.exists():
            return pd.DataFrame()
        sql = f"""
            SELECT mc.name AS entidad,
                   SUM(s.sales) AS ventas,
                   SUM(s.prize) AS premios,
                   ROUND((SUM(s.sales)-SUM(s.prize))/NULLIF(SUM(s.sales),0)*100,2) AS pct_margen,
                   COUNT(DISTINCT s.agency_id) AS agencias,
                   ROUND(SUM(s.sales)*100.0/SUM(SUM(s.sales)) OVER(),2) AS concentracion_pct
            FROM '{sales_path}' s
            LEFT JOIN '{agencys_path}' a ON s.agency_id = a.id
            LEFT JOIN '{groups_path}' g ON a.group_id = g.id
            LEFT JOIN '{centers_path}' c ON g.center_id = c.id
            LEFT JOIN '{master_centers_path}' mc ON c.master_center_id = mc.id
            WHERE s.sales > 0 AND mc.name IS NOT NULL
            GROUP BY mc.name
            ORDER BY ventas DESC
            LIMIT {n}
        """
    else:
        raise ValueError("nivel debe ser 'group', 'center' o 'master_center'")

    with _conn() as conn:
        return conn.execute(sql).df()


def tendencia_productos(reciente_dias: int = 30, previo_dias: int = 30, n: int = 10) -> pd.DataFrame:
    """Compara ventas recientes vs previas por producto."""
    sales_path = DATA_DIR / "aggregated" / "sales_by_agency.parquet"
    products_path = DATA_DIR / "dimensions" / "new_products.parquet"
    if not sales_path.exists():
        return pd.DataFrame()

    sql = f"""
    WITH params AS (SELECT MAX(fecha) AS max_f FROM '{sales_path}'),
         reciente AS (
             SELECT new_product_id, SUM(sales) AS ventas
             FROM '{sales_path}', params
             WHERE fecha >= max_f - INTERVAL '{reciente_dias} days'
             GROUP BY new_product_id
         ),
         previo AS (
             SELECT new_product_id, SUM(sales) AS ventas
             FROM '{sales_path}', params
             WHERE fecha >= max_f - INTERVAL '{reciente_dias + previo_dias} days'
               AND fecha < max_f - INTERVAL '{reciente_dias} days'
             GROUP BY new_product_id
         )
    SELECT p.name AS producto,
           COALESCE(r.ventas, 0) AS ventas_reciente,
           COALESCE(pr.ventas, 0) AS ventas_previo,
           ROUND((COALESCE(r.ventas, 0) - COALESCE(pr.ventas, 0))
                 / NULLIF(pr.ventas, 0) * 100, 2) AS cambio_pct,
           CASE
               WHEN COALESCE(r.ventas, 0) > COALESCE(pr.ventas, 0) * 1.05 THEN 'Creciendo'
               WHEN COALESCE(r.ventas, 0) < COALESCE(pr.ventas, 0) * 0.95 THEN 'Enfriándose'
               ELSE 'Estable'
           END AS tendencia
    FROM reciente r
    FULL OUTER JOIN previo pr ON r.new_product_id = pr.new_product_id
    LEFT JOIN '{products_path}' p ON COALESCE(r.new_product_id, pr.new_product_id) = p.id
    ORDER BY cambio_pct DESC
    LIMIT {n}
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def tendencia_sorteos(reciente_dias: int = 30, previo_dias: int = 30, n: int = 10) -> pd.DataFrame:
    """Compara ventas recientes vs previas por sorteo."""
    sales_path = DATA_DIR / "aggregated" / "sales_by_loteries.parquet"
    loteries_path = DATA_DIR / "dimensions" / "loteries.parquet"
    if not sales_path.exists():
        return pd.DataFrame()

    sql = f"""
    WITH params AS (SELECT MAX(fecha) AS max_f FROM '{sales_path}'),
         reciente AS (
             SELECT lotery_id, SUM(sales) AS ventas
             FROM '{sales_path}', params
             WHERE fecha >= max_f - INTERVAL '{reciente_dias} days'
             GROUP BY lotery_id
         ),
         previo AS (
             SELECT lotery_id, SUM(sales) AS ventas
             FROM '{sales_path}', params
             WHERE fecha >= max_f - INTERVAL '{reciente_dias + previo_dias} days'
               AND fecha < max_f - INTERVAL '{reciente_dias} days'
             GROUP BY lotery_id
         )
    SELECT l.name AS sorteo,
           l.lotery_hour AS hora,
           COALESCE(r.ventas, 0) AS ventas_reciente,
           COALESCE(pr.ventas, 0) AS ventas_previo,
           ROUND((COALESCE(r.ventas, 0) - COALESCE(pr.ventas, 0))
                 / NULLIF(pr.ventas, 0) * 100, 2) AS cambio_pct,
           CASE
               WHEN COALESCE(r.ventas, 0) > COALESCE(pr.ventas, 0) * 1.05 THEN 'Creciendo'
               WHEN COALESCE(r.ventas, 0) < COALESCE(pr.ventas, 0) * 0.95 THEN 'Enfriándose'
               ELSE 'Estable'
           END AS tendencia
    FROM reciente r
    FULL OUTER JOIN previo pr ON r.lotery_id = pr.lotery_id
    LEFT JOIN '{loteries_path}' l ON COALESCE(r.lotery_id, pr.lotery_id) = l.id
    ORDER BY cambio_pct DESC
    LIMIT {n}
    """
    with _conn() as conn:
        return conn.execute(sql).df()


def tickets_anulados_detalle(rango_dias: int = 7) -> pd.DataFrame:
    """Detalle de tickets anulados recientes con apuestas asociadas si están disponibles."""
    tickets_pattern = DATA_DIR / "facts" / "tickets_*.parquet"
    bets_pattern = DATA_DIR / "facts" / "bets_*.parquet"
    agencys_path = DATA_DIR / "dimensions" / "agencys.parquet"
    loteries_path = DATA_DIR / "dimensions" / "loteries.parquet"
    products_path = DATA_DIR / "dimensions" / "new_products.parquet"

    has_tickets = bool(list(DATA_DIR.glob("facts/tickets_*.parquet")))
    if not has_tickets:
        return pd.DataFrame()

    has_bets = bool(list(DATA_DIR.glob("facts/bets_*.parquet")))
    has_details = has_bets and loteries_path.exists() and products_path.exists()

    if has_details:
        sql = f"""
        WITH params AS (SELECT MAX(CAST(created AS DATE)) AS max_d FROM '{tickets_pattern}'),
             ta AS (
                 SELECT t.id AS ticket_id, t.created, t.agency_id, t.total_amount, t.anull_role
                 FROM '{tickets_pattern}' t, params
                 WHERE t.anull_date IS NOT NULL
                   AND CAST(t.created AS DATE) >= max_d - INTERVAL '{rango_dias} days'
                 LIMIT 5000
             )
        SELECT
            ta.ticket_id,
            ta.created,
            a.name AS agencia,
            ta.total_amount,
            ta.anull_role,
            l.name AS sorteo,
            np.name AS producto,
            b.number,
            b.amount AS bet_amount
        FROM ta
        LEFT JOIN '{agencys_path}' a ON ta.agency_id = a.id
        LEFT JOIN '{bets_pattern}' b ON ta.ticket_id = b.ticket_id
        LEFT JOIN '{loteries_path}' l ON b.lotery_id = l.id
        LEFT JOIN '{products_path}' np ON l.product_new = np.id
        ORDER BY ta.created DESC
        LIMIT 1000
        """
    else:
        sql = f"""
        WITH params AS (SELECT MAX(CAST(created AS DATE)) AS max_d FROM '{tickets_pattern}')
        SELECT
            t.id AS ticket_id,
            t.created,
            a.name AS agencia,
            t.total_amount,
            t.anull_role
        FROM '{tickets_pattern}' t, params
        WHERE t.anull_date IS NOT NULL
          AND CAST(t.created AS DATE) >= max_d - INTERVAL '{rango_dias} days'
        LEFT JOIN '{agencys_path}' a ON t.agency_id = a.id
        ORDER BY t.created DESC
        LIMIT 1000
        """
    with _conn() as conn:
        return conn.execute(sql).df()
