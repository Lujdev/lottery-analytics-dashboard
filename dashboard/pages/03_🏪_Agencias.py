import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.auth import require_auth
from dashboard.data import (
    health_score_agencias, health_score_agencias_unificado,
    distribucion_agencias, distribucion_agencias_unificado,
    prediccion_clusters, prediccion_churn, predicciones_disponibles,
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

# ── Clustering ML ───────────────────────────────────────────────────────────
st.divider()
st.subheader("🧬 Segmentación automática (KMeans + PCA)")

preds_ok = predicciones_disponibles()
if not preds_ok["clusters"]:
    st.info(
        "Modelo de clustering no disponible. "
        "Corré `python -m ml.run_all` para generar predicciones."
    )
else:
    df_clust = prediccion_clusters()
    if df_clust.empty:
        st.warning("El archivo de clusters existe pero está vacío.")
    else:
        st.caption(
            "Proyección 2D (PCA) de agencias activas segmentadas por comportamiento comercial. "
            "Cada punto es una agencia; el color indica el cluster asignado por KMeans."
        )
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            df_clust["cluster_label"] = df_clust["cluster_id"].astype(str)
            fig_cl = px.scatter(
                df_clust, x="pca_x", y="pca_y",
                color="cluster_label",
                hover_data=["agency_id", "centroid_distance"],
                labels={"pca_x": "Componente 1", "pca_y": "Componente 2", "cluster_label": "Cluster"},
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig_cl.update_traces(marker=dict(size=8, opacity=0.7))
            st.plotly_chart(fig_cl, use_container_width=True)

        with col_c2:
            st.subheader("Resumen por cluster")
            clust_summary = df_clust.groupby("cluster_id").agg(
                agencias=("agency_id", "count"),
                distancia_prom=("centroid_distance", "mean"),
            ).reset_index()
            clust_summary["distancia_prom"] = clust_summary["distancia_prom"].round(2)
            clust_summary["cluster_label"] = clust_summary["cluster_id"].astype(str)
            fig_cs = px.bar(
                clust_summary, x="cluster_id", y="agencias",
                color="cluster_label",
                labels={"cluster_id": "Cluster", "agencias": "Cantidad de agencias"},
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            st.plotly_chart(fig_cs, use_container_width=True)
            st.dataframe(
                clust_summary.rename(columns={
                    "cluster_id": "Cluster",
                    "agencias": "Agencias",
                    "distancia_prom": "Distancia promedio al centroide",
                }),
                use_container_width=True, hide_index=True,
            )

# ── Churn ML ────────────────────────────────────────────────────────────────
st.divider()
st.subheader("⚠️ Riesgo de abandono (Churn)")

if not preds_ok["churn"]:
    st.info(
        "Modelo de churn no disponible. "
        "Corré `python -m ml.run_all` para generar predicciones."
    )
else:
    df_churn = prediccion_churn()
    if df_churn.empty:
        st.warning("El archivo de churn existe pero está vacío.")
    else:
        st.caption(
            "Random Forest estima la probabilidad de que una agencia deje de vender en los próximos 30 días. "
            "Banda 'alto' = priorizar contacto comercial."
        )
        banda = st.selectbox(
            "Filtrar por banda de riesgo",
            ["Todas", "alto", "medio", "bajo"],
            index=0,
        )
        df_ch_filt = df_churn if banda == "Todas" else df_churn[df_churn["risk_band"] == banda]

        k1, k2, k3 = st.columns(3)
        k1.metric("Agencias scored", f"{len(df_churn):,}")
        k2.metric("Riesgo alto", f"{len(df_churn[df_churn['risk_band'] == 'alto']):,}")
        k3.metric("Riesgo medio", f"{len(df_churn[df_churn['risk_band'] == 'medio']):,}")

        col_ch1, col_ch2 = st.columns(2)
        with col_ch1:
            st.subheader("Distribución de riesgo")
            band_counts = df_churn["risk_band"].value_counts().reset_index()
            band_counts.columns = ["risk_band", "count"]
            fig_band = px.pie(
                band_counts, values="count", names="risk_band",
                color="risk_band",
                color_discrete_map={"alto": "#E8684C", "medio": "#F1C40F", "bajo": "#2ECC71"},
                hole=0.4,
            )
            st.plotly_chart(fig_band, use_container_width=True)

        with col_ch2:
            st.subheader(f"Top 20 — Mayor riesgo ({banda})")
            df_top_ch = df_ch_filt.nlargest(20, "churn_probability")[
                ["agency_id", "churn_probability", "risk_band"]
            ].copy()
            df_top_ch["churn_probability"] = (df_top_ch["churn_probability"] * 100).round(1)
            fig_top_ch = px.bar(
                df_top_ch, x="churn_probability", y="agency_id",
                orientation="h",
                color="risk_band",
                color_discrete_map={"alto": "#E8684C", "medio": "#F1C40F", "bajo": "#2ECC71"},
                labels={"churn_probability": "% Churn", "agency_id": "Agencia ID"},
            )
            fig_top_ch.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_top_ch, use_container_width=True)

        st.subheader("Tabla de riesgo de abandono")
        df_ch_show = df_ch_filt[["agency_id", "churn_probability", "risk_band", "prediction_date"]].copy()
        df_ch_show["churn_probability"] = (df_ch_show["churn_probability"] * 100).round(1)
        df_ch_show["prediction_date"] = pd.to_datetime(df_ch_show["prediction_date"]).dt.strftime("%Y-%m-%d")
        df_ch_show.columns = ["Agencia ID", "% Churn", "Banda", "Fecha scoring"]
        st.dataframe(df_ch_show.sort_values("% Churn", ascending=False), use_container_width=True, hide_index=True)
