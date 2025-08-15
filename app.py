import streamlit as st
import pandas as pd
import numpy as np
import websocket
import json
import threading
import time
import plotly.express as px
import plotly.graph_objects as go

# ========== Streamlit Page Config ==========
st.set_page_config(page_title="🚀 Crypto Bull Run Dashboard", layout="wide")
st.title("🚀 Crypto Bull Run Dashboard")

# ========== Sidebar Inputs ==========
entry_btc = st.sidebar.number_input(
    "Your BTC average entry ($)", min_value=0.0, max_value=1_000_000.0, value=40_000.0, step=100.0
)
entry_eth = st.sidebar.number_input(
    "Your ETH average entry ($)", min_value=0.0, max_value=100_000.0, value=2_500.0, step=10.0
)
qty_btc = st.sidebar.number_input(
    "BTC Quantity", min_value=0.0, max_value=100.0, value=1.0, step=0.01
)
qty_eth = st.sidebar.number_input(
    "ETH Quantity", min_value=0.0, max_value=1000.0, value=1.0, step=0.01
)

# Altcoins list
altcoins = ["ADA", "SOL", "BNB", "XRP", "DOT", "LTC", "DOGE"]
altcoin_entries = {}
for coin in altcoins:
    altcoin_entries[coin] = st.sidebar.number_input(
        f"Your {coin} average entry ($)", min_value=0.0, max_value=10_000.0, value=100.0, step=1.0
    )

# ========== Real-Time Price via WebSocket ==========
API_KEY = "dd65f59eeea44d1a9b5f745fb0df5876d92cb888b30f0cd06d22c346f1a91f64"
SOCKET_URL = f"wss://data-streamer.coindesk.com/?api_key={API_KEY}"

# Data storage
prices = {"BTC-USD": np.nan, "ETH-USD": np.nan}
signals = []

def on_message(ws, message):
    global prices, signals
    data = json.loads(message)
    if data.get("TYPE") == "PRICE":
        symbol = data["instrument"]
        prices[symbol] = float(data["price"])
    elif data.get("TYPE") == "SIGNAL":
        signals.append(data)

def on_error(ws, error):
    st.error(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    st.warning("WebSocket closed")

def on_open(ws):
    # Subscribe to BTC and ETH
    sub_msg = {
        "action": "SUB_ADD",
        "type": "1101",
        "groups": ["VALUE", "CURRENT_HOUR"],
        "subscriptions": [{"market": "cadli", "instrument": "BTC-USD"},
                          {"market": "cadli", "instrument": "ETH-USD"}]
    }
    ws.send(json.dumps(sub_msg))

# Start WebSocket in a separate thread
def start_ws():
    ws = websocket.WebSocketApp(SOCKET_URL,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close,
                                on_open=on_open)
    ws.run_forever()

threading.Thread(target=start_ws, daemon=True).start()

# ========== Display Prices ==========
st.subheader("💰 Real-Time Prices")
st.metric("BTC Price ($)", f"{prices['BTC-USD']:.2f}" if not np.isnan(prices['BTC-USD']) else "N/A", 
          f"{prices['BTC-USD'] - entry_btc:.2f}" if not np.isnan(prices['BTC-USD']) else "")
st.metric("ETH Price ($)", f"{prices['ETH-USD']:.2f}" if not np.isnan(prices['ETH-USD']) else "N/A", 
          f"{prices['ETH-USD'] - entry_eth:.2f}" if not np.isnan(prices['ETH-USD']) else "")

# ========== Portfolio Value ==========
btc_value = (prices['BTC-USD'] * qty_btc) if not np.isnan(prices['BTC-USD']) else 0
eth_value = (prices['ETH-USD'] * qty_eth) if not np.isnan(prices['ETH-USD']) else 0
alt_value = 0

for coin in altcoins:
    # Placeholder as altcoins not subscribed yet
    alt_value += altcoin_entries[coin] * 1  # Replace 1 with actual price

total_portfolio = btc_value + eth_value + alt_value
st.subheader("🎯 Portfolio Value")
st.write(f"${total_portfolio:,.2f}")

# ========== Altcoin Table ==========
st.subheader("🔥 Altcoin Watch")
alt_df = pd.DataFrame({
    "Coin": altcoins,
    "Entry ($)": [altcoin_entries[c] for c in altcoins],
    "Current ($)": [1]*len(altcoins),  # Placeholder
    "Profit ($)": [1 - altcoin_entries[c] for c in altcoins]  # Placeholder
})
st.dataframe(alt_df)

# ========== BTC Rainbow Chart ==========
st.subheader("🌈 BTC Historical Chart")
# Placeholder chart
dates = pd.date_range(start="2021-01-01", periods=100)
btc_prices = np.linspace(30_000, 60_000, 100)
fig = px.line(x=dates, y=btc_prices, labels={"x": "Date", "y": "Price ($)"})
st.plotly_chart(fig, use_container_width=True)

# ========== Trading Signals ==========
st.subheader("🔔 Trading Signals")
if signals:
    sig_df = pd.DataFrame(signals)
    st.dataframe(sig_df)
else:
    st.write("No signals yet.")

