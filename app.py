import math
import time
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Bull Run Exit & Rotation Dashboard", page_icon="🚀", layout="wide")

# =========================
# Sidebar: User Parameters
# =========================
st.sidebar.header("Parameters")
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

st.sidebar.subheader("Trailing Stop (Optional)
")
use_trailing = st.sidebar.checkbox("Enable trailing stop", value=True)
trail_pct = st.sidebar.slider("Trailing stop (%)", 5, 50, 20)

st.sidebar.subheader("Alt Rotation")
target_alt_alloc = st.sidebar.slider("Target Alt allocation when signals fire (%)", 0, 100, 40)
top_n_alts = st.sidebar.slider("Top N alts to scan (by market cap)", 10, 100, 50, 10)

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
        params={"ids":",\".join(ids), "vs_currencies":"usd"},
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

# =========================
# Signals
# =========================
def build_signals(dom, ethbtc, fg_value):
    sig = {
        "dom_below_first": dom is not None and dom < dom_first,
        "dom_below_second": dom is not None and dom < dom_second,
        "ethbtc_break": ethbtc is not None and ethbtc > ethbtc_break,
        "greed_high": fg_value is not None and fg_value >= 80
    }
    sig["rotate_to_alts"] = sig["dom_below_first"] and sig["ethbtc_break"]
    sig["profit_mode"] = sig["dom_below_second"] or sig["greed_high"]
    sig["full_exit_watch"] = sig["dom_below_second"] and sig["greed_high"]

    # Placeholder historical bull-run signals (demo values, in full version integrate API)
    sig["MVRV_Z"] = True  # assume Z >7
    sig["SOPR_LTH"] = True
    sig["Exchange_Inflow"] = False
    sig["Pi_Cycle_Top"] = False
    sig["Funding_Rate"] = True
    sig["Volume_Divergence"] = False
    return sig

# =========================
# Header Metrics
# =========================
col1, col2, col3, col4 = st.columns(4)

btc_dom = None
ethbtc = None
fg_value, fg_label = get_fear_greed()

try:
    g = get_global()
    btc_dom = float(g["data"]["market_cap_percentage"]["btc"])
    col1.metric("BTC Dominance (%)", f"{btc_dom:.2f}")
except Exception as e:
    col1.error(f"BTC.D fetch failed: {e}")

try:
    ethbtc = get_ethbtc()
    col2.metric("ETH/BTC", f"{ethbtc:.6f}")
except Exception as e:
    col2.error(f"ETH/BTC fetch failed: {e}")

if fg_value is not None:
    col3.metric("Fear & Greed", f"{fg_value} ({fg_label})")
else:
    col3.error("Fear & Greed fetch failed")

btc_price = None
eth_price = None
try:
    prices = get_prices_usd(["bitcoin","ethereum"])
    btc_price = float(prices["bitcoin"]["usd"])
    eth_price = float(prices["ethereum"]["usd"])
    col4.metric("BTC / ETH ($)", f"{btc_price:,.0f} / {eth_price:,.0f}")
except Exception as e:
    col4.error(f"Price fetch failed: {e}")

st.markdown("---")

# =========================
# Signal Panel
# =========================
if btc_dom is not None and ethbtc is not None:
    sig = build_signals(btc_dom, ethbtc, fg_value)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(f"**Dom < {dom_first:.2f}%**: {'🟢 YES' if sig['dom_below_first'] else '🔴 NO'}")
    c2.markdown(f"**Dom < {dom_second:.2f}%**: {'🟢 YES' if sig['dom_below_second'] else '🔴 NO'}")
    c3.markdown(f"**ETH/BTC > {ethbtc_break:.3f}**: {'🟢 YES' if sig['ethbtc_break'] else '🔴 NO'}")
    c4.markdown(f"**F&G ≥ 80**: {'🟢 YES' if sig['greed_high'] else '🔴 NO'}")
    c5.markdown(f"**Rotate to Alts**: {'🟢 GO' if sig['rotate_to_alts'] else '🔴 WAIT'}")

    if sig["profit_mode"]:
        st.success("**Profit-taking mode is ON** — either dominance is in strong-confirm zone or Greed is high.")
    else:
        st.info("**Profit-taking mode is OFF** — wait for confluence or your price targets.")

# =========================
# Historical Bull-Run Signals Panel
# =========================
st.header("📌 Historical Bull-Run Top Signals")
signal_names = ["MVRV_Z","SOPR_LTH","Exchange_Inflow","Pi_Cycle_Top","Funding_Rate","Volume_Divergence"]
signal_desc = {
    "MVRV_Z": "MVRV Z-Score >7 → BTC historically overvalued",
    "SOPR_LTH": "Long-term holder SOPR >1.5 → high profit taking",
    "Exchange_Inflow": "Exchange inflows spike → whales moving BTC to exchanges",
    "Pi_Cycle_Top": "Pi Cycle Top indicator intersects price → major top possible",
    "Funding_Rate": "Perpetual funding >0.2% long → market over-leveraged",
    "Volume_Divergence": "Price up, volume down → momentum weakening"
}
cols = st.columns(len(signal_names))
for i, s in enumerate(signal_names):
    status = sig[s]
    cols[i].markdown(f"**{s}**: {'🟢' if status else '🔴'}")
    cols[i].caption(signal_desc[s])

# =========================
# Profit Ladder Planner
# =========================
st.header("🎯 Profit-Taking Ladder")

# ladder function same as before
def build_ladder(entry, current, step_pct, sell_pct, max_steps):
    rows = []
    if entry <= 0:
        return pd.DataFrame(rows)
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
with cL:
    st.subheader("BTC Ladder")
    st.dataframe(btc_ladder,use_container_width=True)
with cR:
    st.subheader("ETH Ladder")
    st.dataframe(eth_ladder,use_container_width=True)

# Trailing Stop
if use_trailing and btc_price:
    st.markdown("---")
    st.subheader("🛡️ Trailing Stop Guidance")
    btc_stop = round(btc_price*(1-trail_pct/100.0),2)
    eth_stop = round(eth_price*(1-trail_pct/100.0),2) if eth_price else None
    st.write(f"- Suggested BTC stop: ${btc_stop:,.2f}")
    if eth_stop:
        st.write(f"- Suggested ETH stop: ${eth_stop:,.2f}")

# =========================
# Altcoin Rotation Table
# =========================
st.header("🔥 Altcoin Rotation Table")
if sig["rotate_to_alts"]:
    alt_df = get_top_alts(top_n_alts)
    def fmt_pct(x): return None if x is None else round(x,2)
    for col in ["24h %","7d %","30d %"]: alt_df[col] = alt_df[col].map(fmt_pct)
    st.dataframe(alt_df,use_container_width=True)
    st.success(f"Alt season detected! Consider allocating {target_alt_alloc}% of portfolio to top momentum alts.")
else:
    st.info("No alt season signal detected. Stay in BTC / stablecoins.")
