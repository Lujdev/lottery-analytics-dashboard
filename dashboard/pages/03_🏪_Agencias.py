import streamlit as st
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.auth import require_auth
from dashboard.data import (
    health_score_agencias, health_score_agencias_unificado,
    distribucion_agencias, distribucion_agencias_unificado,
    MONEDAS,
)
from dashboard.utils import fmt_money
from dashboard.rates import get_rates_to_ves, rates_display

st.set_page_config(page_title="Segmentación de Agencias", layout="wide")

require_auth()

st.title("🏪 Segmentación de Agencias")
st.caption("Health score y distribución de las 5,474 agencias activas.")

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
    with st.spinner("Calculando health scores..."):
        df = health_score_agencias_unificado(rates)
        df_scatter = distribucion_agencias_unificado(rates)
else:
    with st.spinner("Calculando health scores..."):
        df = health_score_agencias(currency_id)
        df_scatter = distribucion_agencias(currency_id)

# KPIs rápidos
k1, k2, k3, k4 = st.columns(4)
k1.metric("Agencias analizadas", f"{len(df):,}")
k2.metric("Health score promedio", f"{df['health_score'].mean():.1f} / 100")
k3.metric("Agencias saludables (≥60)", f"{len(df[df['health_score'] >= 60]):,}")
k4.metric("Agencias en riesgo (<30)", f"{len(df[df['health_score'] < 30]):,}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Distribución de Health Score")
    fig = px.histogram(
        df, x="health_score", nbins=20,
        color_discrete_sequence=["#4C9BE8"],
        labels={"health_score": "Health Score", "count": "Agencias"},
    )
    fig.add_vline(x=60, line_dash="dash", line_color="#2ECC71", annotation_text="Saludable")
    fig.add_vline(x=30, line_dash="dash", line_color="#E8684C", annotation_text="En riesgo")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Ventas vs % Margen por agencia")
    st.caption("Tamaño = días activos. Hover para ver el nombre.")
    fig2 = px.scatter(
        df_scatter,
        x="ventas", y="pct_margen",
        size="dias_activos", size_max=20,
        hover_name="agencia",
        labels={"ventas": f"Ventas ({sym})", "pct_margen": "% Margen", "dias_activos": "Días activos"},
        color="pct_margen",
        color_continuous_scale="RdYlGn",
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

col3, col4 = st.columns(2)

with col3:
    st.subheader("Top 20 — Mayor Health Score")
    top = df.head(20)[["agencia", "health_score", "ventas", "pct_margen", "dias_activos"]]
    fig3 = px.bar(
        top, x="health_score", y="agencia", orientation="h",
        color="health_score", color_continuous_scale="Greens",
        labels={"health_score": "Score", "agencia": ""},
    )
    fig3.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig3, use_container_width=True)

with col4:
    st.subheader("Top 20 — Menor Health Score")
    bottom = df.tail(20)[["agencia", "health_score", "ventas", "pct_margen", "pct_anulacion"]]
    fig4 = px.bar(
        bottom, x="health_score", y="agencia", orientation="h",
        color="health_score", color_continuous_scale="Reds_r",
        labels={"health_score": "Score", "agencia": ""},
    )
    fig4.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

st.subheader("Tabla completa de agencias")
search = st.text_input("Buscar agencia", placeholder="Escribí el nombre...")
df_show = df if not search else df[df["agencia"].str.contains(search, case=False, na=False)]

df_display = df_show[["agencia", "health_score", "ventas", "pct_margen", "dias_activos", "pct_anulacion", "total_tickets"]].copy()
df_display["ventas"] = df_display["ventas"].apply(lambda v: fmt_money(v, sym))
df_display.columns = ["Agencia", "Health Score", "Ventas", "% Margen", "Días Activos", "% Anulación", "Total Tickets"]
st.dataframe(df_display, use_container_width=True, hide_index=True)
