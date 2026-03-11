---
name: defillama-api
description: Free DeFi analytics across all chains — TVL, token prices, DEX volumes, fees/revenue, stablecoins, and bridges
---

# DeFiLlama API — DeFi Macro Analytics

DeFiLlama is the largest DeFi TVL aggregator. Its API is **free with no authentication** for most endpoints — covering TVL, token prices, DEX volumes, fees/revenue, stablecoins, and bridges across all chains.

## Quick Start

```python
import httpx

# No auth required for free endpoints
BASE = "https://api.llama.fi"
COINS = "https://coins.llama.fi"

# Current TVL for a protocol
tvl = httpx.get(f"{BASE}/tvl/raydium").json()
print(f"Raydium TVL: ${tvl:,.0f}")

# Token prices (multi-chain)
resp = httpx.get(f"{COINS}/prices/current/solana:So11111111111111111111111111111111111111112")
sol_price = resp.json()["coins"]["solana:So11111111111111111111111111111111111111112"]["price"]
```

## Base URLs

| Service | Base URL | Auth |
|---------|----------|------|
| TVL / Protocols | `https://api.llama.fi` | Free |
| Coin Prices | `https://coins.llama.fi` | Free |
| Stablecoins | `https://stablecoins.llama.fi` | Free |
| Yields | `https://yields.llama.fi` | Pro ($300/mo) |
| Bridges | `https://bridges.llama.fi` | Free (list) / Pro (detail) |
| Pro API | `https://pro-api.llama.fi/{KEY}/api/...` | Pro key in URL path |

**Rate limits**: ~500 requests per 5 minutes (free). Pro: 1,000 req/min, 1M calls/mo.

## TVL & Protocol Data

```python
# List all protocols with TVL
GET /protocols
# Returns: [{name, slug, tvl, chainTvls, change_1h, change_1d, change_7d, category, chains, ...}]

# Detailed protocol data with historical TVL
GET /protocol/{slug}
# Returns: Full object with tvl[], tokensInUsd{}, currentChainTvls{}, ...

# Simple current TVL number
GET /tvl/{slug}
# Returns: plain number (e.g., 150977324562.40)

# TVL for all chains
GET /v2/chains
# Returns: [{name, tvl, tokenSymbol, chainId, gecko_id}]

# Historical chain TVL
GET /v2/historicalChainTvl/{chain}
# chain: "Ethereum", "Solana", "Arbitrum", etc.
# Returns: [{date, tvl}] — date is unix timestamp (seconds)
```

## Token Prices

Coin identifiers use `{chain}:{address}` format:
- `solana:So11111111111111111111111111111111111111112` (SOL)
- `ethereum:0xdac17f958d2ee523a2206206994597c13d831ec7` (USDT)
- `coingecko:bitcoin` (non-chain lookups)

```python
# Current prices (batch)
GET /prices/current/{coins}
# coins: comma-separated identifiers
# Optional: searchWidth (default 4h)
# Returns: {coins: {id: {price, decimals, symbol, timestamp, confidence}}}

# Historical price at timestamp
GET /prices/historical/{timestamp}/{coins}
# timestamp: unix seconds

# Price chart
GET /chart/{coins}?period=1d&span=30
# period: 1d, 4h, 1h
# Returns: {coins: {id: {prices: [{timestamp, price}]}}}

# Price change percentage
GET /percentage/{coins}

# First recorded price
GET /prices/first/{coins}

# Block number at timestamp
GET /block/{chain}/{timestamp}
```

### Batch Historical Prices

```python
# POST for multiple timestamps per coin
POST /batchHistorical
Body: {"coins": {"solana:So11...": [1709251200, 1709337600]}}
```

## DEX Volumes

```python
# All DEXes aggregated
GET /overview/dexs
# Optional: excludeTotalDataChart=true, dataType=dailyVolume

# Chain-specific
GET /overview/dexs/{chain}
# chain: "Solana", "Ethereum", etc.

# Specific DEX
GET /summary/dexs/{protocol}
# Returns: {total24h, total7d, total30d, totalAllTime, totalDataChart, ...}
```

## Fees & Revenue

```python
# All protocols
GET /overview/fees
# Optional: dataType=dailyFees|dailyRevenue|dailyUserFees

# Chain-specific
GET /overview/fees/{chain}

# Specific protocol
GET /summary/fees/{protocol}
# Returns: {total24h, total7d, methodology{}, totalDataChart[], ...}
```

## Stablecoins

```python
# All stablecoins with supply data
GET https://stablecoins.llama.fi/stablecoins
# Returns: [{name, symbol, pegType, circulating, chainCirculating, price}]

# Historical market cap
GET https://stablecoins.llama.fi/stablecoincharts/all

# Chain-specific stablecoin data
GET https://stablecoins.llama.fi/stablecoincharts/{chain}

# Stablecoin prices (deviation tracking)
GET https://stablecoins.llama.fi/stablecoinprices
```

## Bridges

```python
# List all bridges
GET https://bridges.llama.fi/bridges
# Optional: includeChains=true
# Returns: {bridges: [{name, volume stats, chains, ...}]}
```

## Common Patterns

### Protocol TVL Comparison

```python
def compare_protocol_tvl(slugs: list[str]) -> list[dict]:
    """Compare TVL across protocols."""
    results = []
    for slug in slugs:
        resp = httpx.get(f"https://api.llama.fi/tvl/{slug}", timeout=15.0)
        if resp.status_code == 200:
            results.append({"protocol": slug, "tvl": resp.json()})
    return sorted(results, key=lambda x: x["tvl"], reverse=True)
```

### Multi-Token Price Lookup

```python
def get_solana_prices(mints: list[str]) -> dict[str, float]:
    """Get USD prices for Solana tokens via DeFiLlama."""
    coins = ",".join(f"solana:{m}" for m in mints)
    resp = httpx.get(f"https://coins.llama.fi/prices/current/{coins}")
    data = resp.json().get("coins", {})
    return {
        mint: data[f"solana:{mint}"]["price"]
        for mint in mints
        if f"solana:{mint}" in data
    }
```

### Solana DeFi Overview

```python
def solana_defi_snapshot() -> dict:
    """Get a snapshot of Solana DeFi activity."""
    chain_tvl = httpx.get("https://api.llama.fi/v2/chains").json()
    sol_tvl = next((c["tvl"] for c in chain_tvl if c["name"] == "Solana"), 0)

    dex_vol = httpx.get("https://api.llama.fi/overview/dexs/Solana").json()
    fees = httpx.get("https://api.llama.fi/overview/fees/Solana").json()

    return {
        "tvl": sol_tvl,
        "dex_volume_24h": dex_vol.get("total24h", 0),
        "fees_24h": fees.get("total24h", 0),
    }
```

### Historical Price Analysis

```python
def price_at_date(coin: str, date_str: str) -> float:
    """Get token price at a specific date.

    Args:
        coin: DeFiLlama coin ID (e.g., 'solana:So11...')
        date_str: Date string 'YYYY-MM-DD'
    """
    from datetime import datetime, timezone
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ts = int(dt.timestamp())
    resp = httpx.get(f"https://coins.llama.fi/prices/historical/{ts}/{coin}")
    data = resp.json().get("coins", {})
    return data.get(coin, {}).get("price", 0)
```

## Free vs Pro Endpoints

| Category | Free | Pro ($300/mo) |
|----------|------|---------------|
| TVL / Protocols | Yes | Yes |
| Coin Prices | Yes | Yes |
| DEX Volumes (overview) | Yes | Yes |
| Fees/Revenue (overview) | Yes | Yes |
| Stablecoins | Yes | Yes |
| Bridges (list) | Yes | Yes |
| Yields / Pools | No | Yes |
| Bridge detail | No | Yes |
| Derivatives | No | Yes |
| Emissions/Unlocks | No | Yes |
| Treasuries | No | Yes |
| Hacks database | No | Yes |

## When to Use DeFiLlama vs Alternatives

| Need | Use |
|------|-----|
| Protocol TVL comparison | **DeFiLlama** |
| Multi-chain token prices | **DeFiLlama** (free batch) |
| Historical prices at specific timestamps | **DeFiLlama** |
| DeFi macro analysis | **DeFiLlama** |
| Solana token OHLCV | Birdeye or SolanaTracker |
| Real-time token data | DexScreener or Birdeye |
| Wallet PnL | SolanaTracker |
| On-chain transaction data | Helius |

## Files

### References
- `references/endpoints.md` — Complete endpoint listing with parameters and response schemas
- `references/coin_identifiers.md` — Chain prefixes, address formats, and batch lookup patterns
- `references/error_handling.md` — Rate limits, error codes, retry strategies, large response handling

### Scripts
- `scripts/defi_snapshot.py` — Solana DeFi overview: TVL, volumes, fees, top protocols
- `scripts/price_lookup.py` — Multi-token price lookup with historical comparison
