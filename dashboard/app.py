import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.auth import require_auth

st.set_page_config(
    page_title="PremierPluss Analytics",
    page_icon="🎲",
    layout="wide",
)

require_auth()

st.title("PremierPluss Analytics")
st.markdown("Seleccioná un módulo en el menú lateral.")
