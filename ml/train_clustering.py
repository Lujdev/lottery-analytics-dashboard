"""Pipeline de clustering de agencias: KMeans + PCA."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from ml.config import DEFAULT_K_CLUSTERS, MIN_AGENCIES_FOR_CLUSTERING, RUN_DATE, RUN_ID, parquet_path
from ml.features import build_agency_features
from ml.schemas import validate_schema, with_run_metadata

logger = logging.getLogger(__name__)


def train_clustering(
    output_path: Path | None = None,
    window_days: int = 90,
    n_clusters: int = DEFAULT_K_CLUSTERS,
) -> pd.DataFrame:
    """Entrena KMeans sobre features de agencia y proyecta PCA 2D.

    Returns DataFrame con schema agency_clusters.
    """
    output_path = output_path or parquet_path("agency_clusters")

    logger.info("Clustering: cargando features (window=%d días)...", window_days)
    df = build_agency_features(window_days=window_days)

    if len(df) < MIN_AGENCIES_FOR_CLUSTERING:
        logger.error(
            "Clustering abortado: %d agencias < mínimo %d.",
            len(df),
            MIN_AGENCIES_FOR_CLUSTERING,
        )
        # Devolver empty frame validado pero con metadata
        empty = pd.DataFrame(columns=[
            "agency_id", "cluster_id", "pca_x", "pca_y",
            "centroid_distance", "run_id", "run_date",
        ])
        empty = with_run_metadata(empty, RUN_ID, RUN_DATE)
        validate_schema(empty, "agency_clusters")
        return empty

    feature_cols = [c for c in df.columns if c != "agency_id"]
    X = df[feature_cols].fillna(0).values

    logger.info("Clustering: escalando %d agencias × %d features...", X.shape[0], X.shape[1])
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    k = min(n_clusters, len(df) - 1)
    logger.info("Clustering: entrenando KMeans(k=%d)...", k)
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_scaled)

    logger.info("Clustering: proyectando PCA(2)...")
    pca = PCA(n_components=2)
    X_pca = pca.fit_transform(X_scaled)

    # Distancia al centroide del cluster asignado
    centroid_dist = np.linalg.norm(X_scaled - kmeans.cluster_centers_[labels], axis=1)

    result = pd.DataFrame({
        "agency_id": df["agency_id"].astype(int),
        "cluster_id": labels.astype(int),
        "pca_x": X_pca[:, 0],
        "pca_y": X_pca[:, 1],
        "centroid_distance": centroid_dist,
    })

    result = with_run_metadata(result, RUN_ID, RUN_DATE)
    validate_schema(result, "agency_clusters")

    result.to_parquet(output_path, index=False)
    logger.info("Clustering: escrito %s (%d filas).", output_path, len(result))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    train_clustering()
