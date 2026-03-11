# Birdeye API — Endpoint Reference

Base URL: `https://public-api.birdeye.so`

Headers required on every request:
- `X-API-KEY: your-key`
- `x-chain: solana` (or ethereum, base, arbitrum, etc.)
- `accept: application/json`

## Price Endpoints

### GET `/defi/price` — Single Token Price
- **Params**: `address` (required)
- **CU**: 10
- **Response**: `{ data: { value: 23.44, updateUnixTime: 1692175119, updateHumanTime: "..." }, success: true }`

### POST `/defi/multi_price` — Batch Token Prices
- **Body**: `{ "addresses": ["MINT1", "MINT2"] }`
- **CU**: Variable
- More efficient than calling `/defi/price` in a loop

### GET `/defi/historical_price_unix` — Price at Timestamp
- **Params**: `address`, `unixtime`
- **CU**: 10

### GET `/defi/history_price` — Historical Price Series
- **Params**: `address`, `address_type` (token), `type` (timeframe), `time_from`, `time_to`
- **CU**: 60

### GET `/defi/v3/price/stats/single` — Price Statistics
- **CU**: 20

## OHLCV Endpoints

### GET `/defi/ohlcv` — Token OHLCV
- **Params**: `address`, `type` (1m-1M), `time_from`, `time_to`
- **CU**: 40
- **Max**: 1000 candles per request
- **Timeframes**: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 8H, 12H, 1D, 3D, 1W, 1M
- **Response item**: `{ o, h, l, c, v, unixTime, type, address }`

### GET `/defi/ohlcv/pair` — Pair OHLCV
- **Params**: `address` (pair address), `type`, `time_from`, `time_to`
- **CU**: 40

### GET `/defi/ohlcv/base_quote` — Base/Quote OHLCV
- **CU**: 40

## Token Data Endpoints

### GET `/defi/token_overview` — Token Overview
- **Params**: `address`
- **CU**: 30
- **Key fields**: See `token_overview_fields.md` for complete list

### GET `/defi/token_security` — Security Info
- **Params**: `address`
- **CU**: 50
- **Key fields**: `creatorAddress`, `ownerAddress`, `top10HolderPercent`, `mutableMetadata`, `freezeable`, `freezeAuthority`, `transferFeeEnable`, `isToken2022`, `lockInfo`, `totalSupply`, `creationTx`, `creationTime`

### GET `/defi/token_creation_info` — Creation Details
- **Params**: `address`
- **CU**: 80

### GET `/defi/token_trending` — Trending Tokens
- **Params**: `sort_by` (rank/liquidity/volume24hUSD), `sort_type` (asc/desc), `offset`, `limit`
- **CU**: 50
- **Response item**: `{ address, decimals, liquidity, logoURI, name, symbol, volume24hUSD, rank }`

### GET `/defi/v2/tokens/new_listing` — New Listings
- **Params**: `time_to` (required), `limit` (1-10), `meme_platform_enabled` (boolean, Solana only)
- **CU**: 80
- **Response item**: `{ address, symbol, name, decimals, liquidityAddedAt, liquidity }`

### GET `/defi/v3/token/holder` — Token Holders
- **Params**: `address`
- **CU**: 50

### GET `/defi/v3/token/exit-liquidity` — Exit Liquidity
- **Params**: `address`
- **CU**: 30

### GET `/defi/v3/token/meta-data/single` — Token Metadata
- **CU**: 5

### GET `/defi/v3/token/market-data` — Market Data
- **CU**: 15

### GET `/defi/v3/search` — Search
- **Params**: `keyword`, `chain`
- **CU**: 50

## Trade Endpoints

### GET `/defi/txs/token` — Recent Token Trades
- **Params**: `address`, `offset` (0-1000), `limit` (1-50), `tx_type` (swap/add/remove/all)
- **CU**: 10
- **Response item**: `{ txHash, source, blockUnixTime, address, owner, from: {symbol, decimals, amount, uiAmount, price, nearestPrice}, to: {...} }`

### GET `/defi/txs/token/seek_by_time` — Token Trades by Time
- **Params**: `address`, `before_time` OR `after_time` (NOT both), `offset`, `limit`, `tx_type`
- **CU**: 15
- **Pagination**: Use `data.hasNext` boolean

### GET `/defi/txs/pair` — Pair Trades
- **Params**: Same as token trades but with pair address
- **CU**: 10

### GET `/defi/txs/pair/seek_by_time` — Pair Trades by Time
- **CU**: 15

### GET `/defi/v3/token/txs` — Token Trades (v3)
- **CU**: 20

## Trader Endpoints

### GET `/defi/v2/tokens/top_traders` — Top Traders
- **Params**: `address`, `sort_by` (volume/trade), `sort_type`, `time_frame` (30m-24h), `offset`, `limit` (1-10)
- **CU**: 30
- **Response item**: `{ owner, volume, volumeBuy, volumeSell, trade, tradeBuy, tradeSell, tags }`
- **Tags**: `"arbitrage-bot"`, `"sniper-bot"`, etc.

### GET `/trader/gainers-losers` — Top Gainers/Losers
- **CU**: 30

### GET `/trader/txs/seek_by_time` — Trader Trades by Time
- **CU**: 15

## Wallet Endpoints (30 rpm limit)

### GET `/v1/wallet/token_list` — Portfolio
- **Params**: `wallet`
- **CU**: 100
- **Response**: `{ wallet, totalUsd, items: [{ address, symbol, name, balance, uiAmount, priceUsd, valueUsd }] }`

### GET `/v1/wallet/token_balance` — Token Balance
- **Params**: `wallet`, `token_address`
- **CU**: 5

### GET `/v1/wallet/tx_list` — Transaction History
- **Params**: `wallet`
- **CU**: 150

### GET `/wallet/v2/current-net-worth` — Net Worth
- **CU**: 100

### GET `/wallet/v2/pnl` — PnL
- **CU**: Variable

## Pair Endpoints

### GET `/defi/v3/pair/overview/single` — Pair Overview
- **CU**: 20

### GET `/defi/v2/markets` — All Markets for Token
- **CU**: 50
