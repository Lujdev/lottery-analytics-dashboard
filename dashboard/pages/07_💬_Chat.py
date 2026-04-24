import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.auth import require_auth
from dashboard.llm.chat_assistant import render_chat_ui
import streamlit as st

st.set_page_config(page_title="Chat Analítico", layout="wide")

require_auth()

st.title("💬 Chat")
st.caption("Consultá datos de forma conversacional. Hacé preguntas sobre ventas, agencias, productos y pronósticos.")

render_chat_ui()
