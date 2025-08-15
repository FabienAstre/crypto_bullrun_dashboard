import requests
import pandas as pd
import streamlit as st
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# =========================
# 🌟 App Config
# =========================
st.set_page_config(
    page_title="💖 Crypto Bull Run Dashboard",
    page_icon="🚀",
    layout="wide"
)

st.title("💖 Crypto Bull Run Dashboard")
st.markdown("Welcome! Monitor BTC, ETH, and top altcoins with live signals, profit ladders, and rotation insights. 💎")

# =========================
# 🛠️ Sidebar Settings
# =========================
st.sidebar.header("Dashboard Settings")

# Dominance & ETH/BTC
st.sidebar.subheader("💹 Dominance & ETH/BTC Triggers")
dom_first = st.sidebar.number_input("BTC Dominance: 1st break (%)", 0.0, 100.0, 58.29, 0.01)
dom_second = st.sidebar.number_input("BTC Dominance: Strong confirm (%)", 0.0, 100.0, 54.66, 0.01)
ethbtc_break = st.sidebar.number_input("ETH/BTC breakout level", 0.0, 1.0, 0.054, 0.001)

# Profit-taking plan
st.sidebar.subheader("💰 Profit-Taking Plan")
entry_btc = st.sidebar.number_input("BTC Average Entry ($)", 0.0, 1_000_000.0, 40000.0, 100.0)
entry_eth = st.sidebar.number_input("ETH Average Entry ($)", 0.0, 1_000_000.0, 2000.0, 10.0)
ladder_step_pct = st.sidebar.slider("Take profit every X% gain", 1, 50, 10)
sell_pct_per_step = st.sidebar.slider("Sell Y% each step", 1, 50, 10)
max_ladder_steps = st.sidebar.slider("Max ladder steps", 1, 30, 8)

# Trailing stop
st.sidebar.subheader("🛡️ Trailing Stop")
use_trailing = st.sidebar.checkbox("Enable trailing stop", value=True)
trail_pct = st.sidebar.slider("Trailing stop (%)", 5, 50, 20)

# Altcoin rotation
st.sidebar.subheader("🌈 Altcoin Rotation")
target_alt_alloc = st.sidebar.slider("Target Alt allocation (%)", 0, 100, 40)
top_n_alts = st.sidebar.slider("Top N alts to scan (by market cap)", 10, 100, 50, 10)
st.sidebar.caption("Live data fetched from CoinGecko & Alternative.me. 🐙")

# =========================
# 🔗 Data Fetchers
# =========================
@st.cache_data(ttl=60)
def fetch_global():
    r = requests.get("https://api.coingecko.com/api/v3/global", timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=60)
def fetch_ethbtc():
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": "ethereum", "vs_currencies": "btc"}, timeout=20)
    r.raise_for_status()
    return float(r.json()["ethereum"]["btc"])

@st.cache_data(ttl=60)
def fetch_prices(ids):
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": ",".join(ids), "vs_currencies": "usd"}, timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=300)
def fetch_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=20)
        r.raise_for_status()
        data = r.json()["data"][0]
        return int(data["value"]), data["value_classification"]
    except:
        return None, None

@st.cache_data(ttl=120)
def fetch_top_alts(n=50):
    r = requests.get(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": n+2,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h,7d,30d"
        }, timeout=20)
    r.raise_for_status()
    data = [x for x in r.json() if x["symbol"].upper() not in ("BTC","ETH")][:n]
    return pd.DataFrame([{
        "Rank": x["market_cap_rank"],
        "Coin": x["symbol"].upper(),
        "Name": x["name"],
        "Price ($)": x["current_price"],
        "24h %": x.get("price_change_percentage_24h_in_currency"),
        "7d %": x.get("price_change_percentage_7d_in_currency"),
        "30d %": x.get("price_change_percentage_30d_in_currency"),
        "Mkt Cap ($B)": (x["market_cap"] or 0) / 1e9
    } for x in data])

@st.cache_data(ttl=120)
def fetch_rsi_macd_volume():
    # Placeholder: Replace with real BTC historical computation
    return 72, 0.002, False

# =========================
# 🟢 Signal Builder
# =========================
def build_signals(dom, ethbtc, fg_value, rsi, macd_div, vol_div):
    sig = {
        "dom_below_first": dom is not None and dom < dom_first,
        "dom_below_second": dom is not None and dom < dom_second,
        "ethbtc_break": ethbtc is not None and ethbtc > ethbtc_break,
        "greed_high": fg_value is not None and fg_value >= 80,
        "RSI_overbought": rsi is not None and rsi > 70,
        "MACD_div": macd_div,
        "Volume_div": vol_div
    }
    sig["rotate_to_alts"] = sig["dom_below_first"] and sig["ethbtc_break"]
    sig["profit_mode"] = sig["dom_below_second"] or sig["greed_high"] or sig["RSI_overbought"] or sig["MACD_div"] or sig["Volume_div"]
    sig["full_exit_watch"] = sig["dom_below_second"] and sig["greed_high"]

    # Historical bull-run placeholders
    sig["MVRV_Z"] = True
    sig["SOPR_LTH"] = True
    sig["Exchange_Inflow"] = False
    sig["Pi_Cycle_Top"] = False
    sig["Funding_Rate"] = True
    return sig
