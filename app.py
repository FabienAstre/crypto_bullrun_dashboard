import streamlit as st
import pandas as pd
import numpy as np
import requests
import yfinance as yf

st.set_page_config(page_title="Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")
st.title("🚀 Crypto Bull Run Signals Dashboard")

# =========================
# Helper functions
# =========================
def get_yf_latest(symbol, period="6mo", interval="1d"):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        df.dropna(inplace=True)
        return df
    except:
        return pd.DataFrame()

def get_coingecko_market_chart(coin_id, days="90", vs_currency="usd"):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": vs_currency, "days": days, "interval": "daily"}
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        prices = pd.DataFrame(data["prices"], columns=["timestamp", "price"])
        prices["date"] = pd.to_datetime(prices["timestamp"], unit="ms")
        return prices
    except:
        return pd.DataFrame(columns=["timestamp", "price"])

def get_fear_and_greed():
    try:
        url = "https://api.alternative.me/fng/"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        return int(data["data"][0]["value"])
    except:
        return None

def add_signal(name, description, active):
    """Display a signal only if it has a valid True/False value."""
    if active is None:
        return  # skip if signal cannot be computed
    status = "🟢" if bool(active) else "🔴"
    st.write(f"{status} **{name}** — {description}")

# =========================
# 1. Macro Trend Signals
# =========================
st.subheader("📈 Macro Trend Signals")

# BTC 200D MA
btc_df = get_yf_latest("BTC-USD", period="1y")
btc_above_200dma = None
if not btc_df.empty and len(btc_df) >= 200:
    btc_df["MA200"] = btc_df["Close"].rolling(200).mean()
    try:
        btc_close = float(btc_df["Close"].values[-1])
        btc_ma200 = float(btc_df["MA200"].values[-1])
        if not np.isnan(btc_close) and not np.isnan(btc_ma200):
            btc_above_200dma = btc_close > btc_ma200
    except:
        btc_above_200dma = None
add_signal("BTC > 200D MA", "Long-term bullish structure intact.", btc_above_200dma)

# DXY Downtrend
dxy_df = get_yf_latest("DX-Y.NYB", period="6mo")
dxy_trending_down = None
if not dxy_df.empty:
    try:
        first = float(dxy_df["Close"].values[0])
        last = float(dxy_df["Close"].values[-1])
        dxy_trending_down = last < first
    except:
        dxy_trending_down = None
add_signal("DXY Downtrend", "Weak USD → supports risk assets.", dxy_trending_down)

# NASDAQ Uptrend
nasdaq_df = get_yf_latest("^IXIC", period="6mo")
nasdaq_up = None
if not nasdaq_df.empty:
    try:
        first = float(nasdaq_df["Close"].values[0])
        last = float(nasdaq_df["Close"].values[-1])
        nasdaq_up = last > first
    except:
        nasdaq_up = None
add_signal("NASDAQ Uptrend", "Equities risk-on → crypto-friendly.", nasdaq_up)

# =========================
# 2. Rotation Triggers
# =========================
st.subheader("🔄 Rotation Triggers")

# BTC Dominance (simplified)
btc_market = get_coingecko_market_chart("bitcoin", days="90")
total_market = get_coingecko_market_chart("bitcoin", days="90")  # placeholder
btc_dom_first_break = btc_dom_strong_confirm = None
if not btc_market.empty and not total_market.empty:
    try:
        btc_price = float(btc_market["price"].values[-1])
        total_price = float(total_market["price"].values[-1])
        if total_price != 0:
            btc_dom = btc_price / total_price * 100
            btc_dom_first_break = btc_dom < 50
            btc_dom_strong_confirm = btc_dom < 45
    except:
        btc_dom_first_break = btc_dom_strong_confirm = None
add_signal("BTC Dom < 1st Break", "BTC losing market share → alts may start moving.", btc_dom_first_break)
add_signal("BTC Dom < Strong Confirm", "Major alt rotation confirmed.", btc_dom_strong_confirm)

# ETH/BTC Breakout
ethbtc_df = get_yf_latest("ETH-BTC", period="6mo")
eth_btc_breakout = None
if not ethbtc_df.empty:
    try:
        last = float(ethbtc_df["Close"].values[-1])
        max_val = float(ethbtc_df["Close"].max())
        eth_btc_breakout = last > max_val * 0.98
    except:
        eth_btc_breakout = None
add_signal("ETH/BTC Breakout", "ETH outperforming BTC → bullish for alts.", eth_btc_breakout)

# =========================
# 3. Speculation Heat
# =========================
st.subheader("🔥 Speculation Heat")

# Fear & Greed
fng = get_fear_and_greed()
fng_high = bool(fng >= 80) if fng is not None else None
add_signal("Fear & Greed ≥ 80", "Market extremely greedy → risk of blow-off.", fng_high)

# BTC RSI > 70
rsi_overbought = None
if not btc_df.empty:
    try:
        delta = btc_df["Close"].diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        roll_up = up.rolling(14).mean()
        roll_down = down.rolling(14).mean()
        rs = roll_up / roll_down
        rsi = 100 - (100 / (1 + rs))
        last_rsi = float(rsi.values[-1])
        if not np.isnan(last_rsi):
            rsi_overbought = last_rsi > 70
    except:
        rsi_overbought = None
add_signal("BTC RSI > 70", "BTC potentially overbought.", rsi_overbought)

# BTC Funding Rate High
funding_high = None
try:
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    params = {"symbol": "BTCUSDT", "limit": 1}
    r = requests.get(url, params=params, timeout=20)
    rate = float(r.json()[0]["fundingRate"])
    funding_high = rate > 0.01
except:
    funding_high = None
add_signal("BTC Funding Rate High", "Excessive long leverage in futures.", funding_high)
