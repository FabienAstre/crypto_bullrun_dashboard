import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

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

st.sidebar.caption("This dashboard pulls live data at runtime (CoinDesk API).")

# =========================
# CoinDesk API Fetchers
# =========================

@st.cache_data(ttl=60)
def get_btc_price():
    r = requests.get("https://api.coindesk.com/v2/prices/BTC-USD/spot", timeout=20)
    r.raise_for_status()
    return float(r.json()["data"]["price"])

@st.cache_data(ttl=60)
def get_eth_price():
    # CoinDesk may not provide ETH, use secondary source like CoinCap
    r = requests.get("https://api.coincap.io/v2/assets/ethereum", timeout=20)
    r.raise_for_status()
    return float(r.json()["data"]["priceUsd"])

@st.cache_data(ttl=60)
def get_btc_dominance():
    # Using CoinDesk Toplist by Market Cap
    r = requests.get("https://api.coindesk.com/v2/assets/toplist?limit=100", timeout=20)
    r.raise_for_status()
    data = r.json()["data"]
    total_cap = sum([float(x["market_cap_usd"]) for x in data])
    btc_cap = float([x for x in data if x["symbol"]=="BTC"][0]["market_cap_usd"])
    return btc_cap / total_cap * 100

@st.cache_data(ttl=60)
def get_top_alts(n=50):
    r = requests.get(f"https://api.coindesk.com/v2/assets/toplist?limit={n+2}", timeout=20)
    r.raise_for_status()
    data = [x for x in r.json()["data"] if x["symbol"].upper() not in ("BTC","ETH")][:n]
    return pd.DataFrame([{
        "Rank": int(x["rank"]),
        "Coin": x["symbol"].upper(),
        "Name": x["name"],
        "Price ($)": float(x["price_usd"]),
        "24h %": float(x.get("change_percent_24h") or 0),
        "7d %": float(x.get("change_percent_7d") or 0),
        "30d %": float(x.get("change_percent_30d") or 0),
        "Mkt Cap ($B)": float(x["market_cap_usd"])/1e9
    } for x in data])

@st.cache_data(ttl=120)
def get_rsi_macd_volume():
    # Placeholder: compute locally from historical OHLCV
    return 72, 0.002, False  # RSI, MACD hist divergence, volume divergence

# =========================
# Header Metrics
# =========================
col1, col2, col3, col4 = st.columns(4)

btc_price = get_btc_price()
eth_price = get_eth_price()
btc_dom = get_btc_dominance()
ethbtc = eth_price / btc_price
rsi, macd_div, vol_div = get_rsi_macd_volume()

col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}")
col2.metric("ETH/BTC", f"{ethbtc:.6f}")
col3.metric("RSI (placeholder)", f"{rsi}")
col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}")

# =========================
# Signals Panel
# =========================
def build_signals(dom, ethbtc, rsi, macd_div, vol_div):
    sig = {
        "dom_below_first": dom < dom_first,
        "dom_below_second": dom < dom_second,
        "ethbtc_break": ethbtc > ethbtc_break,
        "RSI_overbought": rsi > 70,
        "MACD_div": macd_div,
        "Volume_div": vol_div
    }
    sig["rotate_to_alts"] = sig["dom_below_first"] and sig["ethbtc_break"]
    sig["profit_mode"] = sig["dom_below_second"] or sig["RSI_overbought"] or sig["MACD_div"] or sig["Volume_div"]
    sig["full_exit_watch"] = sig["dom_below_second"]
    # Historical bull-run placeholders
    sig["MVRV_Z"] = True
    sig["SOPR_LTH"] = True
    sig["Exchange_Inflow"] = False
    sig["Pi_Cycle_Top"] = False
    sig["Funding_Rate"] = True
    return sig

sig = build_signals(btc_dom, ethbtc, rsi, macd_div, vol_div)

cols = st.columns(7)
cols[0].markdown(f"**Dom < {dom_first:.2f}%**: {'🟢 YES' if sig['dom_below_first'] else '🔴 NO'}")
cols[1].markdown(f"**Dom < {dom_second:.2f}%**: {'🟢 YES' if sig['dom_below_second'] else '🔴 NO'}")
cols[2].markdown(f"**ETH/BTC > {ethbtc_break:.3f}**: {'🟢 YES' if sig['ethbtc_break'] else '🔴 NO'}")
cols[3].markdown(f"**RSI > 70**: {'🟢 YES' if sig['RSI_overbought'] else '🔴 NO'}")
cols[4].markdown(f"**MACD Divergence**: {'🟢 YES' if sig['MACD_div'] else '🔴 NO'}")
cols[5].markdown(f"**Volume Divergence**: {'🟢 YES' if sig['Volume_div'] else '🔴 NO'}")
cols[6].markdown(f"**Rotate to Alts**: {'🟢 YES' if sig['rotate_to_alts'] else '🔴 NO'}")

# =========================
# Profit Ladder
# =========================
def build_ladder(entry, current, step_pct, sell_pct, max_steps):
    rows = []
    if entry <= 0: return pd.DataFrame(rows)
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
with cL: st.subheader("BTC Ladder"); st.dataframe(btc_ladder,use_container_width=True)
with cR: st.subheader("ETH Ladder"); st.dataframe(eth_ladder,use_container_width=True)

# =========================
# Trailing Stop
# =========================
if use_trailing:
    st.subheader("🛡️ Trailing Stop Guidance")
    btc_stop = round(btc_price*(1-trail_pct/100.0),2)
    eth_stop = round(eth_price*(1-trail_pct/100.0),2)
    st.write(f"- Suggested BTC stop: ${btc_stop:,.2f}")
    st.write(f"- Suggested ETH stop: ${eth_stop:,.2f}")

# =========================
# Altcoin Watch Table
# =========================
st.header("🔥 Altcoin Watch & Rotation Tables")
alt_df = get_top_alts(top_n_alts)
alt_df['Suggested Action'] = ['✅ Rotate In' if sig['rotate_to_alts'] and x>0 else '⚠️ Wait' for x in alt_df['7d %']]
st.dataframe(alt_df, use_container_width=True)

# =========================
# Altcoin Momentum Chart
# =========================
if not alt_df.empty:
    max_7d = alt_df['7d %'].max()
    min_7d = alt_df['7d %'].min()
    alt_df['Rotation Score (%)'] = alt_df['7d %'].apply(
        lambda x: round(100*(x-min_7d)/(max_7d-min_7d),2) if max_7d!=min_7d else 0
    )
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=alt_df['Coin'], y=alt_df['Rotation Score (%)'], name='Rotation Score (%)', marker_color='indianred', hovertext=alt_df['Suggested Action']))
    fig.add_trace(go.Scatter(x=alt_df['Coin'], y=alt_df['7d %'], name='7d % Change', yaxis='y2', mode='lines+markers', marker_color='royalblue'))
    fig.update_layout(title="Top Altcoins Momentum & Rotation Probability", xaxis_title="Altcoin", yaxis=dict(title="Rotation Score (%)"), yaxis2=dict(title="7d % Change", overlaying='y', side='right'), legend=dict(y=1.1, orientation="h"), hovermode='x unified')
    st.plotly_chart(fig, use_container_width=True)
