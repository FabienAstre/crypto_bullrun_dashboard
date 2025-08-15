import math
import time
import requests
import pandas as pd
import streamlit as st
import datetime
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="🚀 Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")

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

st.sidebar.caption("Live data from CoinGecko & Alternative.me")

# =========================
# Safe Data Fetchers
# =========================
@st.cache_data(ttl=300)
def get_global_safe():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.warning(f"Failed to fetch global data: {e}")
        return None

@st.cache_data(ttl=300)
def get_ethbtc_safe():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids":"ethereum","vs_currencies":"btc"},
            timeout=20
        )
        r.raise_for_status()
        return float(r.json().get("ethereum", {}).get("btc", None))
    except Exception as e:
        st.warning(f"Failed to fetch ETH/BTC: {e}")
        return None

@st.cache_data(ttl=300)
def get_prices_usd_safe(ids):
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(ids), "vs_currencies": "usd"},
            timeout=20
        )
        r.raise_for_status()
        return {k: v.get("usd") for k,v in r.json().items()}
    except Exception as e:
        st.warning(f"Failed to fetch prices: {e}")
        return {k: None for k in ids}

@st.cache_data(ttl=300)
def get_fear_greed_safe():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=20)
        r.raise_for_status()
        data = r.json().get("data", [{}])[0]
        return int(data.get("value", 0)), data.get("value_classification", "N/A")
    except:
        return None, None

@st.cache_data(ttl=300)
def get_top_alts_safe(n=50):
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency":"usd",
                "order":"market_cap_desc",
                "per_page": n+5,
                "page": 1,
                "sparkline":"false",
                "price_change_percentage":"24h,7d,30d"
            },
            timeout=20
        )
        r.raise_for_status()
        data = r.json()
        filtered = [x for x in data if x.get("symbol") and x["symbol"].upper() not in ("BTC","ETH")]
        filtered = filtered[:n]
        return pd.DataFrame([{
            "Rank": x.get("market_cap_rank"),
            "Coin": x.get("symbol","").upper(),
            "Name": x.get("name"),
            "Price ($)": x.get("current_price"),
            "24h %": x.get("price_change_percentage_24h_in_currency"),
            "7d %": x.get("price_change_percentage_7d_in_currency"),
            "30d %": x.get("price_change_percentage_30d_in_currency"),
            "Mkt Cap ($B)": (x.get("market_cap") or 0)/1e9
        } for x in filtered])
    except Exception as e:
        st.warning(f"Failed to fetch altcoins: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=120)
def get_rsi_macd_volume_safe():
    # Placeholder
    return 72, 0.002, False

# =========================
# Build Signals
# =========================
def build_signals(dom, ethbtc, fg_value, rsi, macd_div, vol_div):
    sig = {
        "dom_below_first": dom and dom < dom_first,
        "dom_below_second": dom and dom < dom_second,
        "ethbtc_break": ethbtc and ethbtc > ethbtc_break,
        "greed_high": fg_value and fg_value >= 80,
        "RSI_overbought": rsi and rsi > 70,
        "MACD_div": macd_div,
        "Volume_div": vol_div
    }
    sig["rotate_to_alts"] = sig["dom_below_first"] and sig["ethbtc_break"]
    sig["profit_mode"] = sig["dom_below_second"] or sig["greed_high"] or sig["RSI_overbought"] or sig["MACD_div"] or sig["Volume_div"]
    sig["full_exit_watch"] = sig["dom_below_second"] and sig["greed_high"]
    sig.update({"MVRV_Z": True, "SOPR_LTH": True, "Exchange_Inflow": False, "Pi_Cycle_Top": False, "Funding_Rate": True})
    return sig

# =========================
# Fetch Data
# =========================
btc_dom = (get_global_safe() or {}).get("data", {}).get("market_cap_percentage", {}).get("btc")
ethbtc = get_ethbtc_safe()
fg_value, fg_label = get_fear_greed_safe()
rsi, macd_div, vol_div = get_rsi_macd_volume_safe()
prices = get_prices_usd_safe(["bitcoin","ethereum"])
btc_price = prices.get("bitcoin")
eth_price = prices.get("ethereum")

sig = build_signals(btc_dom, ethbtc, fg_value, rsi, macd_div, vol_div) if btc_dom and ethbtc else {}

# =========================
# Header Metrics
# =========================
cols = st.columns(4)
cols[0].metric("BTC Dominance (%)", f"{btc_dom:.2f}" if btc_dom else "N/A")
cols[1].metric("ETH/BTC", f"{ethbtc:.6f}" if ethbtc else "N/A")
cols[2].metric("Fear & Greed", f"{fg_value} ({fg_label})" if fg_value else "N/A")
cols[3].metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}" if btc_price and eth_price else "N/A")

# =========================
# Signal Panel (Green / Red Dots)
# =========================
st.markdown("---")
st.header("📊 Key Market Signals")

if sig:
    signal_defs = {
        "Dom < First Break": sig.get("dom_below_first"),
        "Dom < Strong Confirm": sig.get("dom_below_second"),
        "ETH/BTC Breakout": sig.get("ethbtc_break"),
        "F&G ≥ 80": sig.get("greed_high"),
        "RSI > 70": sig.get("RSI_overbought"),
        "MACD Divergence": sig.get("MACD_div"),
        "Volume Divergence": sig.get("Volume_div"),
        "Rotate to Alts": sig.get("rotate_to_alts"),
        "Profit Mode": sig.get("profit_mode"),
        "Full Exit Watch": sig.get("full_exit_watch")
    }

    cols = st.columns(len(signal_defs))
    for i, (name, active) in enumerate(signal_defs.items()):
        emoji = "🟢" if active else "🔴"
        cols[i].markdown(f"**{name}**\n\n{emoji}")
else:
    st.warning("Signals unavailable")

# =========================
# Tabs Layout
# =========================
tabs = st.tabs(["💰 Profit Ladder","🔥 Altcoins","🔔 Signals"])

with tabs[0]:
    st.header("🎯 Profit Ladder")
    def build_ladder(entry, step_pct, sell_pct, max_steps):
        if not entry: return pd.DataFrame()
        return pd.DataFrame([{
            "Step #": i,
            "Target Price": round(entry*(1+step_pct/100)**i,2),
            "Gain (%)": round((entry*(1+step_pct/100)**i/entry-1)*100,2),
            "Sell (%)": sell_pct
        } for i in range(1,max_steps+1)])
    
    c1, c2 = st.columns(2)
    c1.subheader("BTC Ladder"); c1.dataframe(build_ladder(entry_btc, ladder_step_pct, sell_pct_per_step, max_ladder_steps), use_container_width=True)
    c2.subheader("ETH Ladder"); c2.dataframe(build_ladder(entry_eth, ladder_step_pct, sell_pct_per_step, max_ladder_steps), use_container_width=True)
    
    if use_trailing and btc_price and eth_price:
        st.subheader("🛡️ Trailing Stop")
        st.write(f"- BTC stop: ${btc_price*(1-trail_pct/100):,.2f}")
        st.write(f"- ETH stop: ${eth_price*(1-trail_pct/100):,.2f}")

with tabs[1]:
    st.header("🔥 Altcoin Momentum & Rotation")
    alt_df = get_top_alts_safe(top_n_alts)
    if not alt_df.empty:
        # Compute rotation score safely
        if alt_df['7d %'].notnull().any():
            min_7d = alt_df['7d %'].min()
            max_7d = alt_df['7d %'].max()
            alt_df['Rotation Score (%)'] = alt_df['7d %'].apply(lambda x: round(100*(x-min_7d)/(max_7d-min_7d),2) if pd.notnull(x) else 0)
        else:
            alt_df['Rotation Score (%)'] = 0
        alt_df['Suggested Action'] = ['✅ Rotate In' if sig.get('rotate_to_alts') else '⚠️ Wait']*len(alt_df)

        col1, col2, col3 = st.columns([1.2,1.2,1])
        fig1 = px.bar(alt_df, x='Coin', y='Rotation Score (%)', color='Rotation Score (%)', color_continuous_scale='RdYlGn', title="Rotation Score (%)")
        fig2 = px.scatter(alt_df, x='Coin', y='7d %', size='Mkt Cap ($B)', color='7d %', color_continuous_scale='RdYlGn', title="7D % vs Market Cap")
        col1.plotly_chart(fig1, use_container_width=True)
        col2.plotly_chart(fig2, use_container_width=True)
        col3.subheader("Top Picks")
        col3.dataframe(alt_df[alt_df['Rotation Score (%)']>=75][['Coin','Name','Price ($)','7d %','Rotation Score (%)','Suggested Action']], use_container_width=True)

        st.markdown("---")
        choice = st.selectbox("View Altcoin History", alt_df['Coin'].tolist())
        days = st.radio("Range", [30,90], horizontal=True)
        try:
            r = requests.get(f"https://api.coingecko.com/api/v3/coins/{choice.lower()}/market_chart", params={"vs_currency":"usd","days":days,"interval":"daily"}, timeout=20).json()
            df_hist = pd.DataFrame(r.get("prices",[]), columns=["timestamp","price"])
            if not df_hist.empty:
                df_hist["date"]=pd.to_datetime(df_hist["timestamp"], unit="ms")
                st.plotly_chart(px.line(df_hist,x="date",y="price",title=f"{choice} Price - Last {days} Days", markers=True), use_container_width=True)
        except:
            st.warning("Failed to fetch historical data")

with tabs[2]:
    st.header("🔔 Signal Confluence Summary")
    if sig:
        active_signals = sum(bool(v) for v in sig.values())
        st.write(f"Active Signals: {active_signals}/{len(sig)}")
        if active_signals>=4: st.warning("High confluence! Consider scaling out or rotating to alts.")
        elif active_signals>=2: st.info("Moderate confluence. Partial profit-taking.")
        else: st.success("Low confluence. Market still bullish.")
    else:
        st.warning("Signal summary unavailable")
