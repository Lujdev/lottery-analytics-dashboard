import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.auth import require_auth
from dashboard.data import (
    anulaciones_por_mes,
    top_agencias_anulacion,
    anulaciones_por_rol,
    kpis_anulaciones,
)

st.set_page_config(page_title="Anomalías y Anulaciones", layout="wide")

require_auth()

st.title("🔍 Anomalías y Anulaciones")
st.caption("Análisis de patrones de anulación de tickets. Tasas inusualmente altas pueden indicar fraude o problemas operativos.")

# KPIs
kpis = kpis_anulaciones()

k1, k2, k3 = st.columns(3)
k1.metric("Total tickets", f"{kpis['total_tickets']:,}")
k2.metric("Tickets anulados", f"{kpis['anulados']:,}")
k3.metric(
    "% Anulación global",
    f"{kpis['pct_anulacion']:.1f}%",
    delta=f"{'⚠️ Alto' if kpis['pct_anulacion'] > 15 else 'Normal'}",
    delta_color="inverse" if kpis['pct_anulacion'] > 15 else "normal",
)

st.divider()

col1, col2 = st.columns(2)

# Tendencia mensual
with col1:
    st.subheader("Tasa de anulación por mes")
    df_mes = anulaciones_por_mes()
    df_mes["mes"] = df_mes["mes"].astype(str)

    fig = go.Figure()
    fig.add_bar(x=df_mes["mes"], y=df_mes["total_tickets"], name="Total", marker_color="#4C9BE8")
    fig.add_bar(x=df_mes["mes"], y=df_mes["anulados"], name="Anulados", marker_color="#E8684C")
    fig.update_layout(barmode="overlay", xaxis_title="Mes", yaxis_title="Tickets")
    st.plotly_chart(fig, use_container_width=True)

# % anulación por mes
with col2:
    st.subheader("% Anulación mensual")
    fig2 = px.line(
        df_mes, x="mes", y="pct_anulacion",
        markers=True,
        labels={"pct_anulacion": "% Anulación", "mes": "Mes"},
        color_discrete_sequence=["#E8684C"],
    )
    fig2.add_hline(y=15, line_dash="dash", line_color="yellow",
                   annotation_text="Umbral alerta 15%")
    fig2.update_layout(yaxis_range=[0, 50])
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

col3, col4 = st.columns(2)

# Top agencias con más anulaciones
with col3:
    st.subheader("Top 25 agencias por % anulación")
    st.caption("Solo agencias con más de 100 tickets.")
    df_ag = top_agencias_anulacion(25)
    fig3 = px.bar(
        df_ag, x="pct_anulacion", y="agencia", orientation="h",
        color="pct_anulacion",
        color_continuous_scale="Reds",
        labels={"pct_anulacion": "% Anulación", "agencia": ""},
        hover_data=["total_tickets", "anulados"],
    )
    fig3.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig3, use_container_width=True)

# Anulaciones por rol
with col4:
    st.subheader("Anulaciones por rol")
    df_rol = anulaciones_por_rol()
    fig4 = px.pie(
        df_rol, values="anulaciones", names="rol",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig4.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# Tabla agencias sospechosas
st.subheader("Agencias sospechosas (% anulación > 30%)")
df_sospechosas = df_ag[df_ag["pct_anulacion"] > 30][
    ["agencia", "total_tickets", "anulados", "pct_anulacion"]
].rename(columns={
    "agencia": "Agencia",
    "total_tickets": "Total Tickets",
    "anulados": "Anulados",
    "pct_anulacion": "% Anulación",
})
if df_sospechosas.empty:
    st.success("No se detectaron agencias con % anulación > 30%")
else:
    st.dataframe(df_sospechosas, use_container_width=True, hide_index=True)
