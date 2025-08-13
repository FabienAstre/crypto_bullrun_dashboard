# app.py
import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import plotly.graph_objects as go

# ---------------------------
# Helper Functions
# ---------------------------
def fetch_fear_greed():
    """Fetch Fear & Greed Index safely"""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        r = requests.get(url).json()
        value = int(r['data'][0]['value'])
        classification = r['data'][0]['value_classification']
        return value, classification
    except:
        st.warning("⚠️ Fear & Greed Index unavailable. Using fallback value 50 (Neutral).")
        return 50, "Neutral"

def fetch_crypto_price(symbol):
    """Fetch latest crypto price from Yahoo Finance safely"""
    try:
        data = yf.download(symbol, period="7d", interval="1d")
        if data.empty:
            st.warning(f"⚠️ {symbol} data empty. Using fallback prices.")
            return None
        return data
    except:
        st.warning(f"⚠️ Error fetching {symbol} price data. Using fallback prices.")
        return None

def check_signal(value, threshold, comparison="lt"):
    """Returns emoji signal based on comparison"""
    if comparison == "lt":
        return "🔴 NO" if value >= threshold else "🟢 YES"
    elif comparison == "gt":
        return "🔴 NO" if value <= threshold else "🟢 YES"
    elif comparison == "ge":
        return "🔴 NO" if value < threshold else "🟢 YES"

# ---------------------------
# Streamlit Layout
# ---------------------------
st.set_page_config(page_title="Crypto Market & Alt Season Dashboard", layout="wide")
st.title("📊 Crypto Market & Alt Season Dashboard")

# ---------------------------
# Fetch live data
# ---------------------------
btc_price_data = fetch_crypto_price("BTC-USD")
eth_price_data = fetch_crypto_price("ETH-USD")

# Safe BTC price
if btc_price_data is not None and not btc_price_data.empty:
    btc_price = btc_price_data['Close'][-1]
else:
    btc_price = 30000  # fallback

# Safe ETH price
if eth_price_data is not None and not eth_price_data.empty:
    eth_price = eth_price_data['Close'][-1]
else:
    eth_price = 2000  # fallback

fear_value, fear_class = fetch_fear_greed()

# ---------------------------
# User Inputs or Fallbacks
# ---------------------------
btc_dominance = st.sidebar.number_input("BTC Dominance (%)", value=60.0)
eth_btc = st.sidebar.number_input("ETH/BTC", value=0.05)

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
rsi_btc = 62.3
rsi_eth = 73.3
btc_sma_cross = "No cross"
eth_sma_cross = "No cross"

extra_data = {
    "Indicator": ["BTC 50/200 SMA", "ETH 50/200 SMA", "BTC RSI(14)", "ETH RSI(14)", "Fear & Greed Index"],
    "Value": [btc_sma_cross, eth_sma_cross, rsi_btc, rsi_eth, f"{fear_value} ({fear_class})"],
    "Note": ["", "", "Overbought" if rsi_btc>70 else "Normal", "Overbought" if rsi_eth>70 else "Normal", ""]
}
st.table(pd.DataFrame(extra_data))

# ---------------------------
# Interactive Charts
# ---------------------------
st.subheader("📈 BTC / ETH Price Charts (7d)")
fig = go.Figure()
if btc_price_data is not None and not btc_price_data.empty:
    fig.add_trace(go.Scatter(x=btc_price_data.index, y=btc_price_data['Close'], name='BTC', line=dict(color='orange')))
if eth_price_data is not None and not eth_price_data.empty:
    fig.add_trace(go.Scatter(x=eth_price_data.index, y=eth_price_data['Close'], name='ETH', line=dict(color='blue')))
fig.update_layout(xaxis_title="Date", yaxis_title="Price (USD)")
st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# Altcoin Rotation Suggestion
# ---------------------------
st.subheader("🔥 Altcoin Rotation Suggestion")
rotation_text = "Stay in BTC / stablecoins. No alt season signal detected."
if btc_dominance < 55 and eth_btc > 0.054 and rsi_eth < 70:
    rotation_text = "Altcoins may outperform. Consider top 10 altcoins by market cap."
st.info(rotation_text)

# ---------------------------
# Tiered Altcoin Rotation Strategy
# ---------------------------
st.subheader("📊 Tiered Altcoin Rotation Strategy")
rotation_table = pd.DataFrame({
    "Tier": ["Tier 1: Large-Cap", "Tier 2: Mid-Cap", "Tier 3: Speculative / Low-Cap"],
    "Example Coins": ["ETH, BNB, SOL", "MATIC, LDO, FTM", "Early DeFi / NFT coins"],
    "Allocation (%)": ["40–50%", "30–40%", "10–20%"],
    "Signal to Buy": [
        "BTC consolidating + ETH/BTC rising",
        "Mid-cap volume rising + BTC dominance falling",
        "Early DeFi/NFT hype or news catalysts"
    ]
})
st.table(rotation_table)

# ---------------------------
# Alt Season Scoring System
# ---------------------------
st.subheader("📌 Alt Season Scoring System (Simplified)")
st.markdown("""
Assign 1 point for each favorable signal:
- BTC dominance falling
- ETH/BTC rising
- Fear & Greed extreme fear
- BTC RSI < 70
- Exchange outflows
- Rising DeFi/NFT TVL
- Altcoin volume surge

**Score Interpretation:**
- 0–2 → Avoid alts
- 3–5 → Consider small allocation
- 6–7 → Strong alt season → rotate portfolio
""")
st.success("✅ Use this scoring system to make systematic rotation decisions rather than guessing!")

# ---------------------------
# Notes
# ---------------------------
st.subheader("💡 Notes & Tips")
st.markdown("""
- RSI>70 may indicate overbought; RSI<30 oversold.  
- Golden cross = bullish momentum; death cross = caution.  
- BTC dominance falling + ETH/BTC rising often signals alt season.  
- Use the tiered rotation table to allocate altcoins systematically.
""")
st.markdown("Made with ❤️ by Fabien Astre")
