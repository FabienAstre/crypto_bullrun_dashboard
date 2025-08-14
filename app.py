# =========================
# Crypto Bull Run Dashboard v4 (Safe Imports)
# =========================

import math
import requests
import pandas as pd
import streamlit as st
import numpy as np

st.set_page_config(page_title="Crypto Bull Run Dashboard", page_icon="🚀", layout="wide")

# =========================
# Check optional ML packages
# =========================
ml_enabled = True
try:
    from sklearn.preprocessing import MinMaxScaler
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
except ModuleNotFoundError:
    ml_enabled = False
    st.warning("Optional ML packages not found. LSTM forecasts will be disabled. "
               "Install `scikit-learn` and `tensorflow` in requirements.txt to enable.")

try:
    import plotly.express as px
except ModuleNotFoundError:
    st.error("Plotly not installed. Charts will not display. Install `plotly` in requirements.txt.")

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

if ml_enabled:
    st.sidebar.subheader("LSTM Forecast")
    forecast_days = st.sidebar.slider("Forecast horizon (days)", 3, 14, 7)

st.sidebar.caption("Dashboard pulls live data at runtime (CoinGecko & Alternative.me).")

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
        params={"ids":"ethereum","vs_currencies":"btc"}, timeout=20
    )
    r.raise_for_status()
    return float(r.json()["ethereum"]["btc"])

@st.cache_data(ttl=60)
def get_prices_usd(ids):
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": ",".join(ids), "vs_currencies": "usd"}, timeout=20
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
        params={"vs_currency":"usd","order":"market_cap_desc","per_page":n+2,
                "page":1,"sparkline":"false","price_change_percentage":"24h,7d,30d"}, timeout=20
    )
    r.raise_for_status()
    data = [x for x in r.json() if x["symbol"].upper() not in ("BTC","ETH")][:n]
    df = pd.DataFrame([{
        "Rank": x["market_cap_rank"], "Coin": x["symbol"].upper(), "Name": x["name"],
        "Price ($)": x["current_price"],
        "24h %": x.get("price_change_percentage_24h_in_currency"),
        "7d %": x.get("price_change_percentage_7d_in_currency"),
        "30d %": x.get("price_change_percentage_30d_in_currency"),
        "Mkt Cap ($B)": (x["market_cap"] or 0)/1e9
    } for x in data])
    return df

@st.cache_data(ttl=3600)
def get_history(coin_id, days=60):
    r = requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                     params={"vs_currency":"usd","days":days,"interval":"daily"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data['prices'], columns=['timestamp','price'])
    df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('date', inplace=True)
    return df[['price']]

# =========================
# Optional LSTM Forecast
# =========================
if ml_enabled:
    def predict_multi_day(df_price, sequence_length=30, forecast_days=7, epochs=50):
        scaler = MinMaxScaler()
        scaled_data = scaler.fit_transform(df_price)
        X, y = [], []
        for i in range(sequence_length, len(scaled_data)):
            X.append(scaled_data[i-sequence_length:i,0])
            y.append(scaled_data[i,0])
        X, y = np.array(X), np.array(y)
        X = X.reshape(X.shape[0], X.shape[1],1)
        
        model = Sequential()
        model.add(LSTM(50, return_sequences=True, input_shape=(X.shape[1],1)))
        model.add(Dropout(0.2))
        model.add(LSTM(50))
        model.add(Dropout(0.2))
        model.add(Dense(1))
        model.compile(optimizer='adam', loss='mean_squared_error')
        model.fit(X, y, epochs=epochs, batch_size=16, verbose=0)
        
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
        try:
            import plotly.express as px
        except:
            st.warning("Plotly not installed. Cannot render forecast chart.")
            return None
        last_date = df_hist.index[-1]
        future_dates = [last_date + pd.Timedelta(days=i+1) for i in range(len(forecast_prices))]
        returns = df_hist['price'].pct_change().dropna()
        volatility = returns.std()
        upper_band = forecast_prices * (1 + volatility)
        lower_band = forecast_prices * (1 - volatility)
        
        fig = px.line(df_hist, x=df_hist.index, y='price', title=f"{coin_name} {len(forecast_prices)}-Day Forecast")
        fig.add_scatter(x=future_dates, y=forecast_prices, mode='lines+markers', name='Forecast')
        fig.add_scatter(x=future_dates, y=upper_band, fill=None, mode='lines', line=dict(color='lightgreen'), name='Upper Band')
        fig.add_scatter(x=future_dates, y=lower_band, fill='tonexty', mode='lines', line=dict(color='lightcoral'), name='Lower Band')
        return fig

# =========================
# ... rest of dashboard code here: metrics, profit ladder, trailing stop, altcoin tables ...
