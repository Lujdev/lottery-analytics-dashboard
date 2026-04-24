import streamlit as st
import pandas as pd
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
    prediccion_anomalias, predicciones_disponibles,
)
from dashboard.llm import generate_anomaly_narrative, is_configured

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

# ── Anomalías ML ────────────────────────────────────────────────────────────
st.divider()
st.subheader("🤖 Detección de anomalías operativas (ML)")

preds_ok = predicciones_disponibles()
if not preds_ok["anomalies"]:
    st.info(
        "Modelo de detección de anomalías no disponible. "
        "Corré `python -m ml.run_all` para generar predicciones."
    )
else:
    df_anom = prediccion_anomalias()
    if df_anom.empty:
        st.warning("El archivo de anomalías existe pero está vacío.")
    else:
        st.caption(
            "Isolation Forest puntuando comportamiento multivariado por agencia. "
            "Score más negativo = más anómalo. Severidad: normal / warning / critical."
        )
        # Solo anómalos
        df_out = df_anom[df_anom["is_anomaly"] == True].copy()
        if df_out.empty:
            st.success("No se detectaron outliers en la última corrida.")
        else:
            # KPIs
            k1, k2, k3 = st.columns(3)
            k1.metric("Outliers detectados", f"{len(df_out):,}")
            k2.metric("Críticos", f"{len(df_out[df_out['severity'] == 'critical']):,}")
            k3.metric("Warnings", f"{len(df_out[df_out['severity'] == 'warning']):,}")

            col_a1, col_a2 = st.columns(2)
            with col_a1:
                st.subheader("Severidad de anomalías")
                sev_counts = df_out["severity"].value_counts().reset_index()
                sev_counts.columns = ["severity", "count"]
                fig_sev = px.bar(
                    sev_counts, x="severity", y="count",
                    color="severity",
                    color_discrete_map={
                        "normal": "#2ECC71",
                        "warning": "#F1C40F",
                        "critical": "#E8684C",
                    },
                    labels={"severity": "Severidad", "count": "Agencias"},
                )
                st.plotly_chart(fig_sev, use_container_width=True)

            with col_a2:
                st.subheader("Top 20 outliers por score")
                df_top = df_out.nsmallest(20, "anomaly_score")[
                    ["agency_id", "anomaly_score", "severity"]
                ].copy()
                df_top["anomaly_score"] = df_top["anomaly_score"].round(3)
                fig_top = px.bar(
                    df_top, x="anomaly_score", y="agency_id",
                    orientation="h",
                    color="severity",
                    color_discrete_map={
                        "normal": "#2ECC71",
                        "warning": "#F1C40F",
                        "critical": "#E8684C",
                    },
                    labels={"anomaly_score": "Score", "agency_id": "Agencia ID"},
                )
                fig_top.update_layout(yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig_top, use_container_width=True)

            st.subheader("Tabla de anomalías detectadas")
            df_show = df_out[["agency_id", "anomaly_score", "severity", "period"]].copy()
            df_show["period"] = pd.to_datetime(df_show["period"]).dt.strftime("%Y-%m")
            df_show.columns = ["Agencia ID", "Score", "Severidad", "Período"]
            st.dataframe(df_show.sort_values("Score"), use_container_width=True, hide_index=True)

            # ── Narrativa LLM por agencia ─────────────────────────────────────────
            st.divider()
            st.subheader("📝 Narrativa ejecutiva (LLM)")
            agency_options = df_out.nsmallest(50, "anomaly_score")["agency_id"].astype(int).tolist()
            selected_agency = st.selectbox(
                "Seleccioná una agencia outlier para generar explicación",
                options=agency_options,
                format_func=lambda x: f"Agencia {x}",
            )
            if st.button("Generar explicación ejecutiva", type="primary"):
                spinner_text = "Consultando al modelo..." if is_configured() else "Generando resumen offline..."
                with st.spinner(spinner_text):
                    narrative = generate_anomaly_narrative(int(selected_agency))
                st.markdown(narrative)
