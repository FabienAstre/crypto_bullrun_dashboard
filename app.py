import streamlit as st
import websocket
import json
import threading
import pandas as pd
import plotly.express as px
from datetime import datetime

# =========================
# Streamlit Config
# =========================
st.set_page_config(page_title="Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")

# =========================
# User Inputs
# =========================
entry_btc = st.sidebar.number_input("Your BTC average entry ($)", 0.0, 1_000_000, 40000.0, 100.0)
entry_eth = st.sidebar.number_input("Your ETH average entry ($)", 0.0, 1_000_000, 3000.0, 10.0)

# =========================
# Initialize session state
# =========================
if "BTC_USD" not in st.session_state:
    st.session_state.BTC_USD = None
if "ETH_USD" not in st.session_state:
    st.session_state.ETH_USD = None
if "ETH_BTC" not in st.session_state:
    st.session_state.ETH_BTC = None
if "trading_signals" not in st.session_state:
    st.session_state.trading_signals = {}

# =========================
# WebSocket Setup
# =========================
API_KEY = "dd65f59eeea44d1a9b5f745fb0df5876d92cb888b30f0cd06d22c346f1a91f64"
URL = f"wss://data-streamer.coindesk.com/?api_key={API_KEY}"

def on_message(ws, message):
    data = json.loads(message)
    msg_type = data.get("TYPE")

    # Example: tick/value updates
    if msg_type == "1101":  # Adjust type based on CoinDesk docs
        for sub in data.get("DATA", []):
            symbol = sub.get("instrument")
            price = sub.get("value")
            if symbol == "BTC-USD":
                st.session_state.BTC_USD = price
            elif symbol == "ETH-USD":
                st.session_state.ETH_USD = price
            # Update ETH/BTC ratio
            if st.session_state.BTC_USD and st.session_state.ETH_USD:
                st.session_state.ETH_BTC = st.session_state.ETH_USD / st.session_state.BTC_USD

    # Example: trading signals
    elif msg_type == "TRADING_SIGNAL":
        st.session_state.trading_signals = data.get("SIGNALS", {})

def on_error(ws, error):
    print("WebSocket Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket Closed")

def on_open(ws):
    print("WebSocket connection established")
    # Subscribe to BTC, ETH, and Trading Signals
    subscribe_msg = {
        "action": "SUB_ADD",
        "type": "1101",
        "groups": ["VALUE", "CURRENT_HOUR"],
        "subscriptions": [
            {"market": "cadli", "instrument": "BTC-USD"},
            {"market": "cadli", "instrument": "ETH-USD"},
            {"market": "cadli", "instrument": "TRADING_SIGNAL"}
        ]
    }
    ws.send(json.dumps(subscribe_msg))

# Run WebSocket in background thread
def start_ws():
    ws = websocket.WebSocketApp(URL,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.run_forever()

threading.Thread(target=start_ws, daemon=True).start()

# =========================
# Dashboard Layout
# =========================
st.title("🚀 Crypto Bull Run Dashboard")

col1, col2, col3 = st.columns(3)
col1.metric("BTC Price ($)", st.session_state.BTC_USD or "N/A",
            (st.session_state.BTC_USD - entry_btc) if st.session_state.BTC_USD else 0)
col2.metric("ETH Price ($)", st.session_state.ETH_USD or "N/A",
            (st.session_state.ETH_USD - entry_eth) if st.session_state.ETH_USD else 0)
col3.metric("ETH/BTC", st.session_state.ETH_BTC or "N/A")

# =========================
# Historical BTC Chart (fallback)
# =========================
try:
    btc_data = pd.read_csv("https://www.cryptodatadownload.com/cdd/Binance_BTCUSDT_d.csv")
    btc_data['date'] = pd.to_datetime(btc_data['date'])
    fig = px.line(btc_data, x="date", y="close", title="🌈 BTC Historical Price")
    st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.warning(f"Failed to fetch historical BTC data: {e}")

# =========================
# Trading Signals
# =========================
st.subheader("🔔 Trading Signals")
if st.session_state.trading_signals:
    st.json(st.session_state.trading_signals)
else:
    st.info("Waiting for real-time trading signals...")

# =========================
# Profit-taking Ladder
# =========================
st.subheader("🎯 Profit-Taking Ladder")
btc_price = st.session_state.BTC_USD
if btc_price:
    ladder = [btc_price * 1.05, btc_price * 1.10, btc_price * 1.20, btc_price * 1.50]
    st.write({"BTC Ladder": ladder})
else:
    st.write("Waiting for BTC price...")
