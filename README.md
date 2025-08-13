# Bull Run Exit & Rotation Dashboard

A Streamlit app that combines:
- **BTC dominance** triggers (58.29% / 54.66%)
- **ETH/BTC** breakout level (0.054)
- **Fear & Greed Index**
- **Profit-taking ladder** (configurable)
- **Trailing stop guidance**
- **Altcoin performance snapshot** (top N, ex-BTC/ETH)
- TradingView live charts for **BTC.D**, **ETHBTC**, and **BTCUSD**

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
1. Push these files to a new GitHub repo.
2. In Streamlit Cloud, create an app, select your repo and `app.py`.
3. Ensure Python 3.10+ is used. Dependencies are in `requirements.txt`.

## Notes
- Live data: CoinGecko (dominance, prices, alt list) and Alternative.me (Fear & Greed).
- Charts: TradingView widgets embedded via iframes.
- This tool is for **education only** — not financial advice.
