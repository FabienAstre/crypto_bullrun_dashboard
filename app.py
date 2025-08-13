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

st.sidebar.subheader("New Indicator Settings")
alt_season_threshold = st.sidebar.slider("Alt Season Ratio threshold (Alts/BTC)", 0.05, 0.50, 0.15, 0.01)
vol_spike_multiple = st.sidebar.slider("Volume spike: X × 7d average", 1.0, 5.0, 2.0, 0.1)

st.sidebar.caption("Live data from CoinGecko & Alternative.me. Cached with retries & fallbacks.")

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
    return safe_request("https://api.coingecko.com/api/v3/global")

@st.cache_data(ttl=300)
def get_ethbtc():
    data = safe_request("https://api.coingecko.com/api/v3/simple/price",
                        params={"ids":"ethereum","vs_currencies":"btc"})
    return float(data["ethereum"]["btc"]) if data and "ethereum" in data else None

@st.cache_data(ttl=300)
def get_prices_usd(ids):
    data = safe_request("https://api.coingecko.com/api/v3/simple/price",
                        params={"ids": ",".join(ids), "vs_currencies": "usd"})
    return data if data else {i: {"usd": None} for i in ids}

@st.cache_data(ttl=300)
def get_fear_greed():
    data = safe_request("https://api.alternative.me/fng/")
    if data and "data" in data and data["data"]:
        fg = data["data"][0]
        return int(fg.get("value", 50)), fg.get("value_classification", "Neutral")
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
        "Mkt Cap ($B)": (x.get("market_cap") or 0) / 1e9
    } for x in data])

# Historical prices & volumes (for indicators)
@st.cache_data(ttl=900)
def get_market_chart(coin_id, days):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval":"daily"}
    data = safe_request(url, params)
    if not data or "prices" not in data:
        return pd.DataFrame()
    dfp = pd.DataFrame(data["prices"], columns=["ts","price"])
    dfv = pd.DataFrame(data.get("total_volumes", []), columns=["ts","volume"])
    df = pd.merge(dfp, dfv, on="ts", how="left")
    df["Date"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("Date").drop(columns=["ts"])
    df = df.rename(columns={"price":"Price","volume":"Volume"})
    return df

# =========================
# Helper calcs: SMA, RSI, Cross, Volume Spike
# =========================
def sma(series, window):
    return series.rolling(window).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val

def detect_cross(short_sma, long_sma):
    if len(short_sma.dropna()) < 2 or len(long_sma.dropna()) < 2:
        return None
    diff_prev = short_sma.iloc[-2] - long_sma.iloc[-2]
    diff_now  = short_sma.iloc[-1] - long_sma.iloc[-1]
    if np.isnan(diff_prev) or np.isnan(diff_now):
        return None
    if diff_prev <= 0 and diff_now > 0:
        return "golden"
    if diff_prev >= 0 and diff_now < 0:
        return "death"
    return None

def volume_spike_flag(vol_series, multiple=2.0, window=7):
    if len(vol_series.dropna()) < window + 1:
        return None, None, None
    latest = vol_series.iloc[-1]
    avg7 = vol_series.iloc[-window-1:-1].mean()
    spike = latest >= multiple * avg7 if avg7 and not np.isnan(avg7) else False
    return spike, latest, avg7

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
# Header metrics
# =========================
col1, col2, col3, col4 = st.columns(4)

g = get_global()
btc_dom = None
if g and "data" in g and "market_cap_percentage" in g["data"]:
    try:
        btc_dom = float(g["data"]["market_cap_percentage"].get("btc", 0))
    except Exception:
        btc_dom = None

if btc_dom is None:
    st.warning("⚠️ BTC Dominance could not be fetched. Using fallback value for signals.")
    btc_dom = 60.0

ethbtc_val = get_ethbtc()
if ethbtc_val is None:
    st.warning("⚠️ ETH/BTC could not be fetched. Signals may be inaccurate.")
    ethbtc_val = 0.05

fg_value, fg_label = get_fear_greed()
if fg_value is None:
    st.warning("⚠️ Fear & Greed index could not be fetched. Using Neutral fallback.")
    fg_value, fg_label = 50, "Neutral"

prices = get_prices_usd(["bitcoin","ethereum"])
btc_price = prices.get("bitcoin",{}).get("usd")
eth_price = prices.get("ethereum",{}).get("usd")

col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}" if btc_dom is not None else "N/A")
col2.metric("ETH/BTC", f"{ethbtc_val:.6f}" if ethbtc_val is not None else "N/A")
col3.metric("Fear & Greed", f"{fg_value} ({fg_label})" if fg_value is not None else "N/A")
col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}" if btc_price and eth_price else "N/A")
st.markdown("---")

# =========================
# Signals Panel with Explanation
# =========================
sig = build_signals(btc_dom, ethbtc_val, fg_value)

st.subheader("⚡ Signals & Actionable Advice")
c1, c2, c3, c4 = st.columns(4)
actions = []
# Dom < first
if sig['dom_below_first']:
    c1.success(f"Dom < {dom_first:.2f}% ✅")
    actions.append("BTC dominance low: Consider altcoin rotation.")
else:
    c1.error(f"Dom < {dom_first:.2f}% ❌")
    actions.append("BTC dominance high: Stay in BTC or stablecoins.")

# Dom < second
if sig['dom_below_second']:
    c2.success(f"Dom < {dom_second:.2f}% ✅")
    actions.append("Strong alt season signal: Evaluate profit-taking and alt rotation.")
else:
    c2.error(f"Dom < {dom_second:.2f}% ❌")

# ETH/BTC breakout
if sig['ethbtc_break']:
    c3.success(f"ETH/BTC > {ethbtc_break:.3f} ✅")
    actions.append("ETH outperforming BTC: Potential alt rotation opportunity.")
else:
    c3.error(f"ETH/BTC > {ethbtc_break:.3f} ❌")

# F&G ≥ 80
if sig['greed_high']:
    c4.success(f"F&G ≥ 80 ✅")
    actions.append("Market greed high: Consider taking profits.")
else:
    c4.error(f"F&G ≥ 80 ❌")

# Profit-taking mode
if sig["profit_mode"]:
    st.success("Profit-taking mode is ON")
else:
    st.info("Profit-taking mode is OFF")

st.markdown("**Suggested Actions:**")
for a in actions:
    st.markdown(f"- {a}")

# =========================
# Extra Indicators
# =========================
st.subheader("📌 Extra Indicators")

btc_hist = get_market_chart("bitcoin", 240)
eth_hist = get_market_chart("ethereum", 240)

# RSI
btc_rsi_val = float(rsi(btc_hist["Price"],14).iloc[-1]) if not btc_hist.empty else None
eth_rsi_val = float(rsi(eth_hist["Price"],14).iloc[-1]) if not eth_hist.empty else None

# Alt Season Ratio
alt_season_ratio = None
if g and "data" in g and "total_market_cap" in g["data"] and "market_cap_percentage" in g["data"]:
    try:
        total_usd = g["data"]["total_market_cap"].get("usd", None)
        btc_pct = g["data"]["market_cap_percentage"].get("btc", None)
        if total_usd and btc_pct is not None and btc_pct > 0:
            btc_mcap = total_usd * (btc_pct / 100.0)
            alt_mcap = total_usd - btc_mcap
            alt_season_ratio = alt_mcap / btc_mcap if btc_mcap > 0 else None
    except Exception:
        alt_season_ratio = None
if alt_season_ratio is None:
    st.warning("⚠️ Alt Season Ratio not available (global mkt data issue).")

# Volume spikes
btc_vol_spike, btc_vol_latest, btc_vol_avg7 = volume_spike_flag(btc_hist["Volume"], vol_spike_multiple, window=7) if not btc_hist.empty else (None,None,None)
eth_vol_spike, eth_vol_latest, eth_vol_avg7 = volume_spike_flag(eth_hist["Volume"], vol_spike_multiple, window=7) if not eth_hist.empty else (None,None,None)

i1, i2, i3, i4 = st.columns(4)
i3.markdown(f"**BTC RSI(14):** {btc_rsi_val:.1f}" if btc_rsi_val else "BTC RSI(14): N/A")
i4.markdown(f"**ETH RSI(14):** {eth_rsi_val:.1f}" if eth_rsi_val else "ETH RSI(14): N/A")

j1, j2, j3 = st.columns(3)
if alt_season_ratio:
    j1.success(f"Alt Season Ratio: {alt_season_ratio:.2f}")
else:
    j1.warning("Alt Season Ratio: N/A ⚠️")

def fmt_vol(v):
    return f"${v/1e9:.2f}B" if v and v >= 1e9 else (f"${v/1e6:.1f}M" if v and v >= 1e6 else (f"${v:,.0f}" if v else "N/A"))

if btc_vol_spike is None:
    j2.warning("BTC Volume Spike: N/A ⚠️")
else:
    j2.markdown(f"**BTC Vol Spike:** {'✅ Yes' if btc_vol_spike else 'No'} (Latest: {fmt_vol(btc_vol_latest)}, 7d Avg: {fmt_vol(btc_vol_avg7)})")

if eth_vol_spike is None:
    j3.warning("ETH Volume Spike: N/A ⚠️")
else:
    j3.markdown(f"**ETH Vol Spike:** {'✅ Yes' if eth_vol_spike else 'No'} (Latest: {fmt_vol(eth_vol_latest)}, 7d Avg: {fmt_vol(eth_vol_avg7)})")

st.caption("Tip: RSI>70 may be overbought; RSI<30 oversold.")

# =========================
# Combined Profit Ladder
# =========================
st.subheader("💰 Combined Profit Ladder (BTC & ETH)")
btc_ladder = build_profit_ladder(entry_btc, ladder_step_pct, sell_pct_per_step, max_ladder_steps); btc_ladder["Coin"]="BTC"
eth_ladder = build_profit_ladder(entry_eth, ladder_step_pct, sell_pct_per_step, max_ladder_steps); eth_ladder["Coin"]="ETH"
combined_ladder = pd.concat([btc_ladder, eth_ladder], ignore_index=True)
combined_ladder = combined_ladder[["Coin", "Step", "Price Target", "% Gain", "Sell %"]]
st.dataframe(combined_ladder, use_container_width=True)

# =========================
# Top Altcoins Table (Buying Chart)
# =========================
st.subheader("🔥 Top Altcoins & Suggested Actions")
alt_df = get_top_alts(top_n_alts)
if sig["rotate_to_alts"] and not alt_df.empty:
    alt_df['Suggested Action'] = f'✅ Buy / Allocate ~{target_alt_alloc}%'
else:
    alt_df['Suggested Action'] = '⚠️ Wait / Hold'
st.dataframe(alt_df, use_container_width=True)

# =========================
# Live Crypto News Feed
# =========================
st.subheader("📰 Crypto News Feed")
try:
    feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/")
    if feed.entries:
        for entry in feed.entries[:10]:
            st.markdown(f"[{entry.title}]({entry.link})")
    else:
        st.info("No news available right now. Try refreshing.")
except Exception as e:
    st.warning(f"News feed could not be loaded: {str(e)}")
