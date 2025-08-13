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

st.sidebar.caption("Live data from CoinGecko & Alternative.me. Refresh may take 5–10s.")

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
    data = safe_request("https://api.coingecko.com/api/v3/global")
    return data if data else None

@st.cache_data(ttl=300)
def get_ethbtc():
    data = safe_request("https://api.coingecko.com/api/v3/simple/price", params={"ids":"ethereum","vs_currencies":"btc"})
    return float(data["ethereum"]["btc"]) if data and "ethereum" in data else None

@st.cache_data(ttl=300)
def get_prices_usd(ids):
    data = safe_request("https://api.coingecko.com/api/v3/simple/price", params={"ids": ",".join(ids), "vs_currencies": "usd"})
    return data if data else {i: {"usd": None} for i in ids}

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

# =========================
# Historical placeholders
# =========================
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
# Profit Ladder
# =========================
def build_profit_ladder(entry_price, step_pct, sell_pct, max_steps):
    ladder = []
    for i in range(1, max_steps+1):
        price_target = entry_price * (1 + step_pct/100 * i)
        ladder.append({"Step": i, "Price Target": price_target, "% Gain": step_pct*i, "Sell %": sell_pct})
    return pd.DataFrame(ladder)

# =========================
# Signals Builder
# =========================
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
# Dashboard Header
# =========================
col1, col2, col3, col4 = st.columns(4)
g = get_global()
btc_dom = float(g["data"]["market_cap_percentage"].get("btc",0)) if g and "data" in g and "market_cap_percentage" in g["data"] else None
ethbtc_val = get_ethbtc()
fg_value, fg_label = get_fear_greed()
prices = get_prices_usd(["bitcoin","ethereum"])
btc_price = prices.get("bitcoin",{}).get("usd")
eth_price = prices.get("ethereum",{}).get("usd")

col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}" if btc_dom else "N/A")
col2.metric("ETH/BTC", f"{ethbtc_val:.6f}" if ethbtc_val else "N/A")
col3.metric("Fear & Greed", f"{fg_value} ({fg_label})" if fg_value else "N/A")
col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}" if btc_price and eth_price else "N/A")
st.markdown("---")

# =========================
# Signals Panel
# =========================
sig = None
if btc_dom is not None and ethbtc_val is not None:
    sig = build_signals(btc_dom, ethbtc_val, fg_value)
else:
    sig = {
        "rotate_to_alts": False,
        "profit_mode": False,
        "dom_below_first": False,
        "dom_below_second": False,
        "ethbtc_break": False,
        "greed_high": False
    }

st.subheader("⚡ Signals")
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"**Dom < {dom_first:.2f}%**: {'🟢 YES' if sig['dom_below_first'] else '🔴 NO'}")
c2.markdown(f"**Dom < {dom_second:.2f}%**: {'🟢 YES' if sig['dom_below_second'] else '🔴 NO'}")
c3.markdown(f"**ETH/BTC > {ethbtc_break:.3f}**: {'🟢 YES' if sig['ethbtc_break'] else '🔴 NO'}")
c4.markdown(f"**F&G ≥ 80**: {'🟢 YES' if sig['greed_high'] else '🔴 NO'}")
if sig["profit_mode"]:
    st.success("Profit-taking mode is ON")
else:
    st.info("Profit-taking mode is OFF")

# =========================
# Profit Ladder Table
# =========================
st.subheader("💰 Profit Ladder")
btc_ladder = build_profit_ladder(entry_btc, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
eth_ladder = build_profit_ladder(entry_eth, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
st.markdown("**BTC Ladder**")
st.dataframe(btc_ladder)
st.markdown("**ETH Ladder**")
st.dataframe(eth_ladder)

# =========================
# Altcoin Table
# =========================
st.subheader("🔥 Top Altcoins & Rotation")
alt_df = get_top_alts(top_n_alts)
if sig["rotate_to_alts"] and not alt_df.empty:
    alt_df['Suggested Action'] = '✅ Rotate In'
else:
    alt_df['Suggested Action'] = '⚠️ Wait'
st.dataframe(alt_df, use_container_width=True)
if sig["rotate_to_alts"]:
    st.success(f"Alt season detected! Consider allocating {target_alt_alloc}% into top momentum alts.")
else:
    st.info("No alt season signal detected. Stay in BTC / stablecoins.")

# =========================
# BTC / ETH Interactive Chart
# =========================
st.subheader("📈 BTC / ETH Interactive Chart")

# Adjustable settings
timeframe = st.selectbox("Timeframe", ["7d", "30d", "90d", "180d", "1y"])
price_type = st.radio("Price Type", ["Closing Price", "% Change"])
show_ma = st.multiselect("Moving Averages", ["7-day", "30-day", "50-day", "200-day"])
compare_eth = st.checkbox("Compare ETH vs BTC", value=True)

# Map timeframe to number of days
tf_days = {"7d":7, "30d":30, "90d":90, "180d":180, "1y":365}[timeframe]

# Fetch historical prices from CoinGecko
@st.cache_data(ttl=600)
def get_historical_price(coin_id, days):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval":"daily"}
    data = safe_request(url, params)
    if data and "prices" in data:
        df = pd.DataFrame(data["prices"], columns=["Timestamp","Price"])
        df["Date"] = pd.to_datetime(df["Timestamp"], unit="ms")
        df.set_index("Date", inplace=True)
        df.drop("Timestamp", axis=1, inplace=True)
        return df
    return pd.DataFrame()

btc_hist = get_historical_price("bitcoin", tf_days)
eth_hist = get_historical_price("ethereum", tf_days)

# Compute % change if selected
if price_type == "% Change":
    btc_hist["Price"] = btc_hist["Price"].pct_change()*100
    if compare_eth:
        eth_hist["Price"] = eth_hist["Price"].pct_change()*100

# Add moving averages
for ma in show_ma:
    days_ma = int(ma.split("-")[0])
    btc_hist[ma] = btc_hist["Price"].rolling(days_ma).mean()
    if compare_eth:
        eth_hist[ma] = eth_hist["Price"].rolling(days_ma).mean()

# Plot
fig = go.Figure()
fig.add_trace(go.Scatter(x=btc_hist.index, y=btc_hist["Price"], name="BTC", line=dict(color="orange")))
if compare_eth:
    fig.add_trace(go.Scatter(x=eth_hist.index, y=eth_hist["Price"], name="ETH", line=dict(color="blue")))

# Add MAs
for ma in show_ma:
    fig.add_trace(go.Scatter(x=btc_hist.index, y=btc_hist[ma], name=f"BTC {ma}", line=dict(dash="dot")))
    if compare_eth:
        fig.add_trace(go.Scatter(x=eth_hist.index, y=eth_hist[ma], name=f"ETH {ma}", line=dict(dash="dot")))

fig.update_layout(title=f"BTC / ETH Price ({timeframe})", xaxis_title="Date", yaxis_title="Price" + (" (%)" if price_type=="% Change" else " ($)"))
st.plotly_chart(fig, use_container_width=True)

# =========================
# Altcoin Momentum Charts
# =========================


fig_alt = go.Figure()
if not alt_df.empty:
    fig_alt.add_trace(go.Bar(x=alt_df['Coin'], y=alt_df['7d %'], name='7d Momentum', marker_color='green'))
fig_alt.update_layout(title="Top Altcoin 7d Momentum", xaxis_title="Coin", yaxis_title="% Change")
st.plotly_chart(fig_alt, use_container_width=True)

# =========================
# Live Crypto News Feed
# =========================
st.subheader("📰 Crypto News Feed")
feed = feedparser.parse("https://cryptopanic.com/news/feed/")
for entry in feed.entries[:10]:
    st.markdown(f"[{entry.title}]({entry.link})")
