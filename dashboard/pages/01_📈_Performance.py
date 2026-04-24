import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.auth import require_auth
from dashboard.data import (
    ventas_por_mes, ventas_por_mes_unificado,
    ventas_por_producto, top_agencias,
    kpis_globales, kpis_globales_unificado,
    prediccion_forecast, predicciones_disponibles,
    MONEDAS,
)
from dashboard.utils import fmt_money, fmt_table
from dashboard.rates import get_rates_to_ves, rates_display

st.set_page_config(page_title="Performance Comercial", layout="wide")

require_auth()

st.title("📈 Performance Comercial")

col_f1, _ = st.columns([1, 3])
with col_f1:
    moneda_label = st.selectbox("Moneda", ["Todas (en Bs.)"] + list(MONEDAS.values()), index=1)

is_unified = moneda_label == "Todas (en Bs.)"
currency_id = None if is_unified else next(k for k, v in MONEDAS.items() if v == moneda_label)
sym = "Bs." if is_unified else moneda_label

if is_unified:
    with st.spinner("Obteniendo tasas de cambio BCV..."):
        rates = get_rates_to_ves()
    if len(rates) == 1:
        st.warning("⚠️ No se pudo obtener tasas de cambio. Solo mostrando VES.")
    else:
        st.caption(f"Tasas actuales: {rates_display(rates)}")
    kpis = kpis_globales_unificado(rates)
    df_mes = ventas_por_mes_unificado(rates)
else:
    kpis = kpis_globales(currency_id)
    df_mes = ventas_por_mes(currency_id)
    df_mes["mes"] = df_mes["mes"].astype(str)

# KPIs
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric(f"Ventas totales ({sym})", fmt_money(kpis["ventas"], sym))
k2.metric(f"Premios pagados ({sym})", fmt_money(kpis["premios"], sym))
k3.metric(f"Margen bruto ({sym})", fmt_money(kpis["margen_bruto"], sym))
k4.metric("% Margen", f"{kpis['pct_margen']:.1f}%")
k5.metric("Agencias activas", f"{kpis['agencias_activas']:,}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Ventas vs Premios por mes")
    fig = go.Figure()
    fig.add_bar(x=df_mes["mes"], y=df_mes["ventas"], name="Ventas", marker_color="#4C9BE8")
    fig.add_bar(x=df_mes["mes"], y=df_mes["premios"], name="Premios", marker_color="#E8684C")
    fig.update_layout(barmode="group", xaxis_title="Mes", yaxis_title=f"Monto ({sym})")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Margen bruto mensual (%)")
    fig2 = px.line(
        df_mes, x="mes", y="pct_margen",
        markers=True, labels={"pct_margen": "% Margen", "mes": "Mes"},
        color_discrete_sequence=["#2ECC71"],
    )
    fig2.update_layout(yaxis_range=[0, 50])
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

df_prod = ventas_por_producto(currency_id).head(15)

col3, col4 = st.columns(2)

with col3:
    st.subheader("Top productos por ventas")
    fig3 = px.bar(
        df_prod, x="ventas", y="producto", orientation="h",
        color="pct_margen", color_continuous_scale="RdYlGn",
        labels={"ventas": "Ventas", "producto": "", "pct_margen": "% Margen"},
    )
    fig3.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig3, use_container_width=True)

with col4:
    st.subheader("Top 20 agencias")
    df_ag = top_agencias(20, currency_id)
    fig4 = px.bar(
        df_ag, x="ventas", y="agencia", orientation="h",
        labels={"ventas": "Ventas", "agencia": ""},
        color_discrete_sequence=["#4C9BE8"],
    )
    fig4.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── Forecast ────────────────────────────────────────────────────────────────
st.subheader("🔮 Pronóstico de ventas (ML)")

preds_ok = predicciones_disponibles()
if not preds_ok["forecast"]:
    st.info(
        "Modelo de forecasting no disponible. "
        "Corré `python -m ml.run_all` para generar predicciones."
    )
else:
    df_forecast = prediccion_forecast()
    if df_forecast.empty:
        st.warning("El archivo de forecast existe pero está vacío.")
    else:
        st.caption(
            "Proyección mensual generada por Prophet/SARIMAX con intervalo de confianza. "
            "Datos futuros: estimación puntual (línea) y banda de incertidumbre (sombreado)."
        )
        # Nacional
        df_nac = df_forecast[df_forecast["entity_type"] == "nacional"].copy()
        if not df_nac.empty:
            df_nac["forecast_date"] = pd.to_datetime(df_nac["forecast_date"]).astype(str)
            fig_fc = go.Figure()
            fig_fc.add_trace(
                go.Scatter(
                    x=df_nac["forecast_date"],
                    y=df_nac["yhat_upper"],
                    fill=None,
                    mode="lines",
                    line_color="rgba(76,155,232,0.2)",
                    showlegend=False,
                )
            )
            fig_fc.add_trace(
                go.Scatter(
                    x=df_nac["forecast_date"],
                    y=df_nac["yhat_lower"],
                    fill="tonexty",
                    mode="lines",
                    line_color="rgba(76,155,232,0.2)",
                    name="Intervalo 95%",
                )
            )
            fig_fc.add_trace(
                go.Scatter(
                    x=df_nac["forecast_date"],
                    y=df_nac["yhat"],
                    mode="lines+markers",
                    line_color="#4C9BE8",
                    name="Pronóstico",
                )
            )
            fig_fc.update_layout(
                xaxis_title="Mes",
                yaxis_title=f"Ventas estimadas ({sym})",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_fc, use_container_width=True)
        else:
            st.info("No hay pronóstico nacional disponible.")

st.divider()

st.subheader("Detalle por producto")
df_display = fmt_table(
    df_prod[["producto", "ventas", "premios", "margen_bruto", "pct_margen"]],
    money_cols=["ventas", "premios", "margen_bruto"],
    symbol=sym,
)
df_display.columns = ["Producto", "Ventas", "Premios", "Margen Bruto", "% Margen"]
st.dataframe(df_display, use_container_width=True, hide_index=True)
