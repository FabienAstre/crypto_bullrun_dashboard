import math
import time
import requests
import pandas as pd
import streamlit as st
import datetime
import numpy as np

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
@st.cache_data(ttl=60)
def get_global():
    r = requests.get("https://api.coingecko.com/api/v3/global", timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=60)
def get_ethbtc():
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids":"ethereum","vs_currencies":"btc"},
        timeout=20
    )
    r.raise_for_status()
    return float(r.json()["ethereum"]["btc"])

@st.cache_data(ttl=60)
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

@st.cache_data(ttl=120)
def get_top_alts(n=50):
    r = requests.get(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": n+2,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h,7d,30d"
        },
        timeout=20
    )
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
# Signals Panel
# =========================
if btc_dom is not None and ethbtc is not None:
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
# Historical Bull-Run Signals Panel
# =========================
st.header("📌 Historical Bull-Run Top Signals")
signal_names = ["MVRV_Z","SOPR_LTH","Exchange_Inflow","Pi_Cycle_Top","Funding_Rate"]
signal_desc = {
    "MVRV_Z": "MVRV Z-Score >7 → BTC historically overvalued",
    "SOPR_LTH": "Long-term holder SOPR >1.5 → high profit taking",
    "Exchange_Inflow": "Exchange inflows spike → whales moving BTC to exchanges",
    "Pi_Cycle_Top": "Pi Cycle Top indicator intersects price → major top possible",
    "Funding_Rate": "Perpetual funding >0.2% long → market over-leveraged"
}
cols = st.columns(len(signal_names))
for i, s in enumerate(signal_names):
    status = sig[s]
    cols[i].markdown(f"**{s}**: {'🟢' if status else '🔴'}")
    cols[i].caption(signal_desc[s])

# =========================
# Profit Ladder Planner
# =========================
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
# Altcoin Tables
# =========================
st.header("🔥 Altcoin Watch & Rotation Tables")
alt_df = get_top_alts(top_n_alts)
alt_df['Suggested Action'] = ['✅ Rotate In' if sig['rotate_to_alts'] and x>0 else '⚠️ Wait' for x in alt_df['7d %']]
st.dataframe(alt_df, use_container_width=True)
if sig['rotate_to_alts']:
    st.success(f"Alt season detected! Consider allocating {target_alt_alloc}% of portfolio into top momentum alts.")
else:
    st.info("No alt season signal detected. Watch these alts and wait for rotation conditions.")

# =========================
# Confluence Summary
# =========================
st.header("🔔 Signal Confluence Summary")
active_signals = sum([sig[s] for s in signal_names + ["RSI_overbought","MACD_div","Volume_div","greed_high"]])
st.write(f"Number of active top-risk / exit signals: {active_signals} / {len(signal_names)+4}")
if active_signals >= 4:
    st.warning("High confluence! Strongly consider scaling out of positions and/or rotating to altcoins.")
elif active_signals >= 2:
    st.info("Moderate confluence. Partial profit-taking or watch closely.")
else:
    st.success("Low confluence. Market still bullish, hold positions.")
import plotly.express as px

# =========================
# Altcoin Chart & Rotation Probability
# =========================
st.header("📈 Altcoin Momentum & Rotation Probability")

# Compute a simple "rotation probability" score: normalize 7d % change relative to top N alts
if not alt_df.empty:
    max_7d = alt_df['7d %'].max()
    min_7d = alt_df['7d %'].min()
    alt_df['Rotation Score (%)'] = alt_df['7d %'].apply(
        lambda x: round(100*(x-min_7d)/(max_7d-min_7d),2) if max_7d!=min_7d else 0
    )
    
    fig = px.bar(
        alt_df.sort_values('Rotation Score (%)', ascending=False).head(top_n_alts),
        x='Coin', y='Rotation Score (%)',
        color='Rotation Score (%)',
        hover_data=['Name','Price ($)','7d %','30d %','Mkt Cap ($B)','Suggested Action'],
        color_continuous_scale='Viridis',
        title="Top Altcoins Rotation Probability"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Optional: highlight coins with very high rotation probability
    top_candidates = alt_df[alt_df['Rotation Score (%)']>=75]
    if not top_candidates.empty and sig['rotate_to_alts']:
        st.success("⚡ High-probability altcoins for rotation detected!")
        st.table(top_candidates[['Coin','Name','Price ($)','7d %','Rotation Score (%)','Suggested Action']])
    elif sig['rotate_to_alts']:
        st.info("Alt season signal ON, but no extreme high-probability alts this week.")
else:
    st.warning("No altcoin data available for chart.")

