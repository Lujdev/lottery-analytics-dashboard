"""Capa de acceso a datos via DuckDB sobre Parquet."""
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
