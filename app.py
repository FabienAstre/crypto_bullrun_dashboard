# app.py
import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import plotly.graph_objects as go
from ta.momentum import RSIIndicator

# ---------------------------
# Helper functions
# ---------------------------
@st.cache_data(ttl=600)
def fetch_fear_greed():
    """Fetch Fear & Greed Index"""
    url = "https://api.alternative.me/fng/?limit=1"
    try:
        r = requests.get(url).json()
        value = int(r['data'][0]['value'])
        classification = r['data'][0]['value_classification']
        return value, classification
    except:
        return None, None

@st.cache_data(ttl=600)
def fetch_crypto_price(symbol):
    """Fetch latest crypto price from Yahoo Finance"""
    try:
        data = yf.download(symbol, period="7d", interval="1d")
        if data.empty:
            return None
        return data
    except:
        return None

def compute_rsi(data, period=14):
    return RSIIndicator(data['Close'], window=period).rsi().iloc[-1] if data is not None else None

def compute_sma_cross(data, short=50, long=200):
    if data is None or len(data) < long:
        return "No cross"
    sma_short = data['Close'].rolling(short).mean().iloc[-1]
    sma_long = data['Close'].rolling(long).mean().iloc[-1]
    if sma_short > sma_long:
        return "Golden Cross"
    elif sma_short < sma_long:
        return "Death Cross"
    return "No cross"

def check_signal(value, threshold, comparison="lt"):
    """Returns emoji signal based on comparison"""
    if value is None:
        return "⚠️ N/A"
    if comparison == "lt":
        return "🔴 NO" if value >= threshold else "🟢 YES"
    elif comparison == "gt":
        return "🔴 NO" if value <= threshold else "🟢 YES"
    elif comparison == "ge":
        return "🔴 NO" if value < threshold else "🟢 YES"

# ---------------------------
# Streamlit Layout
# ---------------------------
st.set_page_config(page_title="Crypto Market Dashboard", layout="wide")
st.title("📊 Crypto Market Dashboard")

# Fetch live data
btc_price_data = fetch_crypto_price("BTC-USD")
eth_price_data = fetch_crypto_price("ETH-USD")
btc_price = btc_price_data['Close'].iloc[-1] if btc_price_data is not None else "N/A"
eth_price = eth_price_data['Close'].iloc[-1] if eth_price_data is not None else "N/A"

fear_value, fear_class = fetch_fear_greed()

# ---------------------------
# User Inputs / Fallbacks
# ---------------------------
btc_dominance = st.sidebar.slider("BTC Dominance (%)", 0.0, 100.0, 60.0)
eth_btc = st.sidebar.number_input("ETH/BTC", value=0.05, format="%.6f")

# ---------------------------
# Signals
# ---------------------------
st.subheader("⚡ Market Signals")
signals = {
    "BTC Dominance < 58.29%": check_signal(btc_dominance, 58.29),
    "BTC Dominance < 54.66%": check_signal(btc_dominance, 54.66),
    "ETH/BTC > 0.054": check_signal(eth_btc, 0.054, "gt"),
    "Fear & Greed ≥ 80": check_signal(fear_value, 80, "ge")
}
st.table(pd.DataFrame.from_dict(signals, orient='index', columns=["Signal"]))

# ---------------------------
# Extra Indicators
# ---------------------------
st.subheader("📌 Extra Indicators")
rsi_btc = compute_rsi(btc_price_data)
rsi_eth = compute_rsi(eth_price_data)
btc_sma_cross = compute_sma_cross(btc_price_data)
eth_sma_cross = compute_sma_cross(eth_price_data)

extra_data = {
    "Indicator": ["BTC 50/200 SMA", "ETH 50/200 SMA", "BTC RSI(14)", "ETH RSI(14)", "Fear & Greed Index"],
    "Value": [
        btc_sma_cross, eth_sma_cross,
        round(rsi_btc, 2) if rsi_btc else "N/A",
        round(rsi_eth, 2) if rsi_eth else "N/A",
        f"{fear_value} ({fear_class})" if fear_value else "N/A"
    ],
    "Note": [
        "", "", 
        "Overbought" if rsi_btc and rsi_btc > 70 else "Normal",
        "Overbought" if rsi_eth and rsi_eth > 70 else "Normal",
        ""
    ]
}
st.table(pd.DataFrame(extra_data))

# ---------------------------
# Interactive Charts
# ---------------------------
st.subheader("📈 BTC / ETH Price Charts (7d)")
fig = go.Figure()
if btc_price_data is not None:
    fig.add_trace(go.Scatter(x=btc_price_data.index, y=btc_price_data['Close'], name='BTC', line=dict(color='orange')))
if eth_price_data is not None:
    fig.add_trace(go.Scatter(x=eth_price_data.index, y=eth_price_data['Close'], name='ETH', line=dict(color='blue')))
fig.update_layout(xaxis_title="Date", yaxis_title="Price (USD)")
st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# Altcoin Rotation Suggestion
# ---------------------------
st.subheader("🔥 Altcoin Rotation Suggestion")
rotation_text = "Stay in BTC / stablecoins. No alt season signal detected."
if btc_dominance < 55 and eth_btc > 0.054 and (rsi_eth and rsi_eth < 70):
    rotation_text = "Altcoins may outperform. Consider top 10 altcoins by market cap."
st.info(rotation_text)

# ---------------------------
# Notes
# ---------------------------
st.subheader("💡 Notes & Tips")
st.markdown("""
- RSI>70 may be overbought; RSI<30 oversold.  
- Golden cross = bullish momentum; death cross = caution.  
- Use BTC dominance and ETH/BTC trend to identify potential altcoin rotation.
""")
