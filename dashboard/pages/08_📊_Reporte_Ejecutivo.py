import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from dashboard.auth import require_auth
from dashboard.llm import generate_executive_report, is_configured
from dashboard.data import predicciones_disponibles

st.set_page_config(page_title="Reporte Ejecutivo", layout="wide")

require_auth()

st.title("📊 Reporte Ejecutivo")
st.caption("Generá reportes mensuales CEO que consolidan KPIs, predicciones, riesgos y acciones sugeridas.")

# Selector de mes (default mes actual)
from datetime import datetime
mes_default = datetime.now().strftime("%Y-%m")
mes = st.text_input("Período (YYYY-MM)", value=mes_default)

if not is_configured():
    st.warning("🔒 OpenRouter no está configurado. El reporte se generará en modo offline con datos crudos.")

preds = predicciones_disponibles()
faltantes = [k for k, v in preds.items() if not v]
if faltantes:
    st.info(f"Faltan predicciones en disco: {', '.join(faltantes)}. El reporte puede estar limitado.")

if st.button("Generar reporte ejecutivo", type="primary"):
    with st.spinner("Armando contexto y consultando al modelo..."):
        try:
            report_path = generate_executive_report(mes.strip())
            st.success(f"Reporte guardado en: {report_path}")
            content = report_path.read_text(encoding="utf-8")
            st.markdown(content)
            st.download_button(
                "Descargar markdown",
                data=content,
                file_name=report_path.name,
                mime="text/markdown",
            )
        except RuntimeError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Error inesperado generando reporte: {exc}")
