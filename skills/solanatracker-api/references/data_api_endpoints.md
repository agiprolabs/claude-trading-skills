# SolanaTracker Data API — Endpoints Reference

Base URL: `https://data.solanatracker.io`
Authentication: `x-api-key` header

---

## Token Endpoints

### Get Token Info
- **Endpoint**: `GET /tokens/{tokenAddress}`
- **Response**: Full token object with metadata, pools, risk, events, holder summary
- **Notes**: Most comprehensive single-call endpoint. Includes risk score, all pools, and recent events.

```bash
curl -H "x-api-key: $KEY" "https://data.solanatracker.io/tokens/So11111111111111111111111111111111111111112"
```

### Latest Tokens
- **Endpoint**: `GET /tokens/latest`
- **Parameters**: `page` (1-10)
- **Response**: Array of newly created tokens
- **Notes**: Useful for monitoring new launches. Updates frequently.

### Trending Tokens
- **Endpoint**: `GET /tokens/trending` or `GET /tokens/trending/{timeframe}`
- **Timeframes**: `5m`, `15m`, `30m`, `1h`, `4h`, `12h`, `24h`
- **Response**: Top 100 tokens by volume for the timeframe

### Graduated / Graduating
- **Endpoint**: `GET /tokens/graduated`, `GET /tokens/graduating`
- **Response**: Tokens that graduated from bonding curves (e.g., pump.fun → Raydium)
- **Notes**: Key signal for tokens transitioning to real liquidity pools.

### Multiple Tokens
- **Endpoint**: `GET /tokens/multi`
- **Parameters**: `tokens` — comma-separated addresses
- **Response**: Array of token objects

### Tokens by Deployer
- **Endpoint**: `GET /tokens/deployer/{deployerAddress}`
- **Response**: All tokens deployed by a specific wallet

---

## Price Endpoints

### Current Price
- **Endpoint**: `GET /price`
- **Parameters**: `token` (required), `priceChanges` (optional, boolean)
- **Response**: `{ price, liquidity, marketCap, priceChange5m, priceChange1h, ... }`

### Historic Prices
- **Endpoint**: `GET /price/history`
- **Parameters**: `token` (required)
- **Response**: Current price + snapshots at 3d, 5d, 7d, 14d, 30d intervals

### Price at Timestamp
- **Endpoint**: `GET /price/history/timestamp`
- **Parameters**: `token`, `timestamp` (unix seconds)

### Price Range
- **Endpoint**: `GET /price/history/range`
- **Parameters**: `token`, `time_from`, `time_to`
- **Response**: Lowest and highest price in the range

### Multi-Token Prices
- **Endpoint**: `GET /price/multi` (GET) or `POST /price/multi` (POST)
- **Parameters**: `tokens` — comma-separated addresses

---

## Chart / OHLCV Endpoints

### OHLCV Candles
- **Endpoint**: `GET /chart/{token}`
- **Parameters**:
  - `type` — Timeframe: `1s`, `5s`, `15s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1mn`
  - `time_from` — Start unix timestamp
  - `time_to` — End unix timestamp
  - `currency` — `usd` (default), `sol`, `eur`
  - `removeOutliers` — Boolean, filter anomalous candles
  - `marketCap` — Boolean, return market cap instead of price
  - `dynamicPools` — Boolean, aggregate across pools
  - `fastCache` — Boolean, use cache for faster response

```bash
curl -H "x-api-key: $KEY" \
  "https://data.solanatracker.io/chart/TOKEN?type=1m&time_from=1700000000&time_to=1700003600"
```

### Specialized Charts
- `GET /chart/{token}/bundlers` — Bundler activity overlay
- `GET /chart/{token}/holders` — Holder count overlay
- `GET /chart/{token}/insiders` — Insider activity overlay
- `GET /chart/{token}/snipers` — Sniper activity overlay

---

## PnL Endpoints

### Wallet PnL
- **Endpoint**: `GET /pnl/{wallet}`
- **Parameters**: `showHistoricPnL` (bool), `holdingCheck` (bool), `hideDetails` (bool)
- **Response**: Summary + per-token breakdown

```json
{
  "summary": {
    "realized": 1234.56,
    "unrealized": 567.89,
    "total": 1802.45,
    "totalInvested": 5000.00,
    "averageBuyAmount": 50.00,
    "totalWins": 42,
    "totalLosses": 18,
    "winPercentage": 70.0,
    "lossPercentage": 30.0
  },
  "tokens": [ /* per-token PnL details */ ]
}
```

### Token-Specific PnL
- **Endpoint**: `GET /pnl/{wallet}/{token}`
- **Response**: PnL for a specific token position

### First Buyers
- **Endpoint**: `GET /first-buyers/{token}`
- **Response**: First buyers of a token with full PnL data
- **Notes**: Useful for identifying early-entry wallets and their current P&L.

---

## Wallet Endpoints

### Wallet Holdings
- **Endpoint**: `GET /wallet/{owner}`
- **Response**: All tokens held with pool, risk, and event data

### Wallet Trades
- **Endpoint**: `GET /wallet/{owner}/trades`
- **Response**: Trade history with buy/sell amounts, prices, timestamps

### Portfolio Chart
- **Endpoint**: `GET /wallet/{owner}/chart`
- **Response**: Portfolio value over time

---

## Top Traders

### Global Top Traders
- **Endpoint**: `GET /top-traders/all` or `GET /top-traders/all/paginated?page=1`
- **Parameters**: `expandPnl` (bool), `sortBy` (`total` or `winPercentage`)

### Token Top Traders
- **Endpoint**: `GET /top-traders/{token}`
- **Parameters**: Same as global

---

## Holder Endpoints

### Paginated Holders
- **Endpoint**: `GET /tokens/{token}/holders?page=1`

### Top Holders
- **Endpoint**: `GET /tokens/{token}/holders/top` — Top 100
- **Endpoint**: `GET /tokens/{token}/holders/top20` — Top 20

### Bundler Detection
- **Endpoint**: `GET /tokens/{token}/bundlers`
- **Response**: Wallets identified as bundlers (batch transaction senders)

---

## Search

- **Endpoint**: `GET /search`
- **Key parameters**: `query`, `symbol`, `minLiquidity`, `maxLiquidity`, `minMarketCap`, `maxMarketCap`, `minVolume`, `maxVolume`, `hasImage`, `hasSocials`, `minHolders`, `maxHolders`, `minRiskScore`, `freezeAuthority`, `mintAuthority`, `deployer`, `market`, `sortBy`, `sortOrder`, `limit` (max 500), `page`, `cursor`

```bash
curl -H "x-api-key: $KEY" \
  "https://data.solanatracker.io/search?minLiquidity=50000&minRiskScore=5&market=raydium&sortBy=volume&limit=20"
```

---

## Trade / Event Endpoints

### Token Trades
- `GET /trades/{token}` — All trades
- `GET /trades/{token}/{wallet}` — Wallet-specific trades
- `GET /trades/pool/{pool}` — Pool-specific trades

### Token Events
- `GET /events/{token}` — Price change events by timeframe
- `GET /events/pool/{pool}` — Pool-specific events

---

## Account Management

- `GET /credits` — Remaining API credits
- `GET /subscription` — Current subscription info
