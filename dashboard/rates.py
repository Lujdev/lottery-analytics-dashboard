"""Tasas de cambio vs VES. BCV para USD, Frankfurter para el resto."""
import streamlit as st
import requests

BCV_URL = "https://dolar.beautyvzla.shop/api/v1/rates/bcv"
FOREX_URL = "https://open.er-api.com/v6/latest/USD"

CURRENCY_IDS = {1: "VES", 2: "USD", 3: "BRL", 4: "PEN", 5: "COP"}


@st.cache_data(ttl=3600)
def get_rates_to_ves() -> dict[int, float]:
    """Devuelve {currency_id: tasa_a_VES}. VES = 1.0 siempre."""
    rates = {1: 1.0}

    try:
        bcv = requests.get(BCV_URL, headers={"accept": "*/*"}, timeout=5).json()
        usd_ves = next((r["sell_price"] for r in bcv if r["currency_pair"] == "USD/VES"), None)
        if usd_ves:
            rates[2] = usd_ves  # 1 USD = X VES
    except Exception:
        usd_ves = None

    if usd_ves:
        try:
            fx = requests.get(FOREX_URL, timeout=5).json()
            cross = fx.get("rates", {})
            # 1 XXX = (USD/VES) / (XXX/USD)
            if "BRL" in cross:
                rates[3] = usd_ves / cross["BRL"]
            if "PEN" in cross:
                rates[4] = usd_ves / cross["PEN"]
            if "COP" in cross:
                rates[5] = usd_ves / cross["COP"]
        except Exception:
            pass

    return rates


def rates_display(rates: dict[int, float]) -> str:
    """String legible para mostrar tasas activas."""
    lines = []
    for cid, rate in rates.items():
        if cid == 1:
            continue
        name = CURRENCY_IDS.get(cid, f"id={cid}")
        lines.append(f"1 {name} = {rate:,.4f} Bs.")
    return " | ".join(lines)
