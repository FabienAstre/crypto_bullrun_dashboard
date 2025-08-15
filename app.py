import math
import time
import requests
import pandas as pd
import streamlit as st
import datetime
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf

st.set_page_config(page_title="Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")

# =========================
# Sidebar Parameters
# =========================
st.sidebar.header("Dashboard Parameters")

# --- Dominance & ETH/BTC ---
st.sidebar.subheader("Dominance & ETH/BTC Triggers")
dom_first = st.sidebar.number_input("BTC Dominance: 1st break (%)", 0.0, 100.0, 58.29, 0.01, format="%.2f")
dom_second = st.sidebar.number_input("BTC Dominance: strong confirm (%)", 0.0, 100.0, 54.66, 0.01, format="%.2f")
ethbtc_break = st.sidebar.number_input("ETH/BTC breakout level", 0.0, 1.0, 0.054, 0.001, format="%.3f")

# --- Profit Ladder ---
st.sidebar.subheader("Profit-Taking Plan")
entry_btc = st.sidebar.number_input("Your BTC average entry ($)", 0.0, 1000000.0, 40000.0, 100.0)
entry_eth = st.sidebar.number_input("Your ETH average entry ($)", 0.0, 1000000.0, 2000.0, 10.0)
ladder_step_pct = st.sidebar.slider("Take profit every X% gain", 1, 50, 10)
sell_pct_per_step = st.sidebar.slider("Sell Y% each step", 1, 50, 10)
max_ladder_steps = st.sidebar.slider("Max ladder steps", 1, 30, 8)

# --- Trailing Stop ---
st.sidebar.subheader("Trailing Stop (Optional)")
use_trailing = st.sidebar.checkbox("Enable trailing stop", value=True)
trail_pct = st.sidebar.slider("Trailing stop (%)", 5, 50, 20)

# --- Alt Rotation ---
st.sidebar.subheader("Alt Rotation")
target_alt_alloc = st.sidebar.slider("Target Alt allocation when signals fire (%)", 0, 100, 40)
top_n_alts = st.sidebar.slider("Top N alts to scan (by market cap)", 10, 100, 50, 10)

st.sidebar.caption("This dashboard pulls live data at runtime (CoinGecko, Alternative.me, Yahoo Finance).")

# =========================
# Data Fetchers
# =========================
@st.cache_data(ttl=300)
def get_global():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

@st.cache_data(ttl=300)
def get_ethbtc():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "ethereum", "vs_currencies": "btc"},
            timeout=20
        )
        r.raise_for_status()
        return float(r.json()["ethereum"]["btc"])
    except Exception:
        return None

@st.cache_data(ttl=300)
def get_price_ratio(pair_ids):
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(pair_ids), "vs_currencies": "usd"},
            timeout=20
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

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
                "price_change_percentage": "24h,7d"
            },
            timeout=20
        )
        r.raise_for_status()
        data = [x for x in r.json() if x["symbol"].upper() not in ("BTC", "ETH")][:n]
        df = pd.DataFrame([{
            "Rank": x["market_cap_rank"],
            "Coin": x["symbol"].upper(),
            "Name": x["name"],
            "Price ($)": x["current_price"],
            "24h %": x.get("price_change_percentage_24h_in_currency"),
            "7d %": x.get("price_change_percentage_7d_in_currency"),
            "Mkt Cap ($B)": (x["market_cap"] or 0)/1e9
        } for x in data])
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_altcap_ex_btc():
    try:
        g = get_global()
        if not g:
            return None
        total_mcap = g["data"]["total_market_cap"]["usd"]
        btc_mcap = total_mcap * g["data"]["market_cap_percentage"]["btc"] / 100
        return total_mcap - btc_mcap
    except Exception:
        return None

@st.cache_data(ttl=300)
def get_solbtc():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "solana", "vs_currencies": "btc"},
            timeout=20
        )
        r.raise_for_status()
        return float(r.json()["solana"]["btc"])
    except Exception:
        return None

@st.cache_data(ttl=300)
def get_eth_gas():
    try:
        r = requests.get("https://api.etherscan.io/api?module=gastracker&action=gasoracle", timeout=20)
        r.raise_for_status()
        data = r.json()
        return int(data["result"]["ProposeGasPrice"])
    except Exception:
        return None

@st.cache_data(ttl=300)
def get_funding_rate():
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT", timeout=20)
        r.raise_for_status()
        return float(r.json()["lastFundingRate"]) * 100  # %
    except Exception:
        return None

@st.cache_data(ttl=300)
def get_index_trend(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if len(df) < 50:
            return None
        ma50 = df["Close"].rolling(50).mean().iloc[-1]
        ma200 = df["Close"].rolling(200).mean().iloc[-1] if len(df) >= 200 else None
        price = df["Close"].iloc[-1]
        return price, ma50, ma200
    except Exception:
        return None

@st.cache_data(ttl=120)
def get_rsi_macd_volume():
    return 72, 0.002, False  # placeholder

# =========================
# Build Signals
# =========================
def build_signals():
    g = get_global()
    btc_dom = float(g["data"]["market_cap_percentage"]["btc"]) if g else None
    ethbtc = get_ethbtc()
    prices = get_price_ratio(["bitcoin", "ethereum"])
    btc_price = prices.get("bitcoin", {}).get("usd")
    eth_price = prices.get("ethereum", {}).get("usd")
    fg_value, _ = get_fear_greed()
    rsi, macd_div, vol_div = get_rsi_macd_volume()
    altcap = get_altcap_ex_btc()
    solbtc = get_solbtc()
    gas = get_eth_gas()
    funding = get_funding_rate()
    dxy = get_index_trend("DX-Y.NYB")
    nasdaq = get_index_trend("^IXIC")

    signals = {
        # Macro Trend
        "BTC > 200D MA": btc_price is not None and dxy is not None and btc_price > get_index_trend("BTC-USD")[2],
        "DXY Downtrend": dxy is not None and dxy[0] < dxy[1],
        "NASDAQ Uptrend": nasdaq is not None and nasdaq[0] > nasdaq[1],

        # Rotation
        "Dom < First Break": btc_dom is not None and btc_dom < dom_first,
        "Dom < Strong Confirm": btc_dom is not None and btc_dom < dom_second,
        "ETH/BTC Breakout": ethbtc is not None and ethbtc > ethbtc_break,
        "Altcap Breakout": altcap is not None and altcap > 200_000_000_000,  # example threshold
        "Sol/BTC Breakout": solbtc is not None and solbtc > 0.0015,

        # Speculation Heat
        "F&G ≥ 80": fg_value is not None and fg_value >= 80,
        "RSI > 70": rsi is not None and rsi > 70,
        "MACD Divergence": macd_div,
        "Volume Divergence": vol_div,
        "Funding Rate High": funding is not None and funding > 0.2,
        "Gas Spike": gas is not None and gas > 80
    }

    return signals, btc_dom, ethbtc, fg_value, btc_price, eth_price

# =========================
# Display Metrics
# =========================
signals, btc_dom, ethbtc, fg_value, btc_price, eth_price = build_signals()

col1, col2, col3, col4 = st.columns(4)
col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}" if btc_dom else "N/A")
col2.metric("ETH/BTC", f"{ethbtc:.6f}" if ethbtc else "N/A")
col3.metric("Fear & Greed", f"{fg_value}" if fg_value else "N/A")
col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}" if btc_price and eth_price else "N/A")

# =========================
# Signal Panel
# =========================
st.markdown("### 📊 Market Signals Overview")
signal_explanations = {
    "BTC > 200D MA": "BTC price above its 200-day moving average → bullish macro trend.",
    "DXY Downtrend": "US dollar weakening → historically bullish for crypto.",
    "NASDAQ Uptrend": "Stock market risk-on sentiment supports crypto rally.",
    "Dom < First Break": "BTC losing dominance → early alt rotation.",
    "Dom < Strong Confirm": "Strong altcoin rotation confirmed.",
    "ETH/BTC Breakout": "Ethereum outperforming Bitcoin.",
    "Altcap Breakout": "Altcoin market cap (excl. BTC) breaking resistance.",
    "Sol/BTC Breakout": "Solana rotation signal.",
    "F&G ≥ 80": "Extreme greed in the market.",
    "RSI > 70": "BTC overbought zone.",
    "MACD Divergence": "Momentum divergence spotted.",
    "Volume Divergence": "Volume not confirming price action.",
    "Funding Rate High": "Over-leveraged longs in the market.",
    "Gas Spike": "Ethereum gas fees unusually high → speculative activity."
}

cols_per_row = 3
items = list(signal_explanations.items())
for i in range(0, len(items), cols_per_row):
    cols = st.columns(min(cols_per_row, len(items) - i))
    for j, (name, desc) in enumerate(items[i:i+cols_per_row]):
        active = signals.get(name, False)
        status = "🟢" if active else "🔴"
        cols[j].markdown(f"{status} **{name}**\n- {desc}")

# =========================
# Profit Ladder
# =========================
st.markdown("---")
st.header("🎯 Profit-Taking Ladder")

def build_ladder(entry, step_pct, sell_pct, max_steps):
    rows = []
    if entry <= 0:
        return pd.DataFrame(rows)
    for i in range(1, max_steps + 1):
        target = entry * (1 + step_pct/100.0)**i
        rows.append({
            "Step #": i,
            "Target Price": round(target, 2),
            "Gain from Entry (%)": round((target / entry - 1) * 100, 2),
            "Sell This Step (%)": sell_pct
        })
    return pd.DataFrame(rows)

btc_ladder = build_ladder(entry_btc, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
eth_ladder = build_ladder(entry_eth, ladder_step_pct, sell_pct_per_step, max_ladder_steps)

cL, cR = st.columns(2)
with cL:
    st.subheader("BTC Ladder")
    st.dataframe(btc_ladder, use_container_width=True)
with cR:
    st.subheader("ETH Ladder")
    st.dataframe(eth_ladder, use_container_width=True)

# =========================
# Trailing Stops
# =========================
if use_trailing and btc_price:
    st.markdown("---")
    st.subheader("🛡️ Trailing Stop Guidance")
    btc_stop = round(btc_price * (1 - trail_pct / 100.0), 2)
    eth_stop = round(eth_price * (1 - trail_pct / 100.0), 2) if eth_price else None
    st.write(f"- Suggested BTC stop: ${btc_stop:,.2f}")
    if eth_stop:
        st.write(f"- Suggested ETH stop: ${eth_stop:,.2f}")

# =========================
# Altcoin Dashboard
# =========================
st.markdown("---")
st.header("🔥 Altcoin Momentum & Rotation Dashboard (Top 30)")

alt_df = get_top_alts_safe(top_n_alts)
if not alt_df.empty:
    alt_df = alt_df.sort_values(by='7d %', ascending=False).head(30)
    min_val = alt_df[['7d %', '24h %']].min().min()
    max_val = alt_df[['7d %', '24h %']].max().max()
    alt_df['Rotation Score (%)'] = alt_df.apply(
        lambda x: round(50*(x['7d %'] - min_val)/(max_val - min_val) +
                        50*(x['24h %'] - min_val)/(max_val - min_val), 2),
        axis=1
    )
    alt_df['Suggested Action'] = ['✅ Rotate In' if signals.get('Dom < First Break') and signals.get('ETH/BTC Breakout') else '⚠️ Wait'] * len(alt_df)

    chart_option = st.selectbox("Select Altcoin Chart", ["Rotation Score (%)", "7-Day % Price Change", "Market Cap vs 7-Day % Change Bubble"])

    if chart_option == "Rotation Score (%)":
        fig = px.bar(alt_df, x='Coin', y='Rotation Score (%)', color='Rotation Score (%)',
                     color_continuous_scale='RdYlGn', title="Rotation Score (%) by Altcoin")
    elif chart_option == "7-Day % Price Change":
        fig = px.bar(alt_df, x='Coin', y='7d %', color='7d %', color_continuous_scale='RdYlGn', text='7d %',
                     title="7-Day % Price Change")
    else:
        fig = px.scatter(alt_df, x='Mkt Cap ($B)', y='7d %', size='Mkt Cap ($B)', color='7d %',
                         hover_name='Coin', color_continuous_scale='RdYlGn_r', size_max=60,
                         title="Market Cap vs 7-Day % Change Bubble")
        fig.update_layout(xaxis_title="Market Cap ($B)", yaxis_title="7-Day % Change")

    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("No altcoin data available for top selection.")
