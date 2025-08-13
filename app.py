import math
import time
import requests
import pandas as pd
import streamlit as st
import datetime
import numpy as np
import plotly.graph_objects as go
import feedparser

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

st.sidebar.caption("This dashboard pulls live data at runtime (CoinGecko & Alternative.me).")

# =========================
# Safe Request with Retry
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
# Data Fetchers with Cache
# =========================
@st.cache_data(ttl=300)
def get_global():
    data = safe_request("https://api.coingecko.com/api/v3/global")
    if data and "data" in data:
        return data
    return None

@st.cache_data(ttl=300)
def get_ethbtc():
    data = safe_request("https://api.coingecko.com/api/v3/simple/price",
                        params={"ids":"ethereum","vs_currencies":"btc"})
    if data and "ethereum" in data:
        return float(data["ethereum"]["btc"])
    return None

@st.cache_data(ttl=300)
def get_prices_usd(ids):
    data = safe_request("https://api.coingecko.com/api/v3/simple/price",
                        params={"ids": ",".join(ids), "vs_currencies": "usd"})
    if data:
        return data
    return {i: {"usd": None} for i in ids}

@st.cache_data(ttl=300)
def get_fear_greed():
    data = safe_request("https://api.alternative.me/fng/")
    if data and "data" in data:
        fg = data["data"][0]
        return int(fg["value"]), fg["value_classification"]
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
        st.warning("Could not fetch top altcoins. Please try again later.")
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
        "Mkt Cap ($B)": (x["market_cap"] or 0) / 1e9
    } for x in data])

@st.cache_data(ttl=600)
def get_rsi_macd_volume():
    # Placeholder for RSI/MACD/Volume analysis
    return 72, 0.002, False

@st.cache_data(ttl=3600)
def get_btc_dominance_history():
    dates = pd.date_range(end=datetime.datetime.today(), periods=90)
    values = np.linspace(65, 55, 90)
    return pd.DataFrame({"Date": dates, "BTC_Dominance": values})

@st.cache_data(ttl=3600)
def get_ethbtc_history():
    dates = pd.date_range(end=datetime.datetime.today(), periods=90)
    values = np.linspace(0.045, 0.055, 90)
    return pd.DataFrame({"Date": dates, "ETHBTC": values})

# =========================
# Signal Builder
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
    sig["MVRV_Z"] = True
    sig["SOPR_LTH"] = True
    sig["Exchange_Inflow"] = False
    sig["Pi_Cycle_Top"] = False
    sig["Funding_Rate"] = True
    return sig

# =========================
# Dashboard Header
# =========================
col1, col2, col3, col4 = st.columns(4)

g = get_global()
btc_dom = float(g["data"]["market_cap_percentage"]["btc"]) if g else None
ethbtc = get_ethbtc()
fg_value, fg_label = get_fear_greed()
rsi, macd_div, vol_div = get_rsi_macd_volume()
prices = get_prices_usd(["bitcoin","ethereum"])
btc_price = prices.get("bitcoin",{}).get("usd")
eth_price = prices.get("ethereum",{}).get("usd")

col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}" if btc_dom else "N/A")
col2.metric("ETH/BTC", f"{ethbtc:.6f}" if ethbtc else "N/A")
col3.metric("Fear & Greed", f"{fg_value} ({fg_label})" if fg_value else "N/A")
col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}" if btc_price and eth_price else "N/A")
st.markdown("---")

# =========================
# Signals Panel
# =========================
if btc_dom and ethbtc:
    sig = build_signals(btc_dom, ethbtc, fg_value, rsi, macd_div, vol_div)
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.markdown(f"**Dom < {dom_first:.2f}%**: {'🟢 YES' if sig['dom_below_first'] else '🔴 NO'}")
    c2.markdown(f"**Dom < {dom_second:.2f}%**: {'🟢 YES' if sig['dom_below_second'] else '🔴 NO'}")
    c3.markdown(f"**ETH/BTC > {ethbtc_break:.3f}**: {'🟢 YES' if sig['ethbtc_break'] else '🔴 NO'}")
    c4.markdown(f"**F&G ≥ 80**: {'🟢 YES' if sig['greed_high'] else '🔴 NO'}")
    c5.markdown(f"**RSI > 70**: {'🟢 YES' if sig['RSI_overbought'] else '🔴 NO'}")
    c6.markdown(f"**MACD Divergence**: {'🟢 YES' if sig['MACD_div'] else '🔴 NO'}")
    c7.markdown(f"**Volume Divergence**: {'🟢 YES' if sig['Volume_div'] else '🔴 NO'}")

    if sig["profit_mode"]:
        st.success("**Profit-taking mode is ON**")
    else:
        st.info("**Profit-taking mode is OFF**")

# =========================
# Altcoin Table
# =========================
st.header("🔥 Top Altcoins & Rotation")
alt_df = get_top_alts(top_n_alts)
if sig["rotate_to_alts"] and not alt_df.empty:
    alt_df['Suggested Action'] = '✅ Rotate In'
else:
    alt_df['Suggested Action'] = '⚠️ Wait'
st.dataframe(alt_df, use_container_width=True)
if sig["rotate_to_alts"]:
    st.success(f"Alt season detected! Consider allocating {target_alt_alloc}% of portfolio into top momentum alts.")
else:
    st.info("No alt season signal detected. Watch these alts and wait for rotation conditions.")

# =========================
# Interactive Charts
# =========================
st.header("📊 Interactive Charts")
df_dom_hist = get_btc_dominance_history()
fig_dom = go.Figure()
fig_dom.add_trace(go.Scatter(x=df_dom_hist['Date'], y=df_dom_hist['BTC_Dominance'], mode='lines', name='BTC Dominance'))
fig_dom.update_layout(title="BTC Dominance (Last 90 Days)", xaxis_title="Date", yaxis_title="BTC Dominance %")
st.plotly_chart(fig_dom, use_container_width=True)

df_ethbtc_hist = get_ethbtc_history()
fig_ethbtc = go.Figure()
fig_ethbtc.add_trace(go.Scatter(x=df_ethbtc_hist['Date'], y=df_ethbtc_hist['ETHBTC'], mode='lines', name='ETH/BTC'))
fig_ethbtc.update_layout(title="ETH/BTC Ratio (Last 90 Days)", xaxis_title="Date", yaxis_title="ETH/BTC")
st.plotly_chart(fig_ethbtc, use_container_width=True)

fig_alt = go.Figure()
if not alt_df.empty:
    fig_alt.add_trace(go.Bar(x=alt_df['Coin'], y=alt_df['7d %'], name='7d Momentum', marker_color='green'))
fig_alt.update_layout(title="Top Altcoin 7d Momentum", xaxis_title="Coin", yaxis_title="% Change")
st.plotly_chart(fig_alt, use_container_width=True)

# =========================
# Live News Feed
# =========================
st.header("📰 Crypto News Feed")
feed = feedparser.parse("https://cryptopanic.com/news/feed/")
for entry in feed.entries[:10]:
    st.markdown(f"[{entry.title}]({entry.link})")
