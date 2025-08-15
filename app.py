import math
import time
import requests
import pandas as pd
import streamlit as st
import datetime
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pytrends.request import TrendReq

st.set_page_config(page_title="Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")

# =========================
# Sidebar Parameters
# =========================
st.sidebar.header("Dashboard Parameters")

st.sidebar.subheader("Dominance & ETH/BTC Triggers")
dom_first = st.sidebar.number_input("BTC Dominance: 1st break (%)", 0.0, 100.0, 58.29, 0.01, format="%.2f")
dom_second = st.sidebar.number_input("BTC Dominance: strong confirm (%)", 0.0, 100.0, 54.66, 0.01, format="%.2f")
ethbtc_break = st.sidebar.number_input("ETH/BTC breakout level", 0.0, 1.0, 0.054, 0.001, format="%.3f")

st.sidebar.subheader("Profit-Taking Plan")
entry_btc = st.sidebar.number_input("Your BTC average entry ($)", 0.0, 1000000.0, 40000.0, 100.0)
entry_eth = st.sidebar.number_input("Your ETH average entry ($)", 0.0, 1000000.0, 2000.0, 10.0)
ladder_step_pct = st.sidebar.slider("Take profit every X% gain", 1, 50, 10)
sell_pct_per_step = st.sidebar.slider("Sell Y% each step", 1, 50, 10)
max_ladder_steps = st.sidebar.slider("Max ladder steps", 1, 30, 8)

st.sidebar.subheader("Trailing Stop (Optional)")
use_trailing = st.sidebar.checkbox("Enable trailing stop", value=True)
trail_pct = st.sidebar.slider("Trailing stop (%)", 5, 50, 20)

st.sidebar.subheader("Alt Rotation")
target_alt_alloc = st.sidebar.slider("Target Alt allocation when signals fire (%)", 0, 100, 40)
top_n_alts = st.sidebar.slider("Top N alts to scan (by market cap)", 10, 100, 50, 10)

st.sidebar.caption("This dashboard pulls live data at runtime (CoinGecko, Alternative.me, Google Trends).")

# =========================
# Data Fetchers
# =========================
@st.cache_data(ttl=300)
def get_global():
    r = requests.get("https://api.coingecko.com/api/v3/global", timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=300)
def get_ethbtc():
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids":"ethereum","vs_currencies":"btc"},
        timeout=20
    )
    r.raise_for_status()
    return float(r.json()["ethereum"]["btc"])

@st.cache_data(ttl=300)
def get_prices_usd(ids):
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": ",".join(ids), "vs_currencies": "usd"},
        timeout=20
    )
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=300)
def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=20)
        r.raise_for_status()
        data = r.json()["data"][0]
        return int(data["value"]), data["value_classification"]
    except Exception:
        return None, None

@st.cache_data(ttl=300)
def get_top_alts_safe(n=50):
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": n+10,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h,7d,30d"
            },
            timeout=20
        )
        r.raise_for_status()
        data = [x for x in r.json() if x["symbol"].upper() not in ("BTC","ETH")][:n]
        df = pd.DataFrame([{
            "Rank": x["market_cap_rank"],
            "Coin": x["symbol"].upper(),
            "Name": x["name"],
            "Price ($)": x["current_price"],
            "24h %": x.get("price_change_percentage_24h_in_currency"),
            "7d %": x.get("price_change_percentage_7d_in_currency"),
            "30d %": x.get("price_change_percentage_30d_in_currency"),
            "Mkt Cap ($B)": (x["market_cap"] or 0)/1e9
        } for x in data])
        return df
    except Exception as e:
        st.warning(f"Altcoin data fetch failed: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=120)
def get_rsi_macd_volume():
    # Placeholder
    return 72, 0.002, False

@st.cache_data(ttl=360)
def get_google_trends(keywords=["Bitcoin","Ethereum"], timeframe='now 7-d'):
    pytrends = TrendReq(hl='en-US', tz=360)
    pytrends.build_payload(keywords, timeframe=timeframe)
    data = pytrends.interest_over_time()
    if not data.empty:
        spikes = {kw: data[kw].pct_change().max()*100 for kw in keywords}
        return spikes
    return {kw: 0 for kw in keywords}

# =========================
# Signal Builder
# =========================
def build_signals(dom, ethbtc, fg_value, rsi, macd_div, vol_div, trends):
    sig = {
        "dom_below_first": dom is not None and dom < dom_first,
        "dom_below_second": dom is not None and dom < dom_second,
        "ethbtc_break": ethbtc is not None and ethbtc > ethbtc_break,
        "greed_high": fg_value is not None and fg_value >= 80,
        "RSI_overbought": rsi is not None and rsi > 70,
        "MACD_div": macd_div,
        "Volume_div": vol_div,
        "GoogleTrendsSpike": any(v>50 for v in trends.values())  # Example threshold
    }
    sig["rotate_to_alts"] = sig["dom_below_first"] and sig["ethbtc_break"]
    sig["profit_mode"] = sig["dom_below_second"] or sig["greed_high"] or sig["RSI_overbought"] or sig["MACD_div"] or sig["Volume_div"]
    sig["full_exit_watch"] = sig["dom_below_second"] and sig["greed_high"]
    sig["MVRV_Z"] = True
    sig["SOPR_LTH"] = True
    sig["Exchange_Inflow"] = False
    sig["Pi_Cycle_Top"] = False
    sig["Funding_Rate"] = True
    return sig

# =========================
# Header Metrics
# =========================
col1, col2, col3, col4 = st.columns(4)

btc_dom = None
ethbtc = None
fg_value, fg_label = get_fear_greed()
rsi, macd_div, vol_div = get_rsi_macd_volume()
trends = get_google_trends()

try:
    g = get_global()
    btc_dom = float(g["data"]["market_cap_percentage"]["btc"])
    col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}")
except Exception as e:
    col1.error(f"BTC.D fetch failed: {e}")

try:
    ethbtc = get_ethbtc()
    col2.metric("ETH/BTC", f"{ethbtc:.6f}")
except Exception as e:
    col2.error(f"ETH/BTC fetch failed: {e}")

if fg_value is not None:
    col3.metric("Fear & Greed", f"{fg_value} ({fg_label})")
else:
    col3.error("Fear & Greed fetch failed")

btc_price = None
eth_price = None
try:
    prices = get_prices_usd(["bitcoin","ethereum"])
    btc_price = float(prices["bitcoin"]["usd"])
    eth_price = float(prices["ethereum"]["usd"])
    col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}")
except Exception as e:
    col4.error(f"Price fetch failed: {e}")

st.markdown("---")

sig = build_signals(btc_dom, ethbtc, fg_value, rsi, macd_div, vol_div, trends)

# =========================
# Signals Panel
# =========================
signal_defs = {
    "Dom < First Break": {"active": sig.get("dom_below_first"), "desc": "BTC losing market share → altcoins may start moving up."},
    "Dom < Strong Confirm": {"active": sig.get("dom_below_second"), "desc": "Confirms major rotation into altcoins → potential altseason."},
    "ETH/BTC Breakout": {"active": sig.get("ethbtc_break"), "desc": "ETH outperforming BTC → bullish for ETH and altcoins."},
    "F&G ≥ 80": {"active": sig.get("greed_high"), "desc": "Extreme greed → market may be overbought."},
    "RSI > 70": {"active": sig.get("RSI_overbought"), "desc": "BTC overbought → possible short-term correction."},
    "MACD Divergence": {"active": sig.get("MACD_div"), "desc": "Momentum slowing → potential reversal."},
    "Volume Divergence": {"active": sig.get("Volume_div"), "desc": "Weak price movement → caution on trend continuation."},
    "Rotate to Alts": {"active": sig.get("rotate_to_alts"), "desc": "Strong rotation signal → move funds into altcoins."},
    "Profit Mode": {"active": sig.get("profit_mode"), "desc": "Suggests scaling out of positions / taking profit."},
    "Full Exit Watch": {"active": sig.get("full_exit_watch"), "desc": "Extreme signal → consider exiting major positions."},
    "Google Trends Spike": {"active": sig.get("GoogleTrendsSpike"), "desc": "Google search interest spiking → retail attention rising."}
}

st.markdown("### 📊 Key Market Signals")
cols = st.columns(len(signal_defs))
for i, (name, info) in enumerate(signal_defs.items()):
    emoji = "🟢" if info["active"] else "🔴"
    cols[i].markdown(f"**{name}** {emoji}  \n*{info['desc']}*")
