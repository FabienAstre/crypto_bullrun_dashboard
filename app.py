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

# =========================
# 🌟 Header Metrics
# =========================
btc_dom, ethbtc, fg_value, fg_label = None, None, None, None
rsi, macd_div, vol_div = fetch_rsi_macd_volume()

col1, col2, col3, col4 = st.columns(4)

try:
    g = fetch_global()
    btc_dom = float(g["data"]["market_cap_percentage"]["btc"])
    col1.metric("🔹 BTC Dominance (%)", f"{btc_dom:.2f}")
except:
    col1.error("BTC.D fetch failed")

try:
    ethbtc = fetch_ethbtc()
    col2.metric("🔹 ETH/BTC", f"{ethbtc:.6f}")
except:
    col2.error("ETH/BTC fetch failed")

fg_value, fg_label = fetch_fear_greed()
if fg_value is not None:
    col3.metric("😱 Fear & Greed", f"{fg_value} ({fg_label})")
else:
    col3.error("Fear & Greed fetch failed")

btc_price, eth_price = None, None
try:
    prices = fetch_prices(["bitcoin","ethereum"])
    btc_price = float(prices["bitcoin"]["usd"])
    eth_price = float(prices["ethereum"]["usd"])
    col4.metric("💰 BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}")
except:
    col4.error("Price fetch failed")

st.markdown("---")

# =========================
# 🟢 Signals Panel
# =========================
if btc_dom and ethbtc:
    sig = build_signals(btc_dom, ethbtc, fg_value, rsi, macd_div, vol_div)
    cols = st.columns(7)
    cols[0].markdown(f"**Dom < {dom_first:.2f}%**: {'🟢 YES' if sig['dom_below_first'] else '🔴 NO'}")
    cols[1].markdown(f"**Dom < {dom_second:.2f}%**: {'🟢 YES' if sig['dom_below_second'] else '🔴 NO'}")
    cols[2].markdown(f"**ETH/BTC > {ethbtc_break:.3f}**: {'🟢 YES' if sig['ethbtc_break'] else '🔴 NO'}")
    cols[3].markdown(f"**F&G ≥ 80**: {'🟢 YES' if sig['greed_high'] else '🔴 NO'}")
    cols[4].markdown(f"**RSI > 70**: {'🟢 YES' if sig['RSI_overbought'] else '🔴 NO'}")
    cols[5].markdown(f"**MACD Divergence**: {'🟢 YES' if sig['MACD_div'] else '🔴 NO'}")
    cols[6].markdown(f"**Volume Divergence**: {'🟢 YES' if sig['Volume_div'] else '🔴 NO'}")

    st.success("💎 Profit-taking mode is ON") if sig["profit_mode"] else st.info("📈 Profit-taking mode is OFF")

# =========================
# 🎯 Profit Ladder Planner
# =========================
st.header("🎯 Profit Ladder Planner")

def build_ladder(entry, step_pct, sell_pct, max_steps):
    if entry <= 0: return pd.DataFrame([])
    ladder = []
    for i in range(1, max_steps+1):
        target = entry * (1 + step_pct/100)**i
        ladder.append({
            "Step #": i,
            "Target Price ($)": round(target,2),
            "Gain from Entry (%)": round((target/entry-1)*100,2),
            "Sell This Step (%)": sell_pct
        })
    return pd.DataFrame(ladder)

btc_ladder = build_ladder(entry_btc, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
eth_ladder = build_ladder(entry_eth, ladder_step_pct, sell_pct_per_step, max_ladder_steps)

cL, cR = st.columns(2)
with cL:
    st.subheader("🔹 BTC Ladder")
    st.dataframe(btc_ladder, use_container_width=True)
with cR:
    st.subheader("🔹 ETH Ladder")
    st.dataframe(eth_ladder, use_container_width=True)

# =========================
# 🛡️ Trailing Stop
# =========================
if use_trailing and btc_price:
    st.markdown("---")
    st.subheader("🛡️ Trailing Stop Guidance")
    btc_stop = round(btc_price*(1-trail_pct/100),2)
    eth_stop = round(eth_price*(1-trail_pct/100),2) if eth_price else None
    st.write(f"- Suggested BTC stop: 💔 ${btc_stop:,.2f}")
    if eth_stop: st.write(f"- Suggested ETH stop: 💔 ${eth_stop:,.2f}")

# =========================
# 🌈 Bitcoin Rainbow Chart
# =========================
st.header("🌈 Bitcoin Rainbow Chart")
try:
    r = requests.get(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        params={"vs_currency":"usd","days":"max","interval":"daily"}, timeout=20
    )
    r.raise_for_status()
    data = r.json()
    prices = pd.DataFrame(data["prices"], columns=["timestamp","price"])
    prices["date"] = pd.to_datetime(prices["timestamp"], unit="ms")
    prices.set_index("date", inplace=True)

    x = np.arange(len(prices))
    prices["log_price"] = np.log(prices["price"])
    base = np.poly1d(np.polyfit(x, prices["log_price"], 2))(x)

    bands = {
        "Fire Sale": base-1.6, "Undervalued": base-1.0, "Fair Value": base-0.5,
        "Overvalued": base, "Very Overvalued": base+0.5, "Bubble": base+1.0
    }
    fig_rainbow = go.Figure()
    colors = ["red","orange","yellow","green","blue","purple"]

    for i, (name, val) in enumerate(bands.items()):
        fig_rainbow.add_trace(go.Scatter(
            x=prices.index, y=np.exp(val),
            line=dict(color=colors[i]),
            name=name,
            fill="tonexty" if i>0 else None
        ))

    fig_rainbow.add_trace(go.Scatter(
        x=prices.index, y=prices["price"], mode="lines",
        name="BTC Price", line=dict(color="black", width=2)
    ))

    fig_rainbow.update_layout(
        title="🌈 BTC Rainbow Chart",
        yaxis_type="log",
        xaxis_title="Date",
        yaxis_title="BTC Price (USD, log scale)",
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.2)
    )
    st.plotly_chart(fig_rainbow, use_container_width=True)
except Exception as e:
    st.warning(f"Failed to fetch BTC rainbow chart: {e}")

# =========================
# 🔥 Altcoin Rotation
# =========================
st.header("🔥 Altcoin Momentum & Rotation")
alt_df = fetch_top_alts(top_n_alts)
if not alt_df.empty:
    alt_df['Suggested Action'] = ['✅ Rotate In' if sig['rotate_to_alts'] else '⚠️ Wait' for _ in alt_df['7d %']]
    # Rotation score
    max_7d, min_7d = alt_df['7d %'].max(), alt_df['7d %'].min()
    alt_df['Rotation Score (%)'] = alt_df['7d %'].apply(lambda x: round(100*(x-min_7d)/(max_7d-min_7d),2) if max_7d!=min_7d else 0)

    # Chart
    fig = go.Figure()
    fig.add_trace(go.Bar(x=alt_df['Coin'], y=alt_df['Rotation Score (%)'], name='Rotation Score (%)', marker_color='indianred', hovertext=alt_df['Suggested Action']))
    fig.add_trace(go.Scatter(x=alt_df['Coin'], y=alt_df['7d %'], name='7d % Change', yaxis='y2', mode='lines+markers', marker_color='royalblue'))
    fig.update_layout(
        title="Top Altcoins Momentum & Rotation Probability",
        xaxis_title="Altcoin",
        yaxis=dict(title="Rotation Score (%)"),
        yaxis2=dict(title="7d % Change", overlaying='y', side='right'),
        legend=dict(y=1.1, orientation="h"),
        hovermode='x unified'
    )
    st.plotly_chart(fig, use_container_width=True)

    # High probability rotation
    top_candidates = alt_df[(alt_df['Rotation Score (%)']>=75) & (sig['rotate_to_alts'])]
    if not top_candidates.empty:
        st.success("⚡ High-probability altcoins for rotation detected!")
        st.table(top_candidates[['Coin','Name','Price ($)','7d %','Rotation Score (%)','Suggested Action']])
    elif sig['rotate_to_alts']:
        st.info("Alt season signal ON, but no extreme high-probability alts this week.")

    # Specific altcoin history
    st.subheader("📈 View Specific Altcoin History")
    alt_choice = st.selectbox("Select an Altcoin", alt_df['Coin'].tolist())
    try:
        r = requests.get(f"https://api.coingecko.com/api/v3/coins/{alt_choice.lower()}/market_chart", params={"vs_currency":"usd","days":30,"interval":"daily"}, timeout=20)
        r.raise_for_status()
        data = r.json()
        prices_hist = pd.DataFrame(data["prices"], columns=["timestamp","price"])
        prices_hist["date"] = pd.to_datetime(prices_hist["timestamp"], unit='ms')
        fig_hist = px.line(prices_hist, x="date", y="price", title=f"{alt_choice} Price Last 30 Days", markers=True)
        st.plotly_chart(fig_hist, use_container_width=True)
    except:
        st.warning(f"Failed to fetch historical data for {alt_choice}")

# =========================
# 🔔 Signal Confluence Summary
# =========================
st.header("🔔 Signal Confluence Summary")
signal_names = ["MVRV_Z","SOPR_LTH","Exchange_Inflow","Pi_Cycle_Top","Funding_Rate"]
all_signals = signal_names + ["RSI_overbought","MACD_div","Volume_div","greed_high"]
active_signals = sum([sig[s] for s in all_signals])
st.write(f"Number of active top-risk / exit signals: {active_signals} / {len(all_signals)}")
if active_signals >= 4:
    st.warning("High confluence! Consider scaling out and/or rotating to altcoins. ⚠️")
elif active_signals >= 2:
    st.info("Moderate confluence. Partial profit-taking or watch closely. 👀")
else:
    st.success("Low confluence. Market still bullish. 🟢")

# Active/inactive signals detail
active_signal_list = [s for s in all_signals if sig[s]]
inactive_signal_list = [s for s in all_signals if not sig[s]]
st.subheader("🔍 Active Signals Detail")
st.write(f"**Active Signals ({len(active_signal_list)})**: {', '.join(active_signal_list) if active_signal_list else 'None'}")
st.write(f"**Inactive Signals ({len(inactive_signal_list)})**: {', '.join(inactive_signal_list) if inactive_signal_list else 'None'}")
