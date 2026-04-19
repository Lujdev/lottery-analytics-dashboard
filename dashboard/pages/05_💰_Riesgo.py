import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.auth import require_auth
from dashboard.data import payout_ratio_por_producto, payout_ratio_por_mes, numeros_mas_apostados, MONEDAS
from dashboard.utils import fmt_money

st.set_page_config(page_title="Gestión de Riesgo", layout="wide")

require_auth()

st.title("💰 Gestión de Riesgo")
st.caption("Payout ratio por producto y sorteo. Payout > 75% = zona de atención. Payout > 100% = pérdida neta.")

col_f1, _ = st.columns([1, 3])
with col_f1:
    moneda_label = st.selectbox("Moneda", list(MONEDAS.values()), index=0)
    currency_id = next(k for k, v in MONEDAS.items() if v == moneda_label)

df_prod = payout_ratio_por_producto(currency_id)
df_mes = payout_ratio_por_mes(currency_id)

# KPIs
payout_global = (df_mes["premios"].sum() / df_mes["ventas"].sum() * 100) if not df_mes.empty else 0
productos_riesgo = len(df_prod[df_prod["payout_ratio"] > 75]) if not df_prod.empty else 0
productos_perdida = len(df_prod[df_prod["payout_ratio"] > 100]) if not df_prod.empty else 0

k1, k2, k3 = st.columns(3)
k1.metric("Payout global", f"{payout_global:.1f}%",
          delta="⚠️ Alto" if payout_global > 75 else "Normal",
          delta_color="inverse" if payout_global > 75 else "normal")
k2.metric("Productos en zona riesgo (>75%)", f"{productos_riesgo}")
k3.metric("Productos con pérdida neta (>100%)", f"{productos_perdida}",
          delta="🚨 Crítico" if productos_perdida > 0 else "OK",
          delta_color="inverse" if productos_perdida > 0 else "normal")

st.divider()

col1, col2 = st.columns(2)

# Payout por mes
with col1:
    st.subheader("Payout ratio mensual (%)")
    fig = px.bar(
        df_mes, x="mes", y="payout_ratio",
        color="payout_ratio",
        color_continuous_scale="RdYlGn_r",
        labels={"payout_ratio": "Payout %", "mes": "Mes"},
        text="payout_ratio",
    )
    fig.add_hline(y=75, line_dash="dash", line_color="yellow", annotation_text="Atención 75%")
    fig.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="Pérdida 100%")
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(yaxis_range=[0, max(110, df_mes["payout_ratio"].max() + 5) if not df_mes.empty else 110])
    st.plotly_chart(fig, use_container_width=True)

# Payout por producto
with col2:
    st.subheader("Payout ratio por producto")
    df_p = df_prod.dropna(subset=["producto"]).sort_values("payout_ratio", ascending=True).tail(20)
    fig2 = px.bar(
        df_p, x="payout_ratio", y="producto", orientation="h",
        color="payout_ratio",
        color_continuous_scale="RdYlGn_r",
        labels={"payout_ratio": "Payout %", "producto": ""},
        text="payout_ratio",
    )
    fig2.add_vline(x=75, line_dash="dash", line_color="yellow")
    fig2.add_vline(x=100, line_dash="dash", line_color="red")
    fig2.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# Números más apostados
st.subheader("Top 30 números más apostados")
st.caption("Concentración de apuestas en números específicos = riesgo si ese número sale ganador.")
with st.spinner("Escaneando 112M bets..."):
    df_nums = numeros_mas_apostados(30)

if not df_nums.empty:
    fig3 = px.bar(
        df_nums.sort_values("apuestas", ascending=False),
        x="number", y="apuestas",
        color="payout_ratio",
        color_continuous_scale="RdYlGn_r",
        labels={"number": "Número", "apuestas": "Veces apostado", "payout_ratio": "Payout %"},
        hover_data=["monto_total", "premios_pagados"],
    )
    st.plotly_chart(fig3, use_container_width=True)

st.divider()

# Tabla productos en riesgo
st.subheader("Productos con payout > 75%")
df_riesgo = df_prod[df_prod["payout_ratio"] > 75].copy()
if df_riesgo.empty:
    st.success("No hay productos con payout > 75% para esta moneda.")
else:
    df_riesgo["ventas"] = df_riesgo["ventas"].apply(lambda v: fmt_money(v, moneda_label))
    df_riesgo["premios"] = df_riesgo["premios"].apply(lambda v: fmt_money(v, moneda_label))
    df_riesgo.columns = ["Producto", "Ventas", "Premios", "Payout %"]
    st.dataframe(df_riesgo, use_container_width=True, hide_index=True)
