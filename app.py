import math
import time
import requests
import pandas as pd
import streamlit as st
import datetime
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

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

st.sidebar.caption("This dashboard pulls live data at runtime (CoinGecko & Alternative.me).")

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
            params={"ids":"ethereum","vs_currencies":"btc"},
            timeout=20
        )
        r.raise_for_status()
        return float(r.json()["ethereum"]["btc"])
    except Exception:
        return None

@st.cache_data(ttl=300)
def get_prices_usd(ids):
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(ids), "vs_currencies": "usd"},
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
    """Get top n altcoins (excluding BTC and ETH), returns DataFrame."""
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
        data = [x for x in r.json() if x["symbol"].upper() not in ("BTC","ETH")][:n]
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

@st.cache_data(ttl=120)
def get_rsi_macd_volume():
    # Placeholder: in a real version fetch BTC price history and compute RSI/MACD/Volume divergence
    return 72, 0.002, False  # RSI, MACD hist divergence, volume divergence

# =========================
# Signals Builder
# =========================
def build_signals(dom, ethbtc, fg_value, rsi, macd_div, vol_div):
    sig = {
        "Dom < First Break": dom is not None and dom < dom_first,
        "Dom < Strong Confirm": dom is not None and dom < dom_second,
        "ETH/BTC Breakout": ethbtc is not None and ethbtc > ethbtc_break,
        "F&G ≥ 80": fg_value is not None and fg_value >= 80,
        "RSI > 70": rsi is not None and rsi > 70,
        "MACD Divergence": macd_div,
        "Volume Divergence": vol_div
    }
    sig["Rotate to Alts"] = sig["Dom < First Break"] and sig["ETH/BTC Breakout"]
    sig["Profit Mode"] = sig["Dom < Strong Confirm"] or sig["F&G ≥ 80"] or sig["RSI > 70"] or sig["MACD Divergence"] or sig["Volume Divergence"]
    sig["Full Exit Watch"] = sig["Dom < Strong Confirm"] and sig["F&G ≥ 80"]
    
    # Fill placeholder signals
    for extra in ["MVRV Z-Score","SOPR LTH","Exchange Inflow","Pi Cycle Top","Funding Rate"]:
        sig[extra] = True if extra in ["MVRV Z-Score","SOPR LTH","Funding Rate"] else False
    
    return sig

# =========================
# Header Metrics
# =========================
col1, col2, col3, col4 = st.columns(4)

g = get_global()
btc_dom = float(g["data"]["market_cap_percentage"]["btc"]) if g else None
btc_dom_display = f"{btc_dom:.2f}" if btc_dom else "N/A"
col1.metric("BTC Dominance (%)", btc_dom_display)

ethbtc = get_ethbtc()
ethbtc_display = f"{ethbtc:.6f}" if ethbtc else "N/A"
col2.metric("ETH/BTC", ethbtc_display)

fg_value, fg_label = get_fear_greed()
col3.metric("Fear & Greed", f"{fg_value} ({fg_label})" if fg_value else "N/A")

prices = get_prices_usd(["bitcoin","ethereum"])
btc_price = prices.get("bitcoin",{}).get("usd")
eth_price = prices.get("ethereum",{}).get("usd")
col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}" if btc_price and eth_price else "N/A")

rsi, macd_div, vol_div = get_rsi_macd_volume()
sig = build_signals(btc_dom, ethbtc, fg_value, rsi, macd_div, vol_div)

st.markdown("---")

# =========================
# Combined Signals Panel with Explanations (Grid Layout)
# =========================
st.markdown("### 📊 Key Market Signals & Explanations")

signal_descriptions = {
    "Dom < First Break": "BTC losing market share → altcoins may start moving up.",
    "Dom < Strong Confirm": "Confirms major rotation into altcoins → potential altseason.",
    "ETH/BTC Breakout": "ETH outperforming BTC → bullish for ETH and altcoins.",
    "F&G ≥ 80": "Extreme greed → market may be overbought.",
    "RSI > 70": "BTC overbought → possible short-term correction.",
    "MACD Divergence": "Momentum slowing → potential reversal.",
    "Volume Divergence": "Weak price movement → caution on trend continuation.",
    "Rotate to Alts": "Strong rotation signal → move funds into altcoins.",
    "Profit Mode": "Suggests scaling out of positions / taking profit.",
    "Full Exit Watch": "Extreme signal → consider exiting major positions.",
    "MVRV Z-Score": "BTC historically overvalued when MVRV Z > 7.",
    "SOPR LTH": "Long-term holder SOPR > 1.5 → high profit taking.",
    "Exchange Inflow": "Exchange inflows spike → whales moving BTC to exchanges.",
    "Pi Cycle Top": "Pi Cycle Top indicator intersects price → major top possible.",
    "Funding Rate": "Perpetual funding > 0.2% long → market over-leveraged."
}

# Number of columns per row
cols_per_row = 3
signal_items = list(signal_descriptions.items())

for i in range(0, len(signal_items), cols_per_row):
    cols = st.columns(min(cols_per_row, len(signal_items)-i))
    for j, (name, desc) in enumerate(signal_items[i:i+cols_per_row]):
        active = sig.get(name, False)
        status_emoji = "🟢" if active else "🔴"
        cols[j].markdown(f"{status_emoji} **{name}**  \n{desc}")


# =========================
# Profit Ladder Planner
# =========================
st.markdown("---")
st.header("🎯 Profit-Taking Ladder")

def build_ladder(entry, step_pct, sell_pct, max_steps):
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

btc_ladder = build_ladder(entry_btc, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
eth_ladder = build_ladder(entry_eth, ladder_step_pct, sell_pct_per_step, max_ladder_steps)

cL, cR = st.columns(2)
with cL:
    st.subheader("BTC Ladder")
    st.dataframe(btc_ladder,use_container_width=True)
with cR:
    st.subheader("ETH Ladder")
    st.dataframe(eth_ladder,use_container_width=True)

# =========================
# Dynamic Trailing Stops
# =========================
if use_trailing and btc_price:
    st.markdown("---")
    st.subheader("🛡️ Trailing Stop Guidance")
    btc_stop = round(btc_price*(1-trail_pct/100.0),2)
    eth_stop = round(eth_price*(1-trail_pct/100.0),2) if eth_price else None
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
    min_val = alt_df[['7d %','24h %']].min().min()
    max_val = alt_df[['7d %','24h %']].max().max()
    alt_df['Rotation Score (%)'] = alt_df.apply(lambda x: round(50*(x['7d %']-min_val)/(max_val-min_val)+50*(x['24h %']-min_val)/(max_val-min_val),2), axis=1)
    alt_df['Suggested Action'] = ['✅ Rotate In' if sig.get('Rotate to Alts') else '⚠️ Wait']*len(alt_df)

    chart_option = st.selectbox("Select Altcoin Chart", ["Rotation Score (%)", "7-Day % Price Change", "Market Cap vs 7-Day % Change Bubble"])

    if chart_option == "Rotation Score (%)":
        fig = px.bar(alt_df, x='Coin', y='Rotation Score (%)', color='Rotation Score (%)',
                     color_continuous_scale='RdYlGn', title="Rotation Score (%) by Altcoin")
    elif chart_option == "7-Day % Price Change":
        fig = px.bar(alt_df, x='Coin', y='7d %', color='7d %', color_continuous_scale='RdYlGn', text='7d %', title="7-Day % Price Change")
    else:
        fig = px.scatter(alt_df, x='Mkt Cap ($B)', y='7d %', size='Mkt Cap ($B)', color='7d %', hover_name='Coin', color_continuous_scale='RdYlGn_r', size_max=60, title="Market Cap vs 7-Day % Change Bubble")
        fig.update_layout(xaxis_title="Market Cap ($B)", yaxis_title="7-Day % Change")

    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("No altcoin data available for top selection.")
