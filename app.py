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
    # Placeholder: in a real version fetch BTC price history and compute RSI/MACD/Volume divergence
    return 72, 0.002, False  # RSI, MACD hist divergence, volume divergence

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
    # Historical bull-run placeholders
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
sig = {}

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

# =========================
# Signals Panel with Explanations
# =========================
if btc_dom is not None and ethbtc is not None:
    sig = build_signals(btc_dom, ethbtc, fg_value, rsi, macd_div, vol_div)

signal_defs = {
    "Dom < First Break": {
        "active": sig.get("dom_below_first"),
        "desc": "BTC losing market share → altcoins may start moving up."
    },
    "Dom < Strong Confirm": {
        "active": sig.get("dom_below_second"),
        "desc": "Confirms major rotation into altcoins → potential altseason."
    },
    "ETH/BTC Breakout": {
        "active": sig.get("ethbtc_break"),
        "desc": "ETH outperforming BTC → bullish for ETH and altcoins."
    },
    "F&G ≥ 80": {
        "active": sig.get("greed_high"),
        "desc": "Extreme greed → market may be overbought."
    },
    "RSI > 70": {
        "active": sig.get("RSI_overbought"),
        "desc": "BTC overbought → possible short-term correction."
    },
    "MACD Divergence": {
        "active": sig.get("MACD_div"),
        "desc": "Momentum slowing → potential reversal."
    },
    "Volume Divergence": {
        "active": sig.get("Volume_div"),
        "desc": "Weak price movement → caution on trend continuation."
    },
    "Rotate to Alts": {
        "active": sig.get("rotate_to_alts"),
        "desc": "Strong rotation signal → move funds into altcoins."
    },
    "Profit Mode": {
        "active": sig.get("profit_mode"),
        "desc": "Suggests scaling out of positions / taking profit."
    },
    "Full Exit Watch": {
        "active": sig.get("full_exit_watch"),
        "desc": "Extreme signal → consider exiting major positions."
    }
}

st.markdown("### 📊 Key Market Signals")
cols = st.columns(len(signal_defs))
for i, (name, info) in enumerate(signal_defs.items()):
    emoji = "🟢" if info["active"] else "🔴"
    cols[i].markdown(f"**{name}** {emoji}  \n*{info['desc']}*")

# =========================
# Profit Ladder Planner
# =========================
st.markdown("---")
st.header("🎯 Profit-Taking Ladder")

def build_ladder(entry, current, step_pct, sell_pct, max_steps):
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

btc_ladder = build_ladder(entry_btc, btc_price, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
eth_ladder = build_ladder(entry_eth, eth_price, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
cL, cR = st.columns(2)
with cL:
    st.subheader("BTC Ladder")
    st.dataframe(btc_ladder,use_container_width=True)
with cR:
    st.subheader("ETH Ladder")
    st.dataframe(eth_ladder,use_container_width=True)

# =========================
# Trailing Stop
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
# Altcoin Dashboard Top 30 (Single Graph + Dropdown + Top Picks)
# =========================
st.markdown("---")
st.header("🔥 Altcoin Momentum & Rotation Dashboard (Top 30)")

# Fetch top 50 altcoins safely
alt_df = get_top_alts_safe(50)
if not alt_df.empty:
    # Take top 30 by 7d % change
    alt_df = alt_df.sort_values(by='7d %', ascending=False).head(30)

    # Compute rotation score
    min_7d = alt_df['7d %'].min()
    max_7d = alt_df['7d %'].max()
    alt_df['Rotation Score (%)'] = alt_df['7d %'].apply(lambda x: round(100*(x-min_7d)/(max_7d-min_7d),2) if pd.notnull(x) else 0)
    alt_df['Suggested Action'] = ['✅ Rotate In' if sig.get('rotate_to_alts') else '⚠️ Wait']*len(alt_df)

    # Dropdown for chart selection
    chart_option = st.selectbox("Select Altcoin Chart", ["Rotation Score (%)", "7-Day % Price Change", "Market Cap vs 7-Day % Change Bubble"])

    if chart_option == "Rotation Score (%)":
        fig = px.bar(
            alt_df, x='Coin', y='Rotation Score (%)', color='Rotation Score (%)',
            color_continuous_scale='RdYlGn', title="Rotation Score (%) by Altcoin"
        )
    elif chart_option == "7-Day % Price Change":
        fig = px.bar(
            alt_df, x='Coin', y='7d %', color='7d %',
            color_continuous_scale='RdYlGn', text='7d %', title="7-Day % Price Change"
        )
    else:  # Bubble chart
        fig = px.scatter(
            alt_df, x='Mkt Cap ($B)', y='7d %', size='Mkt Cap ($B)', color='7d %',
            hover_name='Coin', color_continuous_scale='RdYlGn_r',
            size_max=60, title="Market Cap vs 7-Day % Change Bubble"
        )
        fig.update_layout(xaxis_title="Market Cap ($B)", yaxis_title="7-Day % Change")

    st.plotly_chart(fig, use_container_width=True)

    # =========================
    # Top Rotation Picks
    # =========================
    st.subheader("⚡ Top Rotation Picks")

    # Sidebar filters
    st.sidebar.subheader("Top Picks Filters")
    min_rotation_score = st.sidebar.slider("Min Rotation Score (%)", 0, 100, 50)
    min_7d_change = st.sidebar.slider("Min 7-Day % Change", -100, 100, -50)
    market_cap_filter = st.sidebar.selectbox("Market Cap", ["All", "Large (>10B)", "Mid (1-10B)", "Small (<1B)"])
    action_filter = st.sidebar.selectbox("Suggested Action", ["All", "✅ Rotate In", "⚠️ Wait"])
    sort_by = st.sidebar.selectbox("Sort by", ["Rotation Score (%)", "7d %", "Mkt Cap ($B)"])

    # Filter top candidates
    top_candidates = alt_df[
        (alt_df['Rotation Score (%)'] >= min_rotation_score) &
        (alt_df['7d %'] >= min_7d_change)
    ]

    if market_cap_filter == "Large (>10B)":
        top_candidates = top_candidates[top_candidates['Mkt Cap ($B)'] > 10]
    elif market_cap_filter == "Mid (1-10B)":
        top_candidates = top_candidates[(top_candidates['Mkt Cap ($B)'] >= 1) & (top_candidates['Mkt Cap ($B)'] <= 10)]
    elif market_cap_filter == "Small (<1B)":
        top_candidates = top_candidates[top_candidates['Mkt Cap ($B)'] < 1]

    if action_filter != "All":
        top_candidates = top_candidates[top_candidates['Suggested Action'] == action_filter]

    # Sort the table
    top_candidates = top_candidates.sort_values(by=sort_by, ascending=False)

    # Highlight top coins visually
    def highlight_top(row):
        return ['background-color: #d4edda' if row['Rotation Score (%)'] >= 90 else '' for _ in row]

    st.dataframe(
        top_candidates[['Coin','Name','Price ($)','7d %','Rotation Score (%)','Suggested Action']].style.apply(highlight_top, axis=1),
        use_container_width=True
    )

else:
    st.warning("No altcoin data available for top 30.")
# =========================
# Signals Detail Panel (Expanded)
# =========================
st.subheader("🔍 Signals Detail")

# Define all signals with human-readable descriptions
signal_defs_expanded = {
    "Dom < First Break": {"desc": "BTC losing market share → altcoins may start moving up."},
    "Dom < Strong Confirm": {"desc": "Confirms major rotation into altcoins → potential altseason."},
    "ETH/BTC Breakout": {"desc": "ETH outperforming BTC → bullish for ETH and altcoins."},
    "F&G ≥ 80": {"desc": "Extreme greed → market may be overbought."},
    "RSI > 70": {"desc": "BTC overbought → possible short-term correction."},
    "MACD Divergence": {"desc": "Momentum slowing → potential reversal."},
    "Volume Divergence": {"desc": "Weak price movement → caution on trend continuation."},
    "Rotate to Alts": {"desc": "Strong rotation signal → move funds into altcoins."},
    "Profit Mode": {"desc": "Suggests scaling out of positions / taking profit."},
    "Full Exit Watch": {"desc": "Extreme signal → consider exiting major positions."},
    # Add more signals here if needed
    "MVRV Z-Score": {"desc": "BTC historically overvalued when MVRV Z > 7."},
    "SOPR LTH": {"desc": "Long-term holder SOPR > 1.5 → high profit taking."},
    "Exchange Inflow": {"desc": "Exchange inflows spike → whales moving BTC to exchanges."},
    "Pi Cycle Top": {"desc": "Pi Cycle Top indicator intersects price → major top possible."},
    "Funding Rate": {"desc": "Perpetual funding > 0.2% long → market over-leveraged."}
}

# Display each signal with green/red dot and description
for sig_name, sig_info in signal_defs_expanded.items():
    active = sig.get(sig_name, False)  # Fallback to False if missing
    # Handle numeric signals (like MACD Divergence)
    if isinstance(active, (int, float)):
        status = "🟢" if active else "🔴"
    else:
        status = "🟢" if active else "🔴"
    
    st.markdown(f"{status} **{sig_name}** - {sig_info['desc']}")

