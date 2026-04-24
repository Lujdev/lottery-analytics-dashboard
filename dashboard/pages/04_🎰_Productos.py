import streamlit as st
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.auth import require_auth
from dashboard.data import (
    ventas_por_tipo_producto, ventas_por_tipo_producto_unificado,
    evolucion_productos, evolucion_productos_unificado,
    top_sorteos, top_sorteos_unificado,
    ventas_por_hora, ventas_por_hora_unificado,
    prediccion_basket, predicciones_disponibles,
    MONEDAS,
)
from dashboard.utils import fmt_money
from dashboard.rates import get_rates_to_ves, rates_display

st.set_page_config(page_title="Productos y Sorteos", layout="wide")

require_auth()

st.title("🎰 Productos y Sorteos")
st.caption("Análisis de performance por tipo de producto, sorteo y horario.")

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
    df_tipo = ventas_por_tipo_producto_unificado(rates)
    df_evol = evolucion_productos_unificado(rates)
    df_sorteos = top_sorteos_unificado(rates)
    df_hora = ventas_por_hora_unificado(rates)
else:
    df_tipo = ventas_por_tipo_producto(currency_id)
    df_evol = evolucion_productos(currency_id)
    df_sorteos = top_sorteos(currency_id)
    df_hora = ventas_por_hora(currency_id)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Participación por tipo de producto")
    fig = px.pie(
        df_tipo, values="ventas", names="tipo",
        color_discrete_sequence=px.colors.qualitative.Set2,
        hole=0.4,
    )
    fig.update_traces(textposition="outside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Margen bruto por tipo de producto")
    fig2 = px.bar(
        df_tipo.sort_values("pct_margen", ascending=True),
        x="pct_margen", y="tipo", orientation="h",
        color="pct_margen", color_continuous_scale="RdYlGn",
        labels={"pct_margen": "% Margen", "tipo": ""},
        text="pct_margen",
    )
    fig2.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

st.subheader("Evolución mensual de ventas por tipo")
fig3 = px.area(
    df_evol, x="mes", y="ventas", color="tipo",
    labels={"ventas": f"Ventas ({sym})", "mes": "Mes", "tipo": "Tipo"},
    color_discrete_sequence=px.colors.qualitative.Set2,
)
st.plotly_chart(fig3, use_container_width=True)

st.divider()

col3, col4 = st.columns(2)

with col3:
    st.subheader("Ventas por hora de sorteo")
    if not df_hora.empty and df_hora["hora"].notna().any():
        fig4 = px.bar(
            df_hora.dropna(subset=["hora"]).sort_values("hora"),
            x="hora", y="ventas",
            color="pct_margen", color_continuous_scale="RdYlGn",
            labels={"hora": "Hora", "ventas": f"Ventas ({sym})", "pct_margen": "% Margen"},
        )
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("Sin datos de hora disponibles para esta moneda.")

with col4:
    st.subheader("Top 20 sorteos por ventas")
    fig5 = px.bar(
        df_sorteos, x="ventas", y="sorteo", orientation="h",
        color="pct_margen", color_continuous_scale="RdYlGn",
        labels={"ventas": f"Ventas ({sym})", "sorteo": "", "pct_margen": "% Margen"},
        hover_data=["hora", "dias_activos"],
    )
    fig5.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig5, use_container_width=True)

st.divider()

st.subheader("Detalle de sorteos")
df_show = df_sorteos.copy()
df_show["ventas"] = df_show["ventas"].apply(lambda v: fmt_money(v, sym))
df_show["premios"] = df_show["premios"].apply(lambda v: fmt_money(v, sym))
df_show.columns = ["Sorteo", "Hora", "Ventas", "Premios", "% Margen", "Días Activos"]
st.dataframe(df_show, use_container_width=True, hide_index=True)

# ── Market Basket ───────────────────────────────────────────────────────────
st.divider()
st.subheader("🛒 Market Basket Analysis")

preds_ok = predicciones_disponibles()
if not preds_ok["basket"]:
    st.info(
        "Análisis de canasta no disponible. "
        "Corré `python -m ml.run_all` para generar predicciones."
    )
else:
    df_basket = prediccion_basket()
    if df_basket.empty:
        st.warning("El archivo de basket existe pero está vacío.")
    else:
        st.caption(
            "Reglas de asociación descubiertas con FP-Growth. "
            "Lift > 1 indica que los productos se venden juntos más de lo esperado por azar. "
            "Ordenadas por lift descendente."
        )
        min_conf = st.slider("Confianza mínima", 0.0, 1.0, 0.3, 0.05)
        min_lift = st.slider("Lift mínimo", 0.5, 5.0, 1.0, 0.5)
        df_b_filt = df_basket[
            (df_basket["confidence"] >= min_conf) & (df_basket["lift"] >= min_lift)
        ].copy()

        k1, k2, k3 = st.columns(3)
        k1.metric("Reglas totales", f"{len(df_basket):,}")
        k2.metric("Reglas filtradas", f"{len(df_b_filt):,}")
        k3.metric("Lift máximo", f"{df_basket['lift'].max():.2f}")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.subheader("Top 15 reglas por lift")
            df_top_b = df_b_filt.nlargest(15, "lift")[
                ["antecedent", "consequent", "lift", "confidence"]
            ].copy()
            df_top_b["lift"] = df_top_b["lift"].round(2)
            df_top_b["confidence"] = (df_top_b["confidence"] * 100).round(1)
            fig_b = px.bar(
                df_top_b, x="lift", y=df_top_b.index,
                orientation="h",
                color="confidence",
                color_continuous_scale="Blues",
                labels={"lift": "Lift", "index": "Regla"},
                hover_data=["antecedent", "consequent"],
            )
            fig_b.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_b, use_container_width=True)

        with col_b2:
            st.subheader("Dispersión Confidence vs Lift")
            fig_sc = px.scatter(
                df_b_filt, x="confidence", y="lift",
                size="support",
                color="lift",
                color_continuous_scale="Blues",
                hover_data=["antecedent", "consequent"],
                labels={"confidence": "Confianza", "lift": "Lift"},
            )
            st.plotly_chart(fig_sc, use_container_width=True)

        st.subheader("Tabla de reglas")
        df_b_show = df_b_filt[["antecedent", "consequent", "support", "confidence", "lift"]].copy()
        df_b_show["support"] = (df_b_show["support"] * 100).round(2)
        df_b_show["confidence"] = (df_b_show["confidence"] * 100).round(1)
        df_b_show["lift"] = df_b_show["lift"].round(2)
        df_b_show.columns = ["Antecedente", "Consecuente", "Soporte (%)", "Confianza (%)", "Lift"]
        st.dataframe(df_b_show.sort_values("Lift", ascending=False), use_container_width=True, hide_index=True)
