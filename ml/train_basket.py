"""Pipeline de market basket analysis: FP-Growth + association rules."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ml.config import (
    DEFAULT_BASKET_MIN_CONFIDENCE,
    DEFAULT_BASKET_MIN_LIFT,
    DEFAULT_BASKET_MIN_SUPPORT,
    RUN_DATE,
    RUN_ID,
    parquet_path,
)
from ml.features import build_basket_transactions
from ml.schemas import validate_schema, with_run_metadata

logger = logging.getLogger(__name__)


def train_basket(
    output_path: Path | None = None,
    min_support: float = DEFAULT_BASKET_MIN_SUPPORT,
    min_confidence: float = DEFAULT_BASKET_MIN_CONFIDENCE,
    min_lift: float = DEFAULT_BASKET_MIN_LIFT,
    min_items: int = 2,
) -> pd.DataFrame:
    """Descubre reglas de asociación con FP-Growth.

    Returns DataFrame con schema basket_rules.
    """
    output_path = output_path or parquet_path("basket_rules")

    logger.info("Basket: cargando transacciones (min_items=%d)...", min_items)
    df = build_basket_transactions(min_items=min_items)

    if df.empty or df["ticket_id"].nunique() < 100:
        logger.error("Basket: transacciones insuficientes.")
        empty = pd.DataFrame(columns=[
            "antecedent", "consequent", "support", "confidence",
            "lift", "period", "run_id",
        ])
        empty = with_run_metadata(empty, RUN_ID, RUN_DATE)
        validate_schema(empty, "basket_rules")
        return empty

    # One-hot encoding por ticket_id
    logger.info("Basket: armando matriz one-hot (%d tickets)...", df["ticket_id"].nunique())
    basket = df.groupby(["ticket_id", "item_id"]).size().unstack(fill_value=0)
    basket = (basket > 0).astype(bool)

    # FP-Growth
    from mlxtend.frequent_patterns import fpgrowth, association_rules

    logger.info("Basket: corriendo FP-Growth (min_support=%.4f)...", min_support)
    frequent = fpgrowth(basket, min_support=min_support, use_colnames=True)

    if frequent.empty:
        logger.warning("Basket: FP-Growth no encontró itemsets frecuentes.")
        empty = pd.DataFrame(columns=[
            "antecedent", "consequent", "support", "confidence",
            "lift", "period", "run_id",
        ])
        empty = with_run_metadata(empty, RUN_ID, RUN_DATE)
        validate_schema(empty, "basket_rules")
        return empty

    logger.info("Basket: generando association_rules (min_confidence=%.2f)...", min_confidence)
    rules = association_rules(frequent, metric="confidence", min_threshold=min_confidence)
    rules = rules[rules["lift"] >= min_lift].copy()

    if rules.empty:
        logger.warning("Basket: ninguna regla cumple thresholds.")
        empty = pd.DataFrame(columns=[
            "antecedent", "consequent", "support", "confidence",
            "lift", "period", "run_id",
        ])
        empty = with_run_metadata(empty, RUN_ID, RUN_DATE)
        validate_schema(empty, "basket_rules")
        return empty

    # Convertir frozensets a strings legibles
    def _fmt_itemset(fset):
        return ",".join(sorted(str(x) for x in fset))

    result = pd.DataFrame({
        "antecedent": rules["antecedents"].apply(_fmt_itemset),
        "consequent": rules["consequents"].apply(_fmt_itemset),
        "support": rules["support"],
        "confidence": rules["confidence"],
        "lift": rules["lift"],
        "period": pd.to_datetime(RUN_DATE).replace(day=1),
    })

    result = with_run_metadata(result, RUN_ID, RUN_DATE)
    validate_schema(result, "basket_rules")

    result.to_parquet(output_path, index=False)
    logger.info("Basket: escrito %s (%d reglas).", output_path, len(result))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    train_basket()
