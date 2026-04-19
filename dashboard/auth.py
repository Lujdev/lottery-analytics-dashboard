"""Auth compartido — importar en cada página para verificar sesión."""
import streamlit as st
import streamlit_authenticator as stauth


def get_authenticator():
    credentials = {
        "usernames": {
            "admin": {
                "name": "Admin",
                "password": st.secrets.get("password", "***REMOVED***"),
            }
        }
    }
    return stauth.Authenticate(
        credentials=credentials,
        cookie_name="premier_analytics",
        cookie_key=st.secrets.get("cookie_key", "fallback_key"),
        cookie_expiry_days=30,
    )


def require_auth():
    """Llama en cada página. Redirige al login si no hay sesión."""
    authenticator = get_authenticator()
    authenticator.login(location="main")

    status = st.session_state.get("authentication_status")

    if status is False:
        st.error("Contraseña incorrecta")
        st.stop()
    elif status is None:
        st.stop()
