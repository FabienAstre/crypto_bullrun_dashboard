import streamlit as st
import pandas as pd
import numpy as np
import requests
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =========================
# Streamlit page setup
# =========================
st.set_page_config(page_title="Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")
st.title("🚀 Crypto Bull Run Signals Dashboard")

# =========================
# Helper functions
# =========================
def get_yf_latest(symbol, period="6mo", interval="1d"):
    """Fetch Yahoo Finance data and return as DataFrame."""
    df = yf.download(symbol, period=period, interval=interval)
    df.dropna(inplace=True)
    return df

def get_coingecko_market_chart(coin_id, days="90", vs_currency="usd"):
    """Fetch market chart data from CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": vs_currency, "days": days, "interval": "daily"}
    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    prices = pd.DataFrame(data["prices"], columns=["timestamp", "price"])
    prices["date"] = pd.to_datetime(prices["timestamp"], unit="ms")
    return prices

def get_fear_and_greed():
    """Get Fear & Greed Index from Alternative.me."""
    url = "https://api.alternative.me/fng/"
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()
    return int(data["data"][0]["value"])

def get_eth_gas():
    """Fetch current average ETH gas price from Etherscan (free tier)."""
    url = "https://api.etherscan.io/api"
    params = {
        "module": "gastracker",
        "action": "gasoracle",
        "apikey": "YourApiKeyToken"  # Replace with free API key from etherscan.io
    }
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        result = r.json()["result"]
        return int(result["ProposeGasPrice"])
    except:
        return None

# =========================
# Signals Section
# =========================
def add_signal(name, description, active):
    """Display a signal row with status."""
    active_bool = bool(active)  # Ensure single True/False
    status = "🟢" if active_bool else "🔴"
    st.write(f"{status} **{name}** — {description}")

# =========================
# 1. Macro Trend
# =========================
st.subheader("📈 Macro Trend Signals")

# BTC above 200D MA
btc_df = get_yf_latest("BTC-USD", period="1y")
btc_df["MA200"] = btc_df["Close"].rolling(window=200).mean()
btc_above_200dma = btc_df["Close"].iloc[-1] > btc_df["MA200"].iloc[-1]
add_signal("BTC > 200D MA", "Long-term bullish structure intact.", btc_above_200dma)

# DXY trend
dxy_df = get_yf_latest("DX-Y.NYB", period="6mo")
dxy_trending_down = dxy_df["Close"].iloc[-1] < dxy_df["Close"].iloc[0]
add_signal("DXY Downtrend", "Weak USD → supports risk assets.", dxy_trending_down)

# NASDAQ uptrend
nasdaq_df = get_yf_latest("^IXIC", period="6mo")
nasdaq_up = nasdaq_df["Close"].iloc[-1] > nasdaq_df["Close"].iloc[0]
add_signal("NASDAQ Uptrend", "Equities risk-on → crypto-friendly.", nasdaq_up)

# =========================
# 2. Rotation Triggers
# =========================
st.subheader("🔄 Rotation Triggers")

# BTC Dominance
dom_df = get_coingecko_market_chart("bitcoin", days="90")
eth_df = get_coingecko_market_chart("ethereum", days="90")
total_df = get_coingecko_market_chart("bitcoin", days="90")  # Placeholder, ideally total market cap
btc_dominance = (dom_df["price"].iloc[-1] / total_df["price"].iloc[-1]) * 100 if total_df["price"].iloc[-1] != 0 else 0
btc_dom_first_break = btc_dominance < 50  # Example threshold
btc_dom_strong_confirm = btc_dominance < 45
add_signal("BTC Dom < 1st Break", "BTC losing market share → alts may start moving.", btc_dom_first_break)
add_signal("BTC Dom < Strong Confirm", "Major alt rotation confirmed.", btc_dom_strong_confirm)

# ETH/BTC breakout
eth_btc_df = get_yf_latest("ETH-BTC", period="6mo")
eth_btc_breakout = eth_btc_df["Close"].iloc[-1] > eth_btc_df["Close"].max() * 0.98
add_signal("ETH/BTC Breakout", "ETH outperforming BTC → bullish for alts.", eth_btc_breakout)

# =========================
# 3. Speculation Heat
# =========================
st.subheader("🔥 Speculation Heat")

# Fear & Greed
fng = get_fear_and_greed()
fng_high = fng >= 80
add_signal("Fear & Greed ≥ 80", "Market extremely greedy → risk of blow-off.", fng_high)

# RSI > 70
btc_df["RSI"] = 100 - (100 / (1 + btc_df["Close"].pct_change().apply(lambda x: max(x,0)).mean() /
                             abs(btc_df["Close"].pct_change().apply(lambda x: min(x,0)).mean())))
rsi_overbought = btc_df["RSI"].iloc[-1] > 70
add_signal("BTC RSI > 70", "BTC potentially overbought.", rsi_overbought)

# BTC Funding Rate (Binance)
try:
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    params = {"symbol": "BTCUSDT", "limit": 1}
    r = requests.get(url, params=params)
    funding_rate = float(r.json()[0]["fundingRate"])
    funding_high = funding_rate > 0.01
except:
    funding_high = False
add_signal("BTC Funding Rate High", "Excessive long leverage in futures.", funding_high)

# ETH Gas Spike
gas_price = get_eth_gas()
gas_high = gas_price is not None and gas_price > 80
add_signal("ETH Gas Spike", "High gas fees → network congestion & hype.", gas_high)

# Meme Coin Surge (using DOGE as proxy)
doge_df = get_yf_latest("DOGE-USD", period="1mo")
meme_surge = doge_df["Close"].iloc[-1] > doge_df["Close"].iloc[0] * 1.5
add_signal("Meme Coin Surge", "Speculative mania spilling into meme coins.", meme_surge)
