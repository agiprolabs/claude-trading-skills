---
name: solanatracker-api
description: Solana token data, PnL, risk scores, 1-second OHLCV, wallet analytics, and self-hosted swap execution via Raptor
---

# SolanaTracker API — Token Data, Analytics & Raptor DEX Aggregator

SolanaTracker provides comprehensive Solana token data with unique features: **1-second OHLCV resolution**, **wallet PnL tracking**, **risk scoring**, **bundler/sniper detection**, and a **self-hosted DEX aggregator (Raptor)** supporting 25+ DEXes with no rate limits.

## Quick Start

```python
import httpx

API_KEY = os.getenv("SOLANATRACKER_API_KEY", "")
BASE = "https://data.solanatracker.io"
HEADERS = {"x-api-key": API_KEY}

# Token info with risk score, pools, holders
resp = httpx.get(f"{BASE}/tokens/{mint}", headers=HEADERS)
token = resp.json()
print(f"Risk: {token['risk']['score']}/10, Pools: {len(token['pools'])}")

# Wallet PnL
resp = httpx.get(f"{BASE}/pnl/{wallet}", headers=HEADERS)
pnl = resp.json()
print(f"Win rate: {pnl['summary']['winPercentage']}%")
```

## Authentication & Pricing

- **API Key**: From your SolanaTracker dashboard, passed as `x-api-key` header
- **Plans**: Starting ~€50/mo (200K requests), €200/mo (higher volume), Enterprise custom
- **Raptor**: Free during public beta (self-hosted, no rate limits)

## Core Data Endpoints

### Token Data

```python
# Full token info (metadata, pools, risk, events, holders summary)
GET /tokens/{tokenAddress}

# New tokens (paginated, pages 1-10)
GET /tokens/latest?page=1

# Trending by volume (default: past hour)
GET /tokens/trending
GET /tokens/trending/{timeframe}  # 5m, 15m, 30m, 1h, 4h, 12h, 24h

# Top performers
GET /tokens/top

# Graduated from bonding curves (pump.fun → Raydium)
GET /tokens/graduated
GET /tokens/graduating

# Multiple tokens in one request
GET /tokens/multi?tokens=ADDR1,ADDR2

# Deployer's tokens
GET /tokens/deployer/{deployerAddress}

# Token by pool address
GET /tokens/pool/{poolAddress}

# All-time high
GET /tokens/{token}/ath
```

### Price Data

```python
# Current price with liquidity and market cap
GET /price?token={address}

# Price with change percentages
GET /price?token={address}&priceChanges=true

# Historic prices (3d, 5d, 7d, 14d, 30d snapshots)
GET /price/history?token={address}

# Multiple token prices
GET /price/multi?tokens=ADDR1,ADDR2
```

### OHLCV Charts (1-second resolution)

```python
# Candle data — supports 1s resolution (unique to SolanaTracker)
GET /chart/{token}?type=1s&time_from=UNIX&time_to=UNIX

# Timeframes: 1s, 5s, 15s, 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1mn
# Optional: currency=usd|sol|eur, removeOutliers=true, marketCap=true

# Specialized charts
GET /chart/{token}/bundlers   # Bundler activity overlay
GET /chart/{token}/holders    # Holder count overlay
GET /chart/{token}/insiders   # Insider activity overlay
GET /chart/{token}/snipers    # Sniper activity overlay
```

### Wallet PnL

```python
# Full wallet PnL across all tokens
GET /pnl/{wallet}

# Token-specific PnL
GET /pnl/{wallet}/{token}

# First buyers with PnL
GET /first-buyers/{token}

# Optional params: showHistoricPnL=true (1d/7d/30d), holdingCheck=true
```

**PnL response summary fields**: `realized`, `unrealized`, `total`, `totalInvested`, `averageBuyAmount`, `totalWins`, `totalLosses`, `winPercentage`, `lossPercentage`

### Wallet Data

```python
# All tokens held by wallet
GET /wallet/{owner}

# Paginated wallet tokens
GET /wallet/{owner}/paginated

# Trade history
GET /wallet/{owner}/trades

# Portfolio chart over time
GET /wallet/{owner}/chart
```

### Holder Analysis

```python
# Paginated holder list
GET /tokens/{token}/holders?page=1

# Top 100 holders
GET /tokens/{token}/holders/top

# Top 20 holders (lighter)
GET /tokens/{token}/holders/top20

# Bundler detection
GET /tokens/{token}/bundlers
```

### Top Traders

```python
# Global top traders
GET /top-traders/all
GET /top-traders/all/paginated?page=1

# Token-specific top traders
GET /top-traders/{token}

# Optional: expandPnl=true, sortBy=total|winPercentage
```

### Risk Assessment

Risk is included in the `/tokens/{token}` response:

```json
{
  "risk": {
    "score": 7,        // 1-10 (10 = safest)
    "rugged": false,
    "jupiterVerified": true,
    "risks": [
      { "name": "Top 10 holders own 45%", "level": "warn" },
      { "name": "Freeze authority enabled", "level": "danger" }
    ]
  }
}
```

**Risk factors**: sniper/insider concentration, developer holdings, bundler activity, top 10 holder %, mint/freeze authority, social presence, metadata completeness, liquidity.

### Search (30+ filters)

```python
GET /search?query=BONK&minLiquidity=10000&minRiskScore=5&market=raydium&sortBy=volume&limit=50

# Key filters: query, symbol, minLiquidity, maxLiquidity, minMarketCap, maxMarketCap,
# minVolume, maxVolume, hasImage, hasSocials, minHolders, maxHolders, minRiskScore,
# freezeAuthority, mintAuthority, deployer, market, sortBy, sortOrder, limit (max 500), page
```

## Raptor — Self-Hosted DEX Aggregator

> **See the dedicated `raptor-dex` skill** for complete Raptor documentation including setup, API reference, deployment guides, WebSocket streaming, and execution scripts.

Raptor is SolanaTracker's self-hosted DEX aggregator: 25+ DEXes, no rate limits, no API key, Yellowstone Jet TPU submission. [GitHub](https://github.com/solanatracker/raptor-binary) | [Docs](https://docs.solanatracker.io/raptor/overview)

## DataStream WebSocket

Real-time streaming via WebSocket for 30+ event types:

```python
import websockets, json

async def stream():
    uri = f"wss://datastream.solanatracker.io/{DATASTREAM_KEY}"
    async with websockets.connect(uri) as ws:
        # Subscribe to token trades
        await ws.send(json.dumps({"type": "join", "room": f"transaction:{token_addr}"}))
        # Also: price:{token}, holders:{token}, latest_tokens, graduated, etc.
        async for msg in ws:
            data = json.loads(msg)
            if data.get("type") != "joined":
                print(data)
```

**Key channels**: `transaction:{token}`, `price:{token}`, `holders:{token}`, `latest_tokens`, `graduated`, `graduating`, `bundlers:{token}`, `insiders:{token}`, `snipers:{token}`, `wallet_transaction:{wallet}`

## When to Use SolanaTracker vs Alternatives

| Need | Use |
|------|-----|
| 1-second OHLCV candles | **SolanaTracker** |
| Wallet PnL tracking | **SolanaTracker** |
| Token risk scoring | **SolanaTracker** |
| Bundler/sniper detection | **SolanaTracker** |
| Self-hosted swap execution | **Raptor** |
| Free no-auth quick lookup | DexScreener |
| Real-time gRPC streaming | Yellowstone |
| Parsed transaction history | Helius |
| Cross-chain data | DexScreener or CoinGecko |

## Files

### References
- `references/data_api_endpoints.md` — Complete Data API endpoint reference with parameters and response schemas
- `references/raptor_setup.md` — Raptor quick-start reference (full docs in the `raptor-dex` skill)
- `references/risk_and_pnl.md` — Risk scoring methodology and PnL calculation details
- [docs.solanatracker.io/llms-full.txt](https://docs.solanatracker.io/llms-full.txt) — Complete SolanaTracker documentation (13K+ lines, LLM-optimized) covering Data API, Swap API, Datastream WebSocket, Solana RPC, Yellowstone gRPC, SDK libraries, and all endpoint schemas. Fetch on demand rather than embedding.

### Scripts
- `scripts/token_analysis.py` — Fetch token data, risk score, holders, and trades
- `scripts/wallet_pnl.py` — Wallet PnL analysis with win rate and trade breakdown
