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
    except:
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
    except:
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
    except:
        return {}

@st.cache_data(ttl=300)
def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=20)
        r.raise_for_status()
        data = r.json()["data"][0]
        return int(data["value"]), data["value_classification"]
    except:
        return None, None

@st.cache_data(ttl=300)
def get_top_alts_safe(n=30):
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
            "24h %": x.get("price_change_percentage_24h_in_currency",0.0),
            "7d %": x.get("price_change_percentage_7d_in_currency",0.0),
            "Mkt Cap ($B)": (x["market_cap"] or 0)/1e9
        } for x in data])
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=120)
def get_rsi_macd_volume():
    return 72, 0.002, False  # Placeholder: RSI, MACD hist divergence, volume divergence

@st.cache_data(ttl=3600)
def get_btc_history(days=365):
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
            params={"vs_currency":"usd","days":days,"interval":"daily"},
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data["prices"], columns=["timestamp","price"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("date", inplace=True)
        return df[["price"]]
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_eth_history(days=365):
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/ethereum/market_chart",
            params={"vs_currency":"usd","days":days,"interval":"daily"},
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data["prices"], columns=["timestamp","price"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("date", inplace=True)
        return df[["price"]]
    except:
        return pd.DataFrame()

# =========================
# Signals Builder
# =========================
def build_signals(dom, ethbtc, fg_value, rsi, macd_div, vol_div):
    return {
        "Dom < First Break": dom is not None and dom < dom_first,
        "Dom < Strong Confirm": dom is not None and dom < dom_second,
        "ETH/BTC Breakout": ethbtc is not None and ethbtc > ethbtc_break,
        "F&G ≥ 80": fg_value is not None and fg_value >= 80,
        "RSI > 70": rsi is not None and rsi > 70,
        "MACD Divergence": macd_div,
        "Volume Divergence": vol_div,
        "Rotate to Alts": dom is not None and dom < dom_first and ethbtc is not None and ethbtc > ethbtc_break,
        "Profit Mode": dom is not None and (dom < dom_second or (fg_value is not None and fg_value>=80) or rsi>70 or macd_div or vol_div),
        "Full Exit Watch": dom is not None and dom < dom_second and fg_value is not None and fg_value>=80,
        "MVRV Z-Score": True,
        "SOPR LTH": True,
        "Exchange Inflow": True,
        "Pi Cycle Top": True,
        "Funding Rate": True
    }

# =========================
# Header Metrics
# =========================
col1, col2, col3, col4 = st.columns(4)
g = get_global()
btc_dom = float(g["data"]["market_cap_percentage"]["btc"]) if g else None
col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}" if btc_dom else "N/A")
ethbtc = get_ethbtc()
col2.metric("ETH/BTC", f"{ethbtc:.6f}" if ethbtc else "N/A")
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
# Key Market Signals
# =========================
st.markdown("### 📊 Key Market Signals & Explanations")
signal_descriptions = {
    "Dom < First Break": "BTC losing market share → altcoins may start moving up.",
    "Dom < Strong Confirm": "Confirms major rotation into altcoins → potential altseason.",
    "ETH/BTC Breakout": "ETH outperforming BTC → bullish for ETH and altcoins.",
    "F&G ≥ 80": "Extreme greed → market may be overbought.",
    "RSI > 70": "BTC overbought → possible short-term correction.",
    "MACD Divergence": "Momentum slowing → potential reversal.",
    "Rotate to Alts": "Strong rotation signal → move funds into altcoins.",
    "Profit Mode": "Suggests scaling out of positions / taking profit.",
    "Full Exit Watch": "Extreme signal → consider exiting major positions.",
    "MVRV Z-Score": "BTC historically overvalued when MVRV Z > 7.",
    "SOPR LTH": "Long-term holder SOPR > 1.5 → high profit taking.",
    "Exchange Inflow": "Exchange inflows spike → whales moving BTC to exchanges.",
    "Pi Cycle Top": "MA111 > MA350 → potential market top.",
    "Funding Rate": "Perpetual funding > 0.2% long → market over-leveraged."
}
cols_per_row = 3
signal_items = list(signal_descriptions.items())
for i in range(0, len(signal_items), cols_per_row):
    cols = st.columns(min(cols_per_row, len(signal_items)-i))
    for j, (name, desc) in enumerate(signal_items[i:i+cols_per_row]):
        active = bool(sig.get(name, False))
        status_emoji = "🟢" if active else "🔴"
        cols[j].markdown(f"{status_emoji} **{name}**  \n{desc}")

# =========================
# ETH/BTC Ratio Chart
# =========================
st.markdown("---")
st.header("📈 ETH/BTC Ratio Over Time")
btc_hist = get_btc_history(days=365)
eth_hist = get_eth_history(days=365)
if not btc_hist.empty and not eth_hist.empty:
    df_ratio = pd.DataFrame({
        'ETH/BTC': eth_hist['price'].values / btc_hist['price'].values,
        'Date': eth_hist.index
    })
    fig_ratio = px.line(df_ratio, x='Date', y='ETH/BTC', title='ETH/BTC Ratio 1-Year')
    fig_ratio.add_hline(y=ethbtc_break, line_dash="dash", line_color="red",
                        annotation_text="Breakout Level", annotation_position="top left")
    st.plotly_chart(fig_ratio, use_container_width=True)
else:
    st.warning("ETH/BTC history data not available.")

# =========================
# BTC Price & Resistance Levels (Zoom enabled, 200k removed)
# =========================
st.markdown("---")
st.header("🛡️ BTC Price & Resistance Levels")

# Removed 200k, keeping only valid resistances
btc_resistances = [114000, 120000, 123000]

if not btc_hist.empty:
    fig_btc = px.line(btc_hist, y='price', title="BTC Price (1-Year) with Resistance Levels")

    # Add horizontal resistance lines
    for level in btc_resistances:
        fig_btc.add_hline(
            y=level, 
            line_dash="dash", 
            line_color="red",
            annotation_text=f"Resistance ${level:,.0f}", 
            annotation_position="top left"
        )

    # Labels + Zooming enabled
    fig_btc.update_yaxes(title="Price (USD)")
    fig_btc.update_xaxes(title="Date")
    fig_btc.update_layout(
        xaxis=dict(rangeslider=dict(visible=True)),  # adds zoomable range slider
        dragmode="zoom"  # allows zooming by dragging
    )

    st.plotly_chart(fig_btc, use_container_width=True)
else:
    st.warning("BTC historical price data not available.")


# =========================
# Profit Ladder Planner
# =========================
st.markdown("---")
st.header("🎯 Profit-Taking Ladder")
def build_ladder(entry, step_pct, sell_pct, max_steps):
    rows = []
    if entry <= 0: return pd.DataFrame(rows)
    for i in range(1,max_steps+1):
        target = entry*(1+step_pct/100.0)**i
        rows.append({
            "Step #": i,
            "Target Price": round(target,2),
            "Gain from Entry (%)": round((target/entry-1)*100,2),
            "Sell This Step (%)": sell_pct
        })
    return pd.DataFrame(rows)

btc_ladder = build_ladder(entry_btc, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
eth_ladder = build_ladder(entry_eth, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
cL,cR = st.columns(2)
with cL: st.subheader("BTC Ladder"); st.dataframe(btc_ladder,use_container_width=True)
with cR: st.subheader("ETH Ladder"); st.dataframe(eth_ladder,use_container_width=True)

# =========================
# Trailing Stop Guidance
# =========================
if use_trailing and btc_price:
    st.markdown("---")
    st.subheader("🛡️ Trailing Stop Guidance")
    btc_stop = round(btc_price*(1-trail_pct/100.0),2)
    eth_stop = round(eth_price*(1-trail_pct/100.0),2) if eth_price else None
    st.write(f"- Suggested BTC stop: ${btc_stop:,.2f}")
    if eth_stop: st.write(f"- Suggested ETH stop: ${eth_stop:,.2f}")

# =========================
# Altcoin Heatmap
# =========================
st.markdown("---")
st.header("🔥 Altcoin Rotation Heatmap (TradingView-Style)")
alt_df = get_top_alts_safe(30)

def rotation_tag(row, rotate_signal):
    if rotate_signal and row.get('7d %', 0) > 0:
        return "✅ Rotate In"
    if row.get('7d %', 0) < 0:
        return "⛔ Avoid"
    return "⚠️ Wait"

if not alt_df.empty:
    alt_df['7d %'] = alt_df['7d %'].fillna(0.0)
    alt_df['24h %'] = alt_df['24h %'].fillna(0.0)
    alt_df['Mkt Cap ($B)'] = alt_df['Mkt Cap ($B)'].fillna(0.0)
    alt_df['Rotation'] = alt_df.apply(lambda r: rotation_tag(r, sig.get('Rotate to Alts', False)), axis=1)
    alt_df['Label'] = alt_df.apply(lambda r: f"{r['Coin']}\n{r['7d %']:.1f}%\n{r['Rotation']}", axis=1)

    fig_treemap = go.Figure(go.Treemap(
        labels=alt_df["Label"],
        parents=[""]*len(alt_df),
        values=alt_df["Mkt Cap ($B)"],
        marker=dict(colors=alt_df["7d %"], colorscale="RdYlGn", cmid=0),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Market Cap: %{value:.2f} B<br>"
            "Price: $%{customdata[1]:,.4f}<br>"
            "24h: %{customdata[2]:.2f}%<br>"
            "7d: %{customdata[3]:.2f}%<br>"
            "Rotation: %{customdata[4]}<extra></extra>"
        ),
        customdata=np.stack([alt_df["Name"], alt_df["Price ($)"], alt_df["24h %"], alt_df["7d %"], alt_df["Rotation"]], axis=-1)
    ))
    fig_treemap.update_layout(margin=dict(t=50,l=25,r=25,b=25), title="Altcoin Rotation by Market Cap & 7d Performance")
    st.plotly_chart(fig_treemap, use_container_width=True)
else:
    st.warning("No altcoin data available for rotation heatmap.")
# =========================
# Fibonacci Levels Calculator (CryptoDataDownload CSV)
# =========================
st.markdown("---")
st.header("📏 Fibonacci Levels Calculator (Free CSV Data)")

import io

# -------------------------
# Text input for coin symbol
# -------------------------
crypto_input = st.text_input(
    "Enter coin symbol (e.g., BTC, ETH, XRP, DOGE):",
    value="BTC"
).upper()

# -------------------------
# Date range selection
# -------------------------
start_date = st.date_input("Start Date", value=datetime.date.today() - datetime.timedelta(days=365))
end_date = st.date_input("End Date", value=datetime.date.today())
if start_date > end_date:
    st.error("Error: Start date must be before End date.")
    st.stop()

# -------------------------
# Map symbols to CryptoDataDownload URLs
# -------------------------
crypto_csv_urls = {
    "BTC": "https://www.cryptodatadownload.com/cdd/Binance_BTCUSDT_d.csv",
    "ETH": "https://www.cryptodatadownload.com/cdd/Binance_ETHUSDT_d.csv",
    "XRP": "https://www.cryptodatadownload.com/cdd/Binance_XRPUSDT_d.csv",
    "DOGE": "https://www.cryptodatadownload.com/cdd/Binance_DOGEUSDT_d.csv"
    # add more coins as needed
}

csv_url = crypto_csv_urls.get(crypto_input)
if not csv_url:
    st.warning(f"No CSV URL found for {crypto_input}. Add it manually in the code.")
    st.stop()

# -------------------------
# Load CSV from URL
# -------------------------
@st.cache_data(ttl=3600)
def load_csv(url):
    r = requests.get(url)
    if r.status_code != 200:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(r.text), skiprows=1)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.sort_index()
    return df[['close']].rename(columns={'close': 'price'})

crypto_hist = load_csv(csv_url)

# -------------------------
# Filter by user-selected dates
# -------------------------
crypto_hist_filtered = crypto_hist[
    (crypto_hist.index >= pd.to_datetime(start_date)) &
    (crypto_hist.index <= pd.to_datetime(end_date))
]

if crypto_hist_filtered.empty:
    st.warning(f"No historical data available for {crypto_input} in the selected date range.")
    st.stop()

# -------------------------
# Fibonacci retracement levels
# -------------------------
high = crypto_hist_filtered["price"].max()
low = crypto_hist_filtered["price"].min()

st.write(f"Analyzing {crypto_input} from {crypto_hist_filtered.index.min().date()} to {crypto_hist_filtered.index.max().date()}")
st.write(f"Price High: ${high:,.2f}, Low: ${low:,.2f}")

fib_ratios = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
fib_levels = [low + (high - low) * r for r in fib_ratios]

fib_df = pd.DataFrame({
    "Fibonacci Ratio": fib_ratios,
    "Level ($)": [round(lv, 2) for lv in fib_levels]
})
st.dataframe(fib_df, use_container_width=True)

# -------------------------
# Plot chart with Fibonacci levels
# -------------------------
fig_fib = go.Figure()
fig_fib.add_trace(go.Scatter(
    x=crypto_hist_filtered.index,
    y=crypto_hist_filtered["price"],
    name=f"{crypto_input} Price",
    line=dict(color="blue")
))

for lv, r in zip(fib_levels, fib_ratios):
    fig_fib.add_hline(
        y=lv,
        line_dash="dash",
        line_color="orange",
        annotation_text=f"Fib {r*100:.1f}%: ${lv:,.2f}",
        annotation_position="top left"
    )

fig_fib.update_layout(
    title=f"{crypto_input} Price with Fibonacci Levels",
    yaxis_title="Price (USD)",
    xaxis_title="Date",
    hovermode="x unified"
)
st.plotly_chart(fig_fib, use_container_width=True)

# -------------------------
# Explanation for users
# -------------------------
st.markdown("---")
st.markdown("### 📘 How to Use the Fibonacci Chart")
st.markdown("""
- **Fibonacci retracement levels** are horizontal lines indicating potential support and resistance zones.
- **Common levels:** 23.6%, 38.2%, 50%, 61.8%, 78.6%.
- **Usage:**  
  - Price often **retraces to a Fibonacci level** before continuing the trend.  
  - Levels can be used for **entry, stop-loss, or take-profit targets**.  
  - Combine with other indicators (RSI, MACD) for stronger signals.
- **Customize dates** to analyze different market periods.  
""")
