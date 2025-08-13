import time
import requests
import pandas as pd
import numpy as np
import streamlit as st
import datetime
import plotly.graph_objects as go
import feedparser

st.set_page_config(page_title="Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")

# =========================
# Sidebar Parameters
# =========================
st.sidebar.header("Dashboard Parameters")

st.sidebar.subheader("Dominance & ETH/BTC Triggers")
dom_first = st.sidebar.number_input("BTC Dominance: 1st break (%)", 0.0, 100.0, 58.29, 0.01)
dom_second = st.sidebar.number_input("BTC Dominance: strong confirm (%)", 0.0, 100.0, 54.66, 0.01)
ethbtc_break = st.sidebar.number_input("ETH/BTC breakout level", 0.0, 1.0, 0.054, 0.001)

st.sidebar.subheader("Profit-Taking Plan")
entry_btc = st.sidebar.number_input("BTC average entry ($)", 0.0, 1000000.0, 40000.0, 100.0)
entry_eth = st.sidebar.number_input("ETH average entry ($)", 0.0, 1000000.0, 2000.0, 10.0)
ladder_step_pct = st.sidebar.slider("Take profit every X% gain", 1, 50, 10)
sell_pct_per_step = st.sidebar.slider("Sell Y% each step", 1, 50, 10)
max_ladder_steps = st.sidebar.slider("Max ladder steps", 1, 30, 8)

st.sidebar.subheader("Trailing Stop (Optional)")
use_trailing = st.sidebar.checkbox("Enable trailing stop", value=True)
trail_pct = st.sidebar.slider("Trailing stop (%)", 5, 50, 20)

st.sidebar.subheader("Alt Rotation")
target_alt_alloc = st.sidebar.slider("Target Alt allocation when signals fire (%)", 0, 100, 40)
top_n_alts = st.sidebar.slider("Top N alts to scan", 10, 100, 50, 10)

st.sidebar.subheader("New Indicator Settings")
alt_season_threshold = st.sidebar.slider("Alt Season Ratio threshold (Alts/BTC)", 0.05, 0.50, 0.15, 0.01)
vol_spike_multiple = st.sidebar.slider("Volume spike: X × 7d average", 1.0, 5.0, 2.0, 0.1)

st.sidebar.caption("Live data from CoinGecko & Alternative.me. Cached with retries & fallbacks.")

# =========================
# Safe API request with retry/backoff
# =========================
def safe_request(url, params=None, max_retries=5, backoff=2):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                time.sleep(backoff ** attempt)
            else:
                r.raise_for_status()
        except requests.exceptions.RequestException:
            time.sleep(backoff ** attempt)
    return None

# =========================
# Data Fetching with Caching
# =========================
@st.cache_data(ttl=300)
def get_global():
    return safe_request("https://api.coingecko.com/api/v3/global")

@st.cache_data(ttl=300)
def get_ethbtc():
    data = safe_request("https://api.coingecko.com/api/v3/simple/price",
                        params={"ids":"ethereum","vs_currencies":"btc"})
    return float(data["ethereum"]["btc"]) if data and "ethereum" in data else None

@st.cache_data(ttl=300)
def get_prices_usd(ids):
    data = safe_request("https://api.coingecko.com/api/v3/simple/price",
                        params={"ids": ",".join(ids), "vs_currencies": "usd"})
    return data if data else {i: {"usd": None} for i in ids}

@st.cache_data(ttl=300)
def get_fear_greed():
    data = safe_request("https://api.alternative.me/fng/")
    if data and "data" in data and data["data"]:
        fg = data["data"][0]
        return int(fg.get("value", 50)), fg.get("value_classification", "Neutral")
    return None, None

@st.cache_data(ttl=600)
def get_top_alts(n=50):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": n+2,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d,30d"
    }
    data = safe_request(url, params)
    if not data:
        return pd.DataFrame(columns=["Rank", "Coin", "Name", "Price ($)", "24h %", "7d %", "30d %", "Mkt Cap ($B)"])
    data = [x for x in data if x["symbol"].upper() not in ("BTC","ETH")][:n]
    return pd.DataFrame([{
        "Rank": x["market_cap_rank"],
        "Coin": x["symbol"].upper(),
        "Name": x["name"],
        "Price ($)": x["current_price"],
        "24h %": x.get("price_change_percentage_24h_in_currency"),
        "7d %": x.get("price_change_percentage_7d_in_currency"),
        "30d %": x.get("price_change_percentage_30d_in_currency"),
        "Mkt Cap ($B)": (x.get("market_cap") or 0) / 1e9
    } for x in data])

# =========================
# Helper calcs
# =========================
def build_profit_ladder(entry_price, step_pct, sell_pct, max_steps):
    ladder = []
    for i in range(1, max_steps+1):
        price_target = entry_price * (1 + step_pct/100 * i)
        ladder.append({"Step": i, "Price Target": price_target, "% Gain": step_pct*i, "Sell %": sell_pct})
    return pd.DataFrame(ladder)

def build_signals(dom, ethbtc, fg_value):
    sig = {
        "dom_below_first": dom is not None and dom < dom_first,
        "dom_below_second": dom is not None and dom < dom_second,
        "ethbtc_break": ethbtc is not None and ethbtc > ethbtc_break,
        "greed_high": fg_value is not None and fg_value >= 80,
    }
    sig["rotate_to_alts"] = sig["dom_below_first"] and sig["ethbtc_break"]
    sig["profit_mode"] = sig["dom_below_second"] or sig["greed_high"]
    return sig

# =========================
# Header Metrics
# =========================
col1, col2, col3, col4 = st.columns(4)

g = get_global()
btc_dom = None
if g and "data" in g and "market_cap_percentage" in g["data"]:
    try:
        btc_dom = float(g["data"]["market_cap_percentage"].get("btc", 0))
    except:
        btc_dom = None
if btc_dom is None:
    st.warning("⚠️ BTC Dominance could not be fetched. Using fallback value for signals.")
    btc_dom = 60.0

ethbtc_val = get_ethbtc()
if ethbtc_val is None:
    st.warning("⚠️ ETH/BTC could not be fetched. Signals may be inaccurate.")
    ethbtc_val = 0.05

fg_value, fg_label = get_fear_greed()
if fg_value is None:
    st.warning("⚠️ Fear & Greed index could not be fetched. Using Neutral fallback.")
    fg_value, fg_label = 50, "Neutral"

prices = get_prices_usd(["bitcoin","ethereum"])
btc_price = prices.get("bitcoin",{}).get("usd")
eth_price = prices.get("ethereum",{}).get("usd")

col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}" if btc_dom is not None else "N/A")
col2.metric("ETH/BTC", f"{ethbtc_val:.6f}" if ethbtc_val is not None else "N/A")
col3.metric("Fear & Greed", f"{fg_value} ({fg_label})" if fg_value is not None else "N/A")
col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}" if btc_price and eth_price else "N/A")
st.markdown("---")

# =========================
# Core Signals with Explanation
# =========================
sig = build_signals(btc_dom, ethbtc_val, fg_value)
st.subheader("⚡ Signals & Suggested Actions")

def signal_text(name, flag, explanation, action):
    icon = "🟢 YES" if flag else "🔴 NO"
    st.markdown(f"**{name}:** {icon}  \n*Explanation:* {explanation}  \n*Action:* {action}")

signal_text(
    f"Dom < {dom_first:.2f}%",
    sig["dom_below_first"],
    "BTC dominance dropping below first threshold indicates altcoins may start outperforming BTC.",
    "Prepare to allocate part of your portfolio into top altcoins."
)
signal_text(
    f"Dom < {dom_second:.2f}%",
    sig["dom_below_second"],
    "BTC dominance dropping further suggests altcoin season is stronger and profit-taking on BTC might be considered.",
    "Consider selling portions of BTC for profit and rotating to alts/stablecoins."
)
signal_text(
    f"ETH/BTC > {ethbtc_break:.3f}",
    sig["ethbtc_break"],
    "ETH is outperforming BTC.",
    "Opportunity to rotate from BTC to ETH or ETH-rich alts."
)
signal_text(
    f"F&G ≥ 80",
    sig["greed_high"],
    "Market is extremely greedy; high risk of short-term pullbacks.",
    "Take partial profits and tighten stops."

)
if sig["profit_mode"]:
    st.success("💡 Profit-taking mode is ON: tighten stops or sell portions of holdings.")
else:
    st.info("Profit-taking mode is OFF: no immediate selling signal.")

# =========================
# Profit Ladder Table
# =========================
st.subheader("💰 Combined Profit Ladder (BTC & ETH)")
btc_ladder = build_profit_ladder(entry_btc, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
btc_ladder["Coin"] = "BTC"
eth_ladder = build_profit_ladder(entry_eth, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
eth_ladder["Coin"] = "ETH"
combined_ladder = pd.concat([btc_ladder, eth_ladder], ignore_index=True)
combined_ladder = combined_ladder[["Coin", "Step", "Price Target", "% Gain", "Sell %"]]
st.dataframe(combined_ladder, use_container_width=True)

# =========================
# Altcoin Table & Buying Chart
# =========================
st.subheader("🔥 Top Altcoins & Suggested Action")
alt_df = get_top_alts(top_n_alts)
if sig["rotate_to_alts"] and not alt_df.empty:
    alt_df['Suggested Action'] = '✅ Rotate In'
else:
    alt_df['Suggested Action'] = '⚠️ Wait'
st.dataframe(alt_df, use_container_width=True)

# Altcoin Buying Chart (Top N by 7d %)
st.subheader("📊 Altcoin 7d Performance Chart")
if not alt_df.empty and "7d %" in alt_df.columns:
    fig_alt = go.Figure()
    fig_alt.add_trace(go.Bar(
        x=alt_df['Coin'],
        y=alt_df['7d %'],
        marker_color=['green' if x>=0 else 'red' for x in alt_df['7d %']],
        name='7d Performance'
    ))
    fig_alt.update_layout(
        title="Top Altcoin 7-Day % Change",
        xaxis_title="Coin",
        yaxis_title="% Change",
    )
    st.plotly_chart(fig_alt, use_container_width=True)

# =========================
# Live Crypto News Feed
# =========================
st.subheader("📰 Crypto News Feed")
try:
    feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/")
    if feed.entries:
        for entry in feed.entries[:10]:
            st.markdown(f"[{entry.title}]({entry.link})")
    else:
        st.info("No news available right now. Try refreshing in a few seconds.")
except Exception as e:
    st.warning(f"News feed could not be loaded: {e}")
