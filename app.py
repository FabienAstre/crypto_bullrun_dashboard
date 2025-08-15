import streamlit as st
import pandas as pd
import numpy as np
import requests
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")
st.title("🚀 Crypto Bull Run Signals Dashboard")

# =========================
# Helper functions
# =========================
def get_yf_latest(symbol, period="6mo", interval="1d"):
    """Fetch Yahoo Finance data and return as DataFrame."""
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    df.dropna(inplace=True)
    return df

def get_coingecko_market_chart(coin_id, days="90", vs_currency="usd"):
    """Fetch market chart data from CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": vs_currency, "days": days, "interval": "daily"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    prices = pd.DataFrame(data["prices"], columns=["timestamp", "price"])
    prices["date"] = pd.to_datetime(prices["timestamp"], unit="ms")
    return prices

def get_fear_and_greed():
    """Get Fear & Greed Index from Alternative.me."""
    try:
        url = "https://api.alternative.me/fng/"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        return int(data["data"][0]["value"])
    except:
        return None

# =========================
# Signal display function
# =========================
def add_signal(name, description, active):
    """Display a signal row with status."""
    status = "🟢" if active else "🔴"
    st.write(f"{status} **{name}** — {description}")

# =========================
# 1. Macro Trend Signals
# =========================
st.subheader("📈 Macro Trend Signals")

# BTC 200D MA
btc_df = get_yf_latest("BTC-USD", period="1y")
btc_df["MA200"] = btc_df["Close"].rolling(window=200).mean()
btc_above_200dma = False
if not btc_df.empty and not pd.isna(btc_df["MA200"].iloc[-1]):
    btc_above_200dma = btc_df["Close"].iloc[-1] > btc_df["MA200"].iloc[-1]
add_signal("BTC > 200D MA", "Long-term bullish structure intact.", btc_above_200dma)

# DXY downtrend
dxy_df = get_yf_latest("DX-Y.NYB", period="6mo")
dxy_trending_down = False
if not dxy_df.empty:
    dxy_trending_down = dxy_df["Close"].iloc[-1] < dxy_df["Close"].iloc[0]
add_signal("DXY Downtrend", "Weak USD → supports risk assets.", dxy_trending_down)

# NASDAQ uptrend
nasdaq_df = get_yf_latest("^IXIC", period="6mo")
nasdaq_up = False
if not nasdaq_df.empty:
    nasdaq_up = nasdaq_df["Close"].iloc[-1] > nasdaq_df["Close"].iloc[0]
add_signal("NASDAQ Uptrend", "Equities risk-on → crypto-friendly.", nasdaq_up)

# =========================
# 2. Rotation Triggers
# =========================
st.subheader("🔄 Rotation Triggers")

# BTC Dominance
btc_market = get_coingecko_market_chart("bitcoin", days="90")
total_market = get_coingecko_market_chart("bitcoin", days="90")  # Placeholder
btc_dominance = 0
if not btc_market.empty and not total_market.empty and total_market["price"].iloc[-1] != 0:
    btc_dominance = (btc_market["price"].iloc[-1] / total_market["price"].iloc[-1]) * 100

btc_dom_first_break = btc_dominance < 50
btc_dom_strong_confirm = btc_dominance < 45
add_signal("BTC Dom < 1st Break", "BTC losing market share → alts may start moving.", btc_dom_first_break)
add_signal("BTC Dom < Strong Confirm", "Major alt rotation confirmed.", btc_dom_strong_confirm)

# ETH/BTC breakout
ethbtc_df = get_yf_latest("ETH-BTC", period="6mo")
eth_btc_breakout = False
if not ethbtc_df.empty:
    eth_btc_breakout = ethbtc_df["Close"].iloc[-1] > ethbtc_df["Close"].max() * 0.98
add_signal("ETH/BTC Breakout", "ETH outperforming BTC → bullish for alts.", eth_btc_breakout)

# =========================
# 3. Speculation Heat
# =========================
st.subheader("🔥 Speculation Heat")

# Fear & Greed
fng = get_fear_and_greed()
fng_high = fng >= 80 if fng is not None else False
add_signal("Fear & Greed ≥ 80", "Market extremely greedy → risk of blow-off.", fng_high)

# BTC RSI > 70
rsi_overbought = False
if not btc_df.empty:
    delta = btc_df["Close"].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    roll_up = up.rolling(14).mean()
    roll_down = down.rolling(14).mean()
    rs = roll_up / roll_down
    rsi = 100 - (100 / (1 + rs))
    if not pd.isna(rsi.iloc[-1]):
        rsi_overbought = rsi.iloc[-1] > 70
add_signal("BTC RSI > 70", "BTC potentially overbought.", rsi_overbought)

# BTC Funding Rate High (Binance)
funding_high = False
try:
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    params = {"symbol": "BTCUSDT", "limit": 1}
    r = requests.get(url, params=params, timeout=20)
    funding_rate = float(r.json()[0]["fundingRate"])
    funding_high = funding_rate > 0.01
except:
    funding_high = False
add_signal("BTC Funding Rate High", "Excessive long leverage in futures.", funding_high)
