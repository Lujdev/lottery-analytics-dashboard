"""Feature engineering: constructores de datasets para cada capability.

Todas las funciones son puras sobre los parquets de entrada y devuelven
pandas DataFrames listos para entrenar/scorear. No entrenan modelos.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import duckdb
import pandas as pd

from ml.config import DATA_DIR
from ml.io import load_sales_by_agency

logger = logging.getLogger(__name__)


def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def _max_date_sales() -> pd.Timestamp:
    """Fecha máxima disponible en sales_by_agencia."""
    df = load_sales_by_agency()
    if df.empty or "fecha" not in df.columns:
        return pd.Timestamp.now().normalize()
    return pd.to_datetime(df["fecha"]).max()


# ── 2.2 Features por agencia ────────────────────────────────────────────────

def build_agency_features(window_days: int = 90) -> pd.DataFrame:
    """Dataset de features agregadas por agencia sobre ventana corriente.

    Origen: sales_by_agency + tickets + new_products.
    """
    cutoff = _max_date_sales() - timedelta(days=window_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    sales_path = DATA_DIR / "aggregated" / "sales_by_agency.parquet"
    tickets_pattern = DATA_DIR / "facts" / "tickets_*.parquet"
    products_path = DATA_DIR / "dimensions" / "new_products.parquet"

    # Si no hay tickets en disco, omitir ticket_agg para no romper DuckDB
    has_tickets = bool(list(DATA_DIR.glob("facts/tickets_*.parquet")))
    ticket_sql = f"""
        SELECT
            agency_id,
            COUNT(*)                                                 AS total_tickets,
            AVG(total_amount)                                        AS ticket_avg_amount,
            AVG(cant_bets)                                           AS bets_per_ticket,
            COUNT(*) FILTER (WHERE anull_date IS NOT NULL)
                * 100.0 / NULLIF(COUNT(*), 0)                        AS pct_anulacion
        FROM '{tickets_pattern}'
        WHERE created >= TIMESTAMP '{cutoff_str} 00:00:00'
        GROUP BY agency_id
    """ if has_tickets else "SELECT NULL::INTEGER AS agency_id, 0 AS total_tickets, 0.0 AS ticket_avg_amount, 0.0 AS bets_per_ticket, 0.0 AS pct_anulacion WHERE 1=0"

    sql = f"""
    WITH sales_agg AS (
        SELECT
            agency_id,
            SUM(sales)                                               AS total_sales,
            SUM(prize)                                               AS total_prize,
            COUNT(DISTINCT fecha)                                    AS days_active,
            COUNT(DISTINCT new_product_id)                           AS unique_products,
            AVG(comision)                                            AS avg_comision,
            AVG(utilidad)                                            AS avg_utilidad,
            AVG( (sales - prize) / NULLIF(sales, 0) * 100 )          AS avg_margin_pct,
            STDDEV(sales)                                            AS sales_volatility,
            SUM(sales) / NULLIF(COUNT(DISTINCT fecha), 0)            AS avg_daily_sales
        FROM '{sales_path}'
        WHERE fecha >= DATE '{cutoff_str}'
        GROUP BY agency_id
    ),
    ticket_agg AS ({ticket_sql}),
    product_mix AS (
        SELECT
            s.agency_id,
            p.product_type_id,
            SUM(s.sales)                                             AS type_sales
        FROM '{sales_path}' s
        LEFT JOIN '{products_path}' p
            ON s.new_product_id = p.id
        WHERE s.fecha >= DATE '{cutoff_str}'
        GROUP BY s.agency_id, p.product_type_id
    ),
    product_mix_pivot AS (
        SELECT
            agency_id,
            SUM(CASE WHEN product_type_id = 1 THEN type_sales ELSE 0 END)
                / NULLIF(SUM(type_sales), 0)                         AS product_mix_animalitos_pct,
            SUM(CASE WHEN product_type_id = 2 THEN type_sales ELSE 0 END)
                / NULLIF(SUM(type_sales), 0)                         AS product_mix_triples_pct,
            SUM(CASE WHEN product_type_id = 3 THEN type_sales ELSE 0 END)
                / NULLIF(SUM(type_sales), 0)                         AS product_mix_terminales_pct,
            SUM(CASE WHEN product_type_id = 4 THEN type_sales ELSE 0 END)
                / NULLIF(SUM(type_sales), 0)                         AS product_mix_tripletas_pct,
            SUM(CASE WHEN product_type_id = 5 THEN type_sales ELSE 0 END)
                / NULLIF(SUM(type_sales), 0)                         AS product_mix_centenas_pct
        FROM product_mix
        GROUP BY agency_id
    )
    SELECT
        s.*,
        t.total_tickets,
        t.ticket_avg_amount,
        t.bets_per_ticket,
        t.pct_anulacion,
        pm.product_mix_animalitos_pct,
        pm.product_mix_triples_pct,
        pm.product_mix_terminales_pct,
        pm.product_mix_tripletas_pct,
        pm.product_mix_centenas_pct
    FROM sales_agg s
    LEFT JOIN ticket_agg t ON s.agency_id = t.agency_id
    LEFT JOIN product_mix_pivot pm ON s.agency_id = pm.agency_id
    ORDER BY s.agency_id
    """
    with _conn() as conn:
        df = conn.execute(sql).df()

    logger.info("Agency features: %d agencias, %d columnas.", len(df), len(df.columns))
    return df


# ── 2.3 Serie temporal para forecasting ─────────────────────────────────────

def build_forecast_series(entity_type: str = "national", top_n_agencies: int = 50) -> pd.DataFrame:
    """Series mensuales de ventas listas para forecasting.

    entity_type: 'national' | 'agency'
    """
    sales_path = DATA_DIR / "aggregated" / "sales_by_agency.parquet"

    if entity_type == "national":
        sql = f"""
        SELECT
            DATE_TRUNC('month', fecha) AS mes,
            SUM(sales) AS y,
            SUM(prize) AS prize,
            COUNT(DISTINCT agency_id) AS active_agencies,
            COUNT(DISTINCT new_product_id) AS unique_products
        FROM '{sales_path}'
        GROUP BY 1
        ORDER BY 1
        """
        with _conn() as conn:
            df = conn.execute(sql).df()
        df["entity_type"] = "national"
        df["entity_id"] = 0
    elif entity_type == "agency":
        sql_top = f"""
        SELECT agency_id, SUM(sales) AS total
        FROM '{sales_path}'
        GROUP BY agency_id
        ORDER BY total DESC
        LIMIT {top_n_agencies}
        """
        with _conn() as conn:
            top = conn.execute(sql_top).df()
        if top.empty:
            return pd.DataFrame(columns=["mes", "y", "entity_type", "entity_id"])
        top_ids = ",".join(str(int(x)) for x in top["agency_id"])
        sql = f"""
        SELECT
            DATE_TRUNC('month', fecha) AS mes,
            agency_id AS entity_id,
            SUM(sales) AS y,
            SUM(prize) AS prize,
            COUNT(DISTINCT new_product_id) AS unique_products
        FROM '{sales_path}'
        WHERE agency_id IN ({top_ids})
        GROUP BY 1, 2
        ORDER BY 2, 1
        """
        with _conn() as conn:
            df = conn.execute(sql).df()
        df["entity_type"] = "agency"
    else:
        raise ValueError(f"entity_type no soportado: {entity_type}")

    # Detectar y excluir mes parcial (último mes con datos incompletos)
    df["mes"] = pd.to_datetime(df["mes"])
    if not df.empty:
        max_date = _max_date_sales()
        last_month = df["mes"].max()
        if (
            max_date.year == last_month.year
            and max_date.month == last_month.month
            and max_date.day < 25
        ):
            df = df[df["mes"] < last_month].copy()
            logger.info(
                "Forecast series (%s): excluyendo mes parcial %s (máx fecha en datos: %s)",
                entity_type,
                last_month.strftime("%Y-%m"),
                max_date.strftime("%Y-%m-%d"),
            )

    # Normalizar frecuencia mensual: rellenar huecos con 0
    all_months = pd.date_range(df["mes"].min(), df["mes"].max(), freq="MS")

    if entity_type == "national":
        df = df.set_index("mes").reindex(all_months, fill_value=0).reset_index()
        df = df.rename(columns={"index": "mes"})
        df["entity_type"] = "national"
        df["entity_id"] = 0
    else:
        filled = []
        for eid, g in df.groupby("entity_id"):
            g = g.set_index("mes").reindex(all_months).reset_index()
            g = g.rename(columns={"index": "mes"})
            g["entity_type"] = "agency"
            g["entity_id"] = int(eid)
            for num_col in ("y", "prize", "unique_products"):
                if num_col in g.columns:
                    g[num_col] = g[num_col].fillna(0)
            filled.append(g)
        df = pd.concat(filled, ignore_index=True) if filled else pd.DataFrame()

    logger.info("Forecast series (%s): %d registros.", entity_type, len(df))
    return df


# ── 2.4 Dataset etiquetado para churn ───────────────────────────────────────

def build_churn_dataset(observation_days: int = 90, churn_days: int = 30) -> pd.DataFrame:
    """Dataset con label de churn operativo para clasificación.

    Label = 1 si la agencia no tuvo sales > 0 en los últimos `churn_days`
    días previos al corte (máxima fecha disponible).
    Features = ventanas 30d/60d/90d previas al corte.

    ADVERTENCIA: cuando churn_days=30, monetary_30d y el label comparten
    la misma ventana temporal, produciendo data leakage. Esto se documenta
    como limitación conocida; no afecta el scoring batch pero infla métricas
    de holdout. Para entrenamiento robusto, excluir monetary_30d/frequency_30d
    o aumentar churn_days con ventanas desfasadas.
    """
    cutoff = _max_date_sales()
    churn_cutoff = (cutoff - timedelta(days=churn_days)).strftime("%Y-%m-%d")
    obs_start = (cutoff - timedelta(days=observation_days)).strftime("%Y-%m-%d")
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    sales_path = DATA_DIR / "aggregated" / "sales_by_agency.parquet"
    tickets_path = DATA_DIR / "facts" / "tickets_*.parquet"

    sql_label = f"""
    SELECT DISTINCT agency_id
    FROM '{sales_path}'
    WHERE fecha > DATE '{churn_cutoff}' AND fecha <= DATE '{cutoff_str}' AND sales > 0
    """
    with _conn() as conn:
        active = conn.execute(sql_label).df()["agency_id"].tolist()

    has_tickets = bool(list(DATA_DIR.glob("facts/tickets_*.parquet")))
    ticket_window_sql = f"""
        SELECT
            agency_id,
            COUNT(*) AS total_tickets_90d,
            COUNT(*) FILTER (WHERE anull_date IS NOT NULL)
                * 100.0 / NULLIF(COUNT(*), 0) AS pct_anulacion_90d,
            AVG(total_amount) AS ticket_avg_90d,
            AVG(cant_bets) AS bets_per_ticket_90d
        FROM '{tickets_path}'
        WHERE created > TIMESTAMP '{obs_start} 00:00:00' AND created <= TIMESTAMP '{cutoff_str} 23:59:59'
        GROUP BY agency_id
    """ if has_tickets else "SELECT NULL::INTEGER AS agency_id, 0 AS total_tickets_90d, 0.0 AS pct_anulacion_90d, 0.0 AS ticket_avg_90d, 0.0 AS bets_per_ticket_90d WHERE 1=0"

    sql_features = f"""
    WITH sales_window AS (
        SELECT
            agency_id,
            SUM(sales) AS monetary_90d,
            COUNT(DISTINCT fecha) AS frequency_90d,
            MAX(fecha) AS last_sale_date,
            STDDEV(sales) AS sales_std_90d,
            SUM(CASE WHEN fecha > DATE '{cutoff_str}' - INTERVAL '30 days' THEN sales ELSE 0 END) AS monetary_30d,
            COUNT(DISTINCT CASE WHEN fecha > DATE '{cutoff_str}' - INTERVAL '30 days' THEN fecha END) AS frequency_30d,
            SUM(CASE WHEN fecha > DATE '{cutoff_str}' - INTERVAL '60 days' AND fecha <= DATE '{cutoff_str}' - INTERVAL '30 days' THEN sales ELSE 0 END) AS monetary_60_30d
        FROM '{sales_path}'
        WHERE fecha > DATE '{obs_start}' AND fecha <= DATE '{cutoff_str}'
        GROUP BY agency_id
    ),
    ticket_window AS ({ticket_window_sql})
    SELECT
        s.*,
        t.total_tickets_90d,
        t.pct_anulacion_90d,
        t.ticket_avg_90d,
        t.bets_per_ticket_90d
    FROM sales_window s
    LEFT JOIN ticket_window t ON s.agency_id = t.agency_id
    """
    with _conn() as conn:
        df = conn.execute(sql_features).df()

    all_agencies = set(df["agency_id"].unique())
    churned = all_agencies - set(active)
    df["churn_label"] = df["agency_id"].isin(churned).astype(int)
    df["recency_30d"] = (pd.to_datetime(cutoff) - pd.to_datetime(df["last_sale_date"])).dt.days
    df["sales_decline_60d"] = (df["monetary_30d"] - df["monetary_60_30d"]) / df["monetary_60_30d"].replace(0, pd.NA)

    sql_currency = f"""
    SELECT agency_id, currency_id, SUM(sales) AS s
    FROM '{sales_path}'
    WHERE fecha > DATE '{obs_start}' AND fecha <= DATE '{cutoff_str}'
    GROUP BY agency_id, currency_id
    """
    with _conn() as conn:
        curr = conn.execute(sql_currency).df()
    if not curr.empty:
        curr_sum = curr.groupby("agency_id")["s"].sum().reset_index(name="total")
        curr_max = curr.groupby("agency_id")["s"].max().reset_index(name="max_c")
        curr_merged = curr_max.merge(curr_sum, on="agency_id")
        curr_merged["currency_concentration"] = curr_merged["max_c"] / curr_merged["total"]
        df = df.merge(curr_merged[["agency_id", "currency_concentration"]], on="agency_id", how="left")
    else:
        df["currency_concentration"] = pd.NA

    logger.info("Churn dataset: %d agencias (churn=%d).", len(df), df["churn_label"].sum())
    return df


# ── 2.5 Dataset transaccional para market basket ────────────────────────────

def build_basket_transactions(min_items: int = 2) -> pd.DataFrame:
    """Transacciones por ticket_id con items (new_product_id) para basket analysis.

    Origen: bets JOIN loteries para obtener product_new.
    Filtra tickets con < min_items productos distintos.
    """
    bets_pattern = DATA_DIR / "facts" / "bets_*.parquet"
    loteries_path = DATA_DIR / "dimensions" / "loteries.parquet"

    has_bets = bool(list(DATA_DIR.glob("facts/bets_*.parquet")))
    if not has_bets:
        logger.warning("Basket transactions: no hay archivos bets_*.parquet.")
        return pd.DataFrame(columns=["ticket_id", "item_id"])

    sql = f"""
    SELECT
        b.ticket_id,
        l.product_new AS item_id
    FROM '{bets_pattern}' b
    LEFT JOIN '{loteries_path}' l ON b.lotery_id = l.id
    WHERE l.product_new IS NOT NULL
    """
    with _conn() as conn:
        df = conn.execute(sql).df()

    if df.empty:
        logger.warning("Basket transactions: dataset vacío.")
        return pd.DataFrame(columns=["ticket_id", "item_id"])

    # Filtrar tickets con suficientes items distintos
    ticket_counts = df.groupby("ticket_id")["item_id"].nunique().reset_index(name="n_items")
    valid_tickets = ticket_counts[ticket_counts["n_items"] >= min_items]["ticket_id"]
    df = df[df["ticket_id"].isin(valid_tickets)].copy()

    logger.info("Basket transactions: %d tickets válidos, %d filas.", valid_tickets.nunique(), len(df))
    return df
