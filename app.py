# app.py
import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Crypto Alt Season Radar", layout="wide")
st.title("📊 Crypto Alt Season Radar")
st.markdown("""
This app monitors **BTC, ETH, and Altcoin signals** to detect alt season conditions
and guide rotation strategies.
""")

# ----------------------------
# 1️⃣ Fetch BTC & ETH Data
# ----------------------------
st.header("1. BTC & ETH Signals")

@st.cache_data(ttl=60)
def get_coin_data(coin="bitcoin"):
    """Fetch coin data from CoinGecko safely."""
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}"
        r = requests.get(url).json()
        return r
    except Exception as e:
        st.error(f"Error fetching {coin} data: {e}")
        return {}

btc_data = get_coin_data("bitcoin")
eth_data = get_coin_data("ethereum")

# Safe extraction with fallback values
btc_price = btc_data.get("market_data", {}).get("current_price", {}).get("usd", None)
eth_price = eth_data.get("market_data", {}).get("current_price", {}).get("usd", None)

btc_price = btc_price if btc_price else 30000   # fallback
eth_price = eth_price if eth_price else 2000    # fallback

btc_dominance = btc_data.get("market_data", {}).get("market_cap_percentage", {}).get("btc", None)
btc_dominance = btc_dominance if btc_dominance else 50.0  # fallback

eth_btc_ratio = eth_price / btc_price

# Display metrics
st.metric("BTC Price ($)", btc_price)
st.metric("ETH Price ($)", eth_price)
st.metric("BTC Dominance (%)", round(btc_dominance, 2))
st.metric("ETH/BTC Ratio", round(eth_btc_ratio, 5))

st.markdown("""
**Explanation:**
- **BTC Dominance:** Falling dominance usually signals alt season is starting.
- **ETH/BTC Ratio:** Rising ETH/BTC indicates ETH is outperforming BTC — early alt season.
""")

# ----------------------------
# 2️⃣ Fear & Greed Index
# ----------------------------
st.header("2. Fear & Greed Index")

@st.cache_data(ttl=600)
def get_fng():
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        r = requests.get(url).json()
        data = r["data"][0]
        return int(data["value"]), data["value_classification"]
    except:
        return 50, "Neutral"  # fallback

fng_value, fng_class = get_fng()
st.metric("Fear & Greed Index", f"{fng_value} ({fng_class})")
st.markdown("""
**Explanation:**
- **Extreme Fear (<25):** Early entry for alts.
- **Extreme Greed (>70):** Take profits; altcoins may correct.
""")

# ----------------------------
# 3️⃣ BTC Volatility & Funding Rates (Placeholders)
# ----------------------------
st.header("3. BTC Volatility & Funding Rates")
st.markdown("""
- **BTC ATR (Volatility):** Lower ATR → safer environment for alt rotation.
- **Funding Rates:** Negative funding (<0) → market shorts → good alt entries.

⚠️ Real-time ATR and funding rates require exchange APIs (Binance/Bybit) and are placeholders here.
""")

# ----------------------------
# 4️⃣ Altcoin Rotation Strategy
# ----------------------------
st.header("4. Altcoin Rotation Strategy")

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

st.markdown("""
**Switching Strategy:**
1. BTC consolidating + ETH/BTC rising → rotate 20–40% to Tier 1 alts.
2. Rising volume in mid-caps → rotate 20–30% to Tier 2.
3. BTC/ETH pullback but low dominance → hold alts, take partial profits if needed.
4. BTC/ETH breakout → rotate profits back to BTC/ETH.
""")

# ----------------------------
# 5️⃣ On-Chain & Social Signals (Placeholders)
# ----------------------------
st.header("5. On-Chain & Social Signals")
st.markdown("""
- **Exchange Flows:** Net outflows → safer for alts.
- **Whale Activity:** Large movements → trend change signals.
- **TVL & DeFi Activity:** Rising → early alt entries.
- **Social Metrics:** Twitter, Reddit, Telegram hype → anticipate short-term moves.

⚠️ Real-time integration with Web3 or LunarCrush can be added for automated scoring.
""")

# ----------------------------
# 6️⃣ Alt Season Scoring System
# ----------------------------
st.header("6. Alt Season Scoring System (Simplified)")

st.markdown("""
Assign 1 point for each favorable signal:
- BTC dominance falling
- ETH/BTC rising
- Fear & Greed extreme fear
- BTC ATR low
- Exchange outflows
- Rising DeFi/NFT TVL
- Altcoin volume surge

**Score Interpretation:**
- 0–2 → Avoid alts
- 3–5 → Consider small allocation
- 6–7 → Strong alt season → rotate portfolio
""")

st.success("✅ Use this scoring system to make systematic rotation decisions rather than guessing!")

st.markdown("Made with ❤️ by Fabien Astre")
