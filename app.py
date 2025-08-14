# =========================
# Crypto Bull Run Dashboard v3 with Multi-Day LSTM Forecast
# =========================

import math
import requests
import pandas as pd
import streamlit as st
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
import plotly.express as px

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

st.sidebar.subheader("LSTM Forecast")
forecast_days = st.sidebar.slider("Forecast horizon (days)", 3, 14, 7)

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
    df = pd.DataFrame([{
        "Rank": x["market_cap_rank"],
        "Coin": x["symbol"].upper(),
        "Name": x["name"],
        "Price ($)": x["current_price"],
        "24h %": x.get("price_change_percentage_24h_in_currency"),
        "7d %": x.get("price_change_percentage_7d_in_currency"),
        "30d %": x.get("price_change_percentage_30d_in_currency"),
        "Mkt Cap ($B)": (x["market_cap"] or 0) / 1e9
    } for x in data])
    return df

@st.cache_data(ttl=3600)
def get_history(coin_id, days=60):
    r = requests.get(
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
        params={"vs_currency":"usd","days":days,"interval":"daily"},
        timeout=20
    )
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data['prices'], columns=['timestamp','price'])
    df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('date', inplace=True)
    return df[['price']]

# =========================
# LSTM Multi-Day Forecast
# =========================
def predict_multi_day(df_price, sequence_length=30, forecast_days=7, epochs=50):
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(df_price)
    X, y = [], []
    for i in range(sequence_length, len(scaled_data)):
        X.append(scaled_data[i-sequence_length:i,0])
        y.append(scaled_data[i,0])
    X, y = np.array(X), np.array(y)
    X = X.reshape(X.shape[0], X.shape[1], 1)
    
    model = Sequential()
    model.add(LSTM(50, return_sequences=True, input_shape=(X.shape[1],1)))
    model.add(Dropout(0.2))
    model.add(LSTM(50))
    model.add(Dropout(0.2))
    model.add(Dense(1))
    model.compile(optimizer='adam', loss='mean_squared_error')
    model.fit(X, y, epochs=epochs, batch_size=16, verbose=0)
    
    # Recursive forecast
    last_seq = scaled_data[-sequence_length:].reshape(1, sequence_length,1)
    forecast_scaled = []
    seq = last_seq.copy()
    for _ in range(forecast_days):
        pred_scaled = model.predict(seq, verbose=0)
        forecast_scaled.append(pred_scaled[0,0])
        seq = np.append(seq[:,1:,:], [[pred_scaled[0,0]]], axis=1).reshape(1,sequence_length,1)
    
    forecast_prices = scaler.inverse_transform(np.array(forecast_scaled).reshape(-1,1)).flatten()
    return forecast_prices

def plot_forecast(df_hist, forecast_prices, coin_name):
    last_date = df_hist.index[-1]
    future_dates = [last_date + pd.Timedelta(days=i+1) for i in range(len(forecast_prices))]
    returns = df_hist['price'].pct_change().dropna()
    volatility = returns.std()
    upper_band = forecast_prices * (1 + volatility)
    lower_band = forecast_prices * (1 - volatility)
    
    fig = px.line(df_hist, x=df_hist.index, y='price', title=f"{coin_name} {len(forecast_prices)}-Day Forecast with Confidence Bands")
    fig.add_scatter(x=future_dates, y=forecast_prices, mode='lines+markers', name='Forecast')
    fig.add_scatter(x=future_dates, y=upper_band, fill=None, mode='lines', line=dict(color='lightgreen'), name='Upper Band')
    fig.add_scatter(x=future_dates, y=lower_band, fill='tonexty', mode='lines', line=dict(color='lightcoral'), name='Lower Band')
    return fig

# =========================
# Header Metrics
# =========================
col1, col2, col3, col4 = st.columns(4)
btc_dom, ethbtc = None, None
fg_value, fg_label = get_fear_greed()

try:
    g = get_global()
    btc_dom = float(g["data"]["market_cap_percentage"]["btc"])
    col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}")
except:
    col1.error("BTC.D fetch failed")

try:
    ethbtc = get_ethbtc()
    col2.metric("ETH/BTC", f"{ethbtc:.6f}")
except:
    col2.error("ETH/BTC fetch failed")

if fg_value is not None:
    col3.metric("Fear & Greed", f"{fg_value} ({fg_label})")
else:
    col3.error("Fear & Greed fetch failed")

btc_price, eth_price = None, None
try:
    prices = get_prices_usd(["bitcoin","ethereum"])
    btc_price = float(prices["bitcoin"]["usd"])
    eth_price = float(prices["ethereum"]["usd"])
    col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}")
except:
    col4.error("Price fetch failed")

st.markdown("---")

# =========================
# Profit Ladder
# =========================
def build_ladder(entry, step_pct, sell_pct, max_steps):
    rows=[]
    for i in range(1,max_steps+1):
        target = entry*(1+step_pct/100.0)**i
        rows.append({"Step #":i,"Target Price":round(target,2),
                     "Gain from Entry (%)":round((target/entry-1)*100,2),"Sell This Step (%)":sell_pct})
    return pd.DataFrame(rows)

btc_ladder = build_ladder(entry_btc, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
eth_ladder = build_ladder(entry_eth, ladder_step_pct, sell_pct_per_step, max_ladder_steps)
cL,cR = st.columns(2)
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
# Altcoin Table & Forecast
# =========================
st.header("🔥 Altcoin Watch & Rotation Tables")
alt_df = get_top_alts(top_n_alts)
symbol_to_id = {row['Coin']: row['Name'].lower().replace(" ","-") for i,row in alt_df.iterrows()}

alt_choice = st.selectbox("Select Altcoin to View Forecast", alt_df['Coin'].tolist())
coin_id = symbol_to_id[alt_choice]

try:
    df_hist = get_history(coin_id, days=60)
    forecast_prices = predict_multi_day(df_hist, sequence_length=30, forecast_days=forecast_days)
    fig = plot_forecast(df_hist, forecast_prices, alt_choice)
    st.plotly_chart(fig,use_container_width=True)
except Exception as e:
    st.warning(f"Failed multi-day forecast for {alt_choice}: {e}")

sig_rotate_alts = btc_dom is not None and ethbtc is not None and btc_dom < dom_first and ethbtc > ethbtc_break
alt_df['Suggested Action'] = ['✅ Rotate In' if sig_rotate_alts else '⚠️ Wait' for x in alt_df['7d %']]
st.dataframe(alt_df, use_container_width=True)
if sig_rotate_alts:
    st.success(f"Alt season detected! Consider allocating {target_alt_alloc}% of portfolio into top momentum alts.")
else:
    st.info("No alt season signal detected. Watch these alts and wait for rotation conditions.")
