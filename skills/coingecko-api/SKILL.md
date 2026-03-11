---
name: coingecko-api
description: >
  Broad crypto market data from CoinGecko covering 13,000+ tokens. Global market
  stats, historical price data going back years, exchange volumes, trending tokens,
  and category filters. Best for macro analysis and long-term historical data.
dependencies:
  - httpx
  - pandas
  - numpy
tags:
  - api
  - market-data
  - crypto
  - historical
  - macro
---

# CoinGecko API Skill

Query the CoinGecko API for comprehensive crypto market data — prices, historical
charts, exchange volumes, trending tokens, global stats, and category breakdowns.
The free tier requires no API key and supports 30 calls/min.

## When to Use This Skill

- **Macro analysis**: Global market cap, BTC dominance, total volume trends
- **Historical data**: Daily/hourly OHLCV going back years (not minutes-level)
- **Cross-exchange comparisons**: Exchange volume rankings and trust scores
- **Trending/discovery**: What tokens are trending on CoinGecko in the last 24h
- **Category analysis**: Compare DeFi vs L1 vs meme coin market caps
- **Token research**: Full metadata including links, description, community stats

Use **Birdeye** or **DexScreener** instead for real-time Solana DEX data, new token
launches, or sub-daily granularity on Solana tokens.

## Quick Start

### Get Current Prices

```python
import httpx

# No API key needed for free tier
resp = httpx.get(
    "https://api.coingecko.com/api/v3/simple/price",
    params={"ids": "solana,bitcoin,ethereum", "vs_currencies": "usd",
            "include_24hr_change": "true"},
)
data = resp.json()
for coin, info in data.items():
    print(f"{coin}: ${info['usd']:.2f} ({info['usd_24h_change']:+.1f}%)")
```

### Get Top Coins by Market Cap

```python
import httpx

resp = httpx.get(
    "https://api.coingecko.com/api/v3/coins/markets",
    params={"vs_currency": "usd", "order": "market_cap_desc",
            "per_page": 10, "page": 1, "sparkline": "false"},
)
for coin in resp.json():
    print(f"{coin['symbol'].upper():>6}  ${coin['current_price']:>10,.2f}  "
          f"MCap: ${coin['market_cap']/1e9:.1f}B  "
          f"24h: {coin['price_change_percentage_24h']:+.1f}%")
```

### Get Historical Price Data

```python
import httpx
import pandas as pd

resp = httpx.get(
    "https://api.coingecko.com/api/v3/coins/solana/market_chart",
    params={"vs_currency": "usd", "days": "90", "interval": "daily"},
)
data = resp.json()
df = pd.DataFrame(data["prices"], columns=["timestamp", "price"])
df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
df = df.set_index("date").drop(columns=["timestamp"])
print(df.describe())
```

### Get OHLC Candle Data

```python
import httpx

resp = httpx.get(
    "https://api.coingecko.com/api/v3/coins/solana/ohlc",
    params={"vs_currency": "usd", "days": "30"},
)
# Returns [[timestamp, open, high, low, close], ...]
candles = resp.json()
for c in candles[-5:]:
    print(f"  O={c[1]:.2f}  H={c[2]:.2f}  L={c[3]:.2f}  C={c[4]:.2f}")
```

### Global Market Stats

```python
import httpx

resp = httpx.get("https://api.coingecko.com/api/v3/global")
g = resp.json()["data"]
print(f"Total Market Cap:  ${g['total_market_cap']['usd']/1e12:.2f}T")
print(f"24h Volume:        ${g['total_volume']['usd']/1e9:.0f}B")
print(f"BTC Dominance:     {g['market_cap_percentage']['btc']:.1f}%")
print(f"Active Coins:      {g['active_cryptocurrencies']:,}")
```

### Trending Coins

```python
import httpx

resp = httpx.get("https://api.coingecko.com/api/v3/search/trending")
for item in resp.json()["coins"]:
    coin = item["item"]
    print(f"#{coin['market_cap_rank'] or '?':>4}  {coin['name']} ({coin['symbol']})")
```

## Authentication

The free tier requires no API key (30 calls/min). For higher limits, get a Pro
key from https://www.coingecko.com/en/api/pricing and set:

```bash
export COINGECKO_API_KEY="CG-xxxxxxxxxxxxxxxxxxxx"
```

Pro requests use a different base URL and header:

```python
import os, httpx

API_KEY = os.getenv("COINGECKO_API_KEY", "")
if API_KEY:
    BASE_URL = "https://pro-api.coingecko.com/api/v3"
    HEADERS = {"x-cg-pro-api-key": API_KEY}
else:
    BASE_URL = "https://api.coingecko.com/api/v3"
    HEADERS = {}
```

## Rate Limiting

Free tier: 30 requests/min. Implement backoff on 429 responses:

```python
import time, httpx

def cg_get(url: str, params: dict, max_retries: int = 3) -> dict:
    """GET with retry on rate limit."""
    for attempt in range(max_retries):
        resp = httpx.get(url, params=params, headers=HEADERS, timeout=15.0)
        if resp.status_code == 429:
            wait = 2 ** attempt * 10
            print(f"Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("Max retries exceeded")
```

## Finding CoinGecko Token IDs

CoinGecko uses slug-style IDs (e.g., `solana`, `bitcoin`, `usd-coin`). To find
an ID from a contract address or name, see `references/id_mapping.md`.

Quick lookup by contract address (useful for Solana tokens):

```python
import httpx

# Look up by Solana contract address
contract = "So11111111111111111111111111111111111111112"
resp = httpx.get(
    "https://api.coingecko.com/api/v3/coins/solana/contract/"
    + contract
)
coin = resp.json()
print(f"ID: {coin['id']}, Name: {coin['name']}")
```

## Key Limitations

- **No real-time data**: Prices update every 1-2 minutes on free tier
- **Limited Solana coverage**: Many newer Solana tokens are not listed
- **OHLC granularity**: Only 1/7/14/30/90/180/365 day windows, candle size
  depends on the window (see `references/endpoints.md`)
- **Historical gaps**: Some tokens have missing data for early periods
- **Free tier throttling**: 30 req/min means batch operations need careful pacing

See `references/data_quality.md` for detailed notes on data gaps and tier differences.

## Files

### References
- `references/endpoints.md` — Complete endpoint reference with parameters, response schemas, and rate limits
- `references/id_mapping.md` — How to find CoinGecko IDs for tokens, contract address mapping, search tips
- `references/data_quality.md` — Data quality notes, historical gaps, free vs pro tier differences

### Scripts
- `scripts/fetch_market_data.py` — Fetch top coins, trending tokens, and global stats (supports `--demo` mode)
- `scripts/historical_analysis.py` — Fetch historical OHLCV data and compute returns, volatility, drawdown (supports `--demo` mode)
