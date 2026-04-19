import streamlit as st
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.auth import require_auth
from dashboard.data import volumen_por_proveedor, evolucion_proveedor_mes, fallos_por_proveedor, _provider_parquet_exists

st.set_page_config(page_title="Proveedores Externos", layout="wide")

require_auth()

st.title("🌐 Proveedores Externos")

if not _provider_parquet_exists():
    st.warning("⚠️ Datos de proveedores no extraídos todavía.")
    st.code(".venv/bin/python -m etl.extractors.providers")
    st.stop()

df_vol = volumen_por_proveedor()
df_evol = evolucion_proveedor_mes()
df_fallos = fallos_por_proveedor()

# KPIs
k1, k2 = st.columns(2)
k1.metric("Proveedores activos", f"{len(df_vol):,}")
k2.metric("Total tickets enviados", f"{df_vol['tickets'].sum():,}" if not df_vol.empty else "—")

st.divider()

if not df_fallos.empty:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Volumen por proveedor")
        fig = px.pie(
            df_vol, values="tickets", names="provider",
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig.update_traces(textposition="outside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Tasa de fallos por proveedor")
        fig2 = px.bar(
            df_fallos, x="pct_fallo", y="provider", orientation="h",
            color="pct_fallo", color_continuous_scale="Reds",
            labels={"pct_fallo": "% Fallos", "provider": ""},
            text="pct_fallo",
        )
        fig2.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        st.plotly_chart(fig2, use_container_width=True)
else:
    st.subheader("Volumen por proveedor")
    if not df_vol.empty:
        total = df_vol["tickets"].sum()
        df_vol["pct"] = df_vol["tickets"] / total * 100
        df_plot = df_vol[df_vol["pct"] >= 0.5].copy()
        otros = df_vol[df_vol["pct"] < 0.5]["tickets"].sum()
        if otros > 0:
            import pandas as pd
            df_plot = pd.concat([
                df_plot,
                pd.DataFrame([{"provider": "Otros", "tickets": otros, "dias_activos": 0, "pct": otros / total * 100}])
            ], ignore_index=True)
        fig = px.bar(
            df_plot.sort_values("tickets"),
            x="tickets", y="provider", orientation="h",
            color="provider",
            color_discrete_sequence=px.colors.qualitative.Set2,
            labels={"tickets": "Tickets", "provider": ""},
            text=df_plot.sort_values("tickets")["pct"].apply(lambda p: f"{p:.1f}%"),
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# Evolución mensual
if not df_evol.empty:
    st.subheader("Evolución mensual por proveedor")
    fig3 = px.line(
        df_evol, x="mes", y="tickets", color="provider",
        markers=True,
        labels={"tickets": "Tickets", "mes": "Mes", "provider": "Proveedor"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig3.update_xaxes(tickangle=45)
    st.plotly_chart(fig3, use_container_width=True)

# Tabla
st.subheader("Detalle por proveedor")
if not df_vol.empty:
    st.dataframe(
        df_vol.rename(columns={"provider": "Proveedor", "tickets": "Tickets", "dias_activos": "Días Activos"}),
        use_container_width=True,
        hide_index=True,
    )
