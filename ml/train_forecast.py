"""Pipeline de forecasting: Prophet primario, SARIMAX fallback."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ml.config import (
    DEFAULT_FORECAST_HORIZON_MONTHS,
    MIN_MONTHS_FOR_FORECAST,
    RUN_DATE,
    RUN_ID,
    parquet_path,
)
from ml.features import build_forecast_series
from ml.schemas import validate_schema, with_run_metadata

logger = logging.getLogger(__name__)

# Intentar cargar Prophet; si falla, quedará None y usaremos SARIMAX.
try:
    from prophet import Prophet

    _PROPHET_AVAILABLE = True
except Exception as exc:
    logger.warning("Prophet no disponible (%s). Fallback a SARIMAX.", exc)
    _PROPHET_AVAILABLE = False

# SARIMAX siempre disponible (statsmodels)
from statsmodels.tsa.statespace.sarimax import SARIMAX


def _fit_prophet(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Forecast con Prophet. df debe tener 'ds' (fecha) y 'y' (valor).

    Devuelve SOLO el horizonte futuro (no las fechas históricas).
    """
    n = len(df)
    yearly_seasonality = n >= 12
    m = Prophet(yearly_seasonality=yearly_seasonality, daily_seasonality=False)
    m.fit(df[["ds", "y"]])
    future = m.make_future_dataframe(periods=horizon, freq="MS")
    forecast = m.predict(future)
    forecast = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]
    # Filtrar solo fechas futuras: posteriores al último dato histórico
    max_ds = df["ds"].max()
    forecast = forecast[forecast["ds"] > max_ds]
    return forecast


def _fit_sarimax(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Forecast con SARIMAX(1,1,1)(1,1,1,12) como fallback robusto.

    Si hay menos de 24 observaciones se omite la componente estacional
    porque no hay suficientes datos para estimarla."""
    y = df.set_index("ds")["y"]
    # Asegurar frecuencia mensual
    y = y.asfreq("MS").fillna(0)
    n = len(y)
    try:
        if n >= 24:
            model = SARIMAX(
                y,
                order=(1, 1, 1),
                seasonal_order=(1, 1, 1, 12),
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
        else:
            model = SARIMAX(
                y, order=(1, 1, 1), enforce_stationarity=False, enforce_invertibility=False
            )
        fitted = model.fit(disp=False)
    except Exception as exc:
        logger.warning("SARIMAX fit falló (%s); probando modelo simple ARIMA(1,1,1).", exc)
        model = SARIMAX(y, order=(1, 1, 1), enforce_stationarity=False, enforce_invertibility=False)
        fitted = model.fit(disp=False)

    pred = fitted.get_forecast(steps=horizon)
    conf = pred.conf_int(alpha=0.10)
    future_dates = pd.date_range(start=y.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")

    return pd.DataFrame({
        "ds": future_dates,
        "yhat": pred.predicted_mean.values,
        "yhat_lower": conf.iloc[:, 0].values,
        "yhat_upper": conf.iloc[:, 1].values,
    })


def _forecast_entity(
    entity_df: pd.DataFrame,
    horizon: int,
    entity_type: str,
    entity_id: int,
) -> pd.DataFrame | None:
    """Forecast para una entidad. Devuelve None si no hay datos suficientes."""
    df = entity_df.sort_values("mes").copy()
    df = df.rename(columns={"mes": "ds", "y": "y"})
    df["ds"] = pd.to_datetime(df["ds"])
    # Filtrar ds no nulo y y no negativo
    df = df.dropna(subset=["ds", "y"])
    df["y"] = df["y"].clip(lower=0)

    # Defense in depth: detectar mes parcial residual (outlier extremo en el último punto)
    if len(df) >= 4:
        last_y = df["y"].iloc[-1]
        recent_median = df["y"].iloc[-4:-1].median()
        if recent_median > 0 and last_y < recent_median * 0.1:
            logger.warning(
                "Forecast %s/%s: último mes %s es outlier extremo (%.0f vs mediana reciente %.0f); excluyendo.",
                entity_type, entity_id, df["ds"].iloc[-1].strftime("%Y-%m"),
                last_y, recent_median,
            )
            df = df.iloc[:-1].copy()

    if len(df) < MIN_MONTHS_FOR_FORECAST:
        logger.warning("Forecast omitido para %s/%s: %d meses < mínimo %d.", entity_type, entity_id, len(df), MIN_MONTHS_FOR_FORECAST)
        return None

    n_positive = (df["y"] > 0).sum()
    if n_positive < MIN_MONTHS_FOR_FORECAST:
        logger.warning("Forecast omitido para %s/%s: %d meses con ventas > 0 insuficientes.", entity_type, entity_id, n_positive)
        return None

    model_used = "prophet"
    try:
        if _PROPHET_AVAILABLE:
            forecast = _fit_prophet(df, horizon)
        else:
            raise ImportError("Prophet no disponible")
    except Exception as exc:
        logger.warning("Prophet falló para %s/%s (%s). Fallback SARIMAX.", entity_type, entity_id, exc)
        try:
            forecast = _fit_sarimax(df, horizon)
            model_used = "sarimax"
        except Exception as exc2:
            logger.error("SARIMAX también falló para %s/%s (%s). Omitiendo.", entity_type, entity_id, exc2)
            return None

    forecast["entity_type"] = entity_type
    forecast["entity_id"] = int(entity_id)
    forecast["forecast_date"] = forecast["ds"]
    forecast["model"] = model_used
    forecast = forecast.drop(columns=["ds"])
    # Clip lower a 0 para que no prediga ventas negativas
    for col in ("yhat", "yhat_lower", "yhat_upper"):
        forecast[col] = forecast[col].clip(lower=0)
    return forecast


def train_forecast(
    output_path: Path | None = None,
    horizon_months: int = DEFAULT_FORECAST_HORIZON_MONTHS,
    top_n_agencies: int = 50,
) -> pd.DataFrame:
    """Genera forecast nacional + top agencias.

    Returns DataFrame con schema forecast_sales.
    """
    output_path = output_path or parquet_path("forecast_sales")

    frames: list[pd.DataFrame] = []

    # Nacional
    logger.info("Forecast: serie nacional...")
    df_national = build_forecast_series(entity_type="national")
    if not df_national.empty:
        fc = _forecast_entity(df_national, horizon_months, "nacional", 0)
        if fc is not None:
            frames.append(fc)

    # Top agencias
    logger.info("Forecast: top %d agencias...", top_n_agencies)
    df_agency = build_forecast_series(entity_type="agency", top_n_agencies=top_n_agencies)
    if not df_agency.empty and "entity_id" in df_agency.columns:
        for eid, g in df_agency.groupby("entity_id"):
            fc = _forecast_entity(g, horizon_months, "agency", eid)
            if fc is not None:
                frames.append(fc)

    if not frames:
        logger.error("Forecast: no se generó ningún forecast.")
        empty = pd.DataFrame(columns=[
            "entity_type", "entity_id", "forecast_date", "yhat",
            "yhat_lower", "yhat_upper", "model", "run_id", "run_date",
        ])
        empty = with_run_metadata(empty, RUN_ID, RUN_DATE)
        validate_schema(empty, "forecast_sales")
        return empty

    result = pd.concat(frames, ignore_index=True)
    result = with_run_metadata(result, RUN_ID, RUN_DATE)
    validate_schema(result, "forecast_sales")

    result.to_parquet(output_path, index=False)
    logger.info("Forecast: escrito %s (%d filas).", output_path, len(result))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    train_forecast()
