import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# --------------------------
# Config
# --------------------------
st.set_page_config(page_title="Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")
API_KEY = "dd65f59eeea44d1a9b5f745fb0df5876d92cb888b30f0cd06d22c346f1a91f64"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# --------------------------
# Sidebar Parameters
# --------------------------
st.sidebar.header("Dashboard Parameters")

dom_first = st.sidebar.number_input("BTC Dominance: 1st break (%)", 0.0, 100.0, 58.29, 0.01)
dom_second = st.sidebar.number_input("BTC Dominance: strong confirm (%)", 0.0, 100.0, 54.66, 0.01)
ethbtc_break = st.sidebar.number_input("ETH/BTC breakout level", 0.0, 1.0, 0.054, 0.001)

entry_btc = st.sidebar.number_input("Your BTC average entry ($)", 0.0, 1_000_000, 40000.0, 100.0)
entry_eth = st.sidebar.number_input("Your ETH average entry ($)", 0.0, 1_000_000, 2000.0, 10.0)
ladder_step_pct = st.sidebar.slider("Take profit every X% gain", 1, 50, 10)
sell_pct_per_step = st.sidebar.slider("Sell Y% each step", 1, 50, 10)
max_ladder_steps = st.sidebar.slider("Max ladder steps", 1, 30, 8)

use_trailing = st.sidebar.checkbox("Enable trailing stop", value=True)
trail_pct = st.sidebar.slider("Trailing stop (%)", 5, 50, 20)

target_alt_alloc = st.sidebar.slider("Target Alt allocation when signals fire (%)", 0, 100, 40)
top_n_alts = st.sidebar.slider("Top N alts to scan (by market cap)", 10, 100, 50, 10)

# --------------------------
# Data Fetchers
# --------------------------
@st.cache_data(ttl=60)
def get_price(symbol: str):
    url = f"https://api.coindesk.com/v2/prices/{symbol}-USD/spot"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return float(r.json()["data"]["amount"])

@st.cache_data(ttl=60)
def get_multiple_prices(symbols: list):
    url = "https://api.coindesk.com/v2/prices/multi-symbols-full-data"
    r = requests.get(url, headers=HEADERS, params={"symbols": ",".join(symbols)}, timeout=20)
    r.raise_for_status()
    data = r.json()["data"]
    prices = {sym: float(data[sym]["price"]["amount"]) for sym in data}
    return prices

@st.cache_data(ttl=120)
def get_trading_signals():
    url = "https://api.coindesk.com/v2/trading-signals/latest"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()["data"]

# --------------------------
# Fetch BTC/ETH Prices
# --------------------------
try:
    btc_price = get_price("BTC")
    eth_price = get_price("ETH")
    ethbtc = eth_price / btc_price
except Exception as e:
    st.error(f"Price fetch failed: {e}")
    btc_price, eth_price, ethbtc = None, None, None

# --------------------------
# Signals
# --------------------------
try:
    trading_signals = get_trading_signals()
except Exception as e:
    st.warning(f"Trading signals fetch failed: {e}")
    trading_signals = {}

# --------------------------
# Header Metrics
# --------------------------
col1, col2, col3 = st.columns(3)
col1.metric("BTC Price ($)", f"{btc_price:,.2f}" if btc_price else "N/A")
col2.metric("ETH Price ($)", f"{eth_price:,.2f}" if eth_price else "N/A")
col3.metric("ETH/BTC", f"{ethbtc:.6f}" if ethbtc else "N/A")

# --------------------------
# Historical Chart Placeholder (BTC Rainbow)
# --------------------------
st.header("🌈 Bitcoin Historical Chart")
try:
    url = "https://api.coindesk.com/v2/prices/BTC-USD/historical"
    r = requests.get(url, headers=HEADERS, params={"start_date":"2010-07-17","end_date":datetime.today().strftime("%Y-%m-%d")}, timeout=20)
    r.raise_for_status()
    hist = pd.DataFrame(r.json()["data"])
    hist["date"] = pd.to_datetime(hist["time"])
    hist.set_index("date", inplace=True)
    fig = px.line(hist, y="price", title="BTC Historical Price")
    st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.warning(f"Failed to fetch historical BTC data: {e}")

# --------------------------
# Profit Ladder
# --------------------------
def build_ladder(entry, current, step_pct, sell_pct, max_steps):
    rows = []
    if entry <= 0:
        return pd.DataFrame(rows)
    for i in range(1, max_steps+1):
        target = entry * (1 + step_pct/100.0)**i
        rows.append({
            "Step #": i,
            "Target Price": round(target,2),
            "Gain from Entry (%)": round((target/entry-1)*100,2),
            "Sell This Step (%)": sell_pct
        })
    return pd.DataFrame(rows)

btc_ladder = build_ladder(entry_btc, btc_price, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
eth_ladder = build_ladder(entry_eth, eth_price, ladder_step_pct, sell_pct_per_step, max_ladder_steps)

st.header("🎯 Profit-Taking Ladder")
c1, c2 = st.columns(2)
with c1:
    st.subheader("BTC Ladder")
    st.dataframe(btc_ladder, use_container_width=True)
with c2:
    st.subheader("ETH Ladder")
    st.dataframe(eth_ladder, use_container_width=True)

# --------------------------
# Trailing Stop Guidance
# --------------------------
if use_trailing and btc_price:
    st.markdown("---")
    st.subheader("🛡️ Trailing Stop Guidance")
    st.write(f"- Suggested BTC stop: ${btc_price*(1-trail_pct/100):,.2f}")
    if eth_price:
        st.write(f"- Suggested ETH stop: ${eth_price*(1-trail_pct/100):,.2f}")

# --------------------------
# Altcoin Prices & Rotation
# --------------------------
st.header("🔥 Altcoin Watch")
try:
    alt_symbols = ["ADA","SOL","BNB","XRP","DOT","LTC","DOGE"][:top_n_alts]  # example top alts
    alt_prices = get_multiple_prices(alt_symbols)
    alt_df = pd.DataFrame([
        {"Coin": k, "Price ($)": v} for k,v in alt_prices.items()
    ])
    st.dataframe(alt_df)
except Exception as e:
    st.warning(f"Altcoin fetch failed: {e}")

# --------------------------
# Trading Signals Panel
# --------------------------
st.header("🔔 Trading Signals")
if trading_signals:
    for signal_name, status in trading_signals.items():
        st.markdown(f"**{signal_name}**: {'🟢' if status else '🔴'}")
else:
    st.info("No trading signals available")
