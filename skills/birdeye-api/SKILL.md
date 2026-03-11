---
name: birdeye-api
description: Solana token market data via Birdeye — prices, OHLCV, trades, token metadata, security checks, and trader activity
---

# Birdeye API — Solana Market Data

Birdeye aggregates market data across all Solana DEXes (and 13 other chains). Prices, OHLCV candles, trade history, token metadata, security info, and wallet analytics. Primary data source for Solana token research and historical analysis.

**Note**: For real-time trading systems, use Yellowstone gRPC (see `yellowstone-grpc` skill). Birdeye is best for historical data, research, and analysis workflows.

## Quick Start

### 1. Get an API Key

Sign up at [birdeye.so](https://birdeye.so) — free tier: 30K compute units/month, 1 req/sec.

```bash
export BIRDEYE_API_KEY="your-api-key"
```

### 2. Install Dependencies

```bash
uv pip install httpx pandas python-dotenv
```

### 3. First Request

```python
import httpx, os

API_KEY = os.environ["BIRDEYE_API_KEY"]
headers = {"X-API-KEY": API_KEY, "x-chain": "solana", "accept": "application/json"}

# Get SOL price
resp = httpx.get(
    "https://public-api.birdeye.so/defi/price",
    headers=headers,
    params={"address": "So11111111111111111111111111111111111111112"},
)
price = resp.json()["data"]["value"]
print(f"SOL: ${price}")
```

## Core Endpoints

All endpoints use base URL `https://public-api.birdeye.so` with `X-API-KEY` and `x-chain` headers.

### Token Price

```python
# Single token price (10 CU)
GET /defi/price?address=TOKEN_MINT

# Multiple token prices (variable CU)
POST /defi/multi_price
Body: {"addresses": ["MINT1", "MINT2", "MINT3"]}

# Price at specific timestamp (10 CU)
GET /defi/historical_price_unix?address=TOKEN_MINT&unixtime=1700000000

# Historical price series (60 CU)
GET /defi/history_price?address=TOKEN_MINT&address_type=token&type=15m&time_from=T1&time_to=T2
```

### OHLCV Candles

The primary endpoint for backtesting data.

```python
# Token OHLCV (40 CU, max 1000 candles per request)
GET /defi/ohlcv?address=TOKEN_MINT&type=15m&time_from=T1&time_to=T2
```

**Timeframes**: `1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 8H, 12H, 1D, 3D, 1W, 1M`

Response:
```json
{
  "data": {
    "items": [
      {"o": 23.5, "h": 24.1, "l": 23.2, "c": 23.8, "v": 1234567.89, "unixTime": 1692175200, "type": "15m"}
    ]
  },
  "success": true
}
```

**Pagination for long history**: Max 1000 candles per request. At 15m intervals, 1000 candles ≈ 10.4 days. Slide `time_from`/`time_to` windows for longer history.

```python
# Pair OHLCV (40 CU)
GET /defi/ohlcv/pair?address=PAIR_ADDRESS&type=1H&time_from=T1&time_to=T2
```

### Token Overview

Comprehensive metadata + market data in one call.

```python
# Token overview (30 CU)
GET /defi/token_overview?address=TOKEN_MINT
```

Returns: `name`, `symbol`, `decimals`, `logoURI`, `liquidity`, `price`, `mc` (market cap), `supply`, price changes (30m/1h/2h/4h/6h/8h/12h/24h), trade counts, buy/sell volumes, unique wallets, and social links.

See `references/birdeye_endpoints.md` for full field listing.

### Token Security

Pre-trade safety check — essential before entering any new token.

```python
# Token security (50 CU)
GET /defi/token_security?address=TOKEN_MINT
```

Returns:
- `creatorAddress`, `ownerAddress` — who controls the token
- `top10HolderPercent` — concentration risk
- `mutableMetadata` — can metadata be changed?
- `freezeable`, `freezeAuthority` — can tokens be frozen?
- `transferFeeEnable` — Token-2022 transfer fees?
- `isToken2022` — which token program?
- `lockInfo` — LP lock details

**Quick safety checks**:
- Mintable = `ownerAddress != null` (supply can increase)
- Renounced = `ownerAddress == null` (no mint authority)
- Mutable = `mutableMetadata == true`
- Freezeable = `freezeable == true`

### Trades

```python
# Recent trades for a token (10 CU)
GET /defi/txs/token?address=TOKEN_MINT&limit=50&tx_type=swap

# Trades by time range (15 CU)
GET /defi/txs/token/seek_by_time?address=TOKEN_MINT&after_time=UNIX_TS&limit=50
# WARNING: do NOT pass both before_time and after_time — returns 422
```

Trade response fields: `txHash`, `source` (DEX), `blockUnixTime`, `owner` (trader), `from` (token sent), `to` (token received) with amounts and prices.

### Top Traders

```python
# Top traders for a token (30 CU)
GET /defi/v2/tokens/top_traders?address=TOKEN_MINT&time_frame=24h&sort_by=volume&limit=10
```

Returns: `owner`, `volume`, `volumeBuy`, `volumeSell`, `trade`, `tradeBuy`, `tradeSell`, `tags` (e.g., `"arbitrage-bot"`, `"sniper-bot"`).

### New Listings

```python
# New token listings (80 CU)
GET /defi/v2/tokens/new_listing?time_to=UNIX_TS&limit=10&meme_platform_enabled=true
```

Returns tokens listed within ~3 days with liquidity ≥ $10. Set `meme_platform_enabled=true` to include PumpFun tokens.

### Trending Tokens

```python
# Trending tokens (50 CU)
GET /defi/token_trending?sort_by=rank&sort_type=asc&limit=20
```

### Token Holders

```python
# Token holders (50 CU)
GET /defi/v3/token/holder?address=TOKEN_MINT
```

### Search

```python
# Search tokens/markets (50 CU)
GET /defi/v3/search?keyword=bonk&chain=solana
```

## Wallet Endpoints

**Rate limited**: 30 rpm across all wallet endpoints regardless of tier.

```python
# Wallet portfolio (100 CU)
GET /v1/wallet/token_list?wallet=WALLET_ADDRESS

# Single token balance (5 CU)
GET /v1/wallet/token_balance?wallet=WALLET&token_address=TOKEN_MINT

# Wallet transaction history (150 CU)
GET /v1/wallet/tx_list?wallet=WALLET_ADDRESS

# Wallet net worth (100 CU)
GET /wallet/v2/current-net-worth?wallet=WALLET_ADDRESS

# Wallet PnL (variable CU)
GET /wallet/v2/pnl?wallet=WALLET_ADDRESS
```

## WebSocket API

Real-time streaming for price, trades, and new listings. Requires Premium Plus ($250/mo) or higher.

```python
# Connection URL
wss://public-api.birdeye.so/socket/solana?x-api-key=YOUR_KEY

# Required headers
Origin: ws://public-api.birdeye.so
Sec-WebSocket-Protocol: echo-protocol

# Subscribe to price updates
{"type": "SUBSCRIBE_PRICE", "data": {"chartType": "1m", "address": "TOKEN", "currency": "usd"}}

# Subscribe to trades
{"type": "SUBSCRIBE_TXS", "data": {"address": "TOKEN"}}

# Subscribe to new listings
{"type": "SUBSCRIBE_TOKEN_NEW_LISTING", "data": {}}
```

Max 100 tokens per connection. Channels: `SUBSCRIBE_PRICE`, `SUBSCRIBE_TXS`, `SUBSCRIBE_TOKEN_NEW_LISTING`, `SUBSCRIBE_NEW_PAIR`, `SUBSCRIBE_LARGE_TRADE_TXS`, `SUBSCRIBE_WALLET_TXS`, `SUBSCRIBE_TOKEN_STATS`.

## Pricing & CU Budget

| Tier | Price/mo | CU | Rate Limit |
|------|----------|-----|-----------|
| Free | $0 | 30K | 1 rps |
| Lite | $39 | 1.5M | 15 rps |
| Starter | $99 | 5M | 15 rps |
| Premium | $199 | 15M | 50 rps |
| Premium Plus | $250 | 20M | 50 rps + WebSocket |
| Business | $499-$2,300 | 50M-500M | 100-150 rps |

**CU planning**: Free tier (30K CU) = ~750 price calls OR ~375 OHLCV calls/month. Budget accordingly.

## Files

### References
- `references/birdeye_endpoints.md` — Complete endpoint listing with parameters, CU costs, and response fields
- `references/error_handling.md` — Error codes, rate limits, retry strategies, CU optimization
- `references/token_overview_fields.md` — Full field reference for token_overview response

### Scripts
- `scripts/fetch_ohlcv.py` — Fetch OHLCV candle data with pagination for backtesting
- `scripts/token_screener.py` — Screen tokens using overview, security, and trader data
