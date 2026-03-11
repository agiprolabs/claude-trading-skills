# CoinGecko API — Endpoints Reference

Base URL (free): `https://api.coingecko.com/api/v3`
Base URL (pro): `https://pro-api.coingecko.com/api/v3`

Free tier: 30 calls/min, no key required.
Pro tier: add header `x-cg-pro-api-key: YOUR_KEY`.

---

## Simple Price

- **Endpoint**: `GET /simple/price`
- **Description**: Current price for one or more coins in one or more currencies.
- **Parameters**:
  | Param | Required | Description |
  |---|---|---|
  | `ids` | Yes | Comma-separated CoinGecko IDs (e.g., `bitcoin,solana`) |
  | `vs_currencies` | Yes | Comma-separated fiat/crypto (e.g., `usd,btc`) |
  | `include_market_cap` | No | `true` to include market cap |
  | `include_24hr_vol` | No | `true` to include 24h volume |
  | `include_24hr_change` | No | `true` to include 24h % change |
  | `include_last_updated_at` | No | `true` to include Unix timestamp |
- **Response**:
  ```json
  {
    "solana": {
      "usd": 125.43,
      "usd_market_cap": 58000000000,
      "usd_24h_vol": 2100000000,
      "usd_24h_change": 3.456,
      "last_updated_at": 1709856000
    }
  }
  ```
- **Example**: `curl "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd&include_24hr_change=true"`

---

## Coins Markets

- **Endpoint**: `GET /coins/markets`
- **Description**: Top coins with market data (price, volume, market cap, changes).
- **Parameters**:
  | Param | Required | Default | Description |
  |---|---|---|---|
  | `vs_currency` | Yes | — | Target currency (e.g., `usd`) |
  | `ids` | No | — | Filter to specific coin IDs |
  | `category` | No | — | Filter by category slug |
  | `order` | No | `market_cap_desc` | Sort: `market_cap_desc`, `volume_desc`, `id_asc` |
  | `per_page` | No | 100 | Results per page (1-250) |
  | `page` | No | 1 | Page number |
  | `sparkline` | No | `false` | Include 7-day sparkline array |
  | `price_change_percentage` | No | — | Comma-separated: `1h,24h,7d,14d,30d,200d,1y` |
- **Response** (array):
  ```json
  [{
    "id": "solana",
    "symbol": "sol",
    "name": "Solana",
    "current_price": 125.43,
    "market_cap": 58000000000,
    "market_cap_rank": 5,
    "total_volume": 2100000000,
    "high_24h": 128.50,
    "low_24h": 120.10,
    "price_change_percentage_24h": 3.456,
    "circulating_supply": 440000000,
    "total_supply": 580000000,
    "ath": 260.06,
    "ath_date": "2021-11-06T21:54:35.825Z",
    "atl": 0.500801,
    "atl_date": "2020-05-11T19:35:23.449Z"
  }]
  ```
- **Example**: `curl "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=10&page=1"`

---

## Coin Detail

- **Endpoint**: `GET /coins/{id}`
- **Description**: Full coin data — description, links, community stats, market data.
- **Parameters**:
  | Param | Required | Default | Description |
  |---|---|---|---|
  | `id` | Yes (path) | — | CoinGecko coin ID |
  | `localization` | No | `true` | Include localized descriptions |
  | `tickers` | No | `true` | Include exchange tickers |
  | `market_data` | No | `true` | Include market data |
  | `community_data` | No | `true` | Include community stats |
  | `developer_data` | No | `true` | Include GitHub stats |
  | `sparkline` | No | `false` | Include 7-day sparkline |
- **Notes**: Large response (~50KB). Set unneeded sections to `false` to reduce size.
- **Example**: `curl "https://api.coingecko.com/api/v3/coins/solana?tickers=false&community_data=false"`

---

## Market Chart (Historical)

- **Endpoint**: `GET /coins/{id}/market_chart`
- **Description**: Historical price, market cap, and volume over time.
- **Parameters**:
  | Param | Required | Description |
  |---|---|---|
  | `id` | Yes (path) | CoinGecko coin ID |
  | `vs_currency` | Yes | Target currency |
  | `days` | Yes | Data range: `1`, `7`, `14`, `30`, `90`, `180`, `365`, `max` |
  | `interval` | No | `daily` for daily points (auto-selected otherwise) |
- **Granularity rules** (free tier):
  - 1 day: ~5-minute intervals
  - 2-90 days: hourly
  - 90+ days: daily
  - Setting `interval=daily` forces daily regardless
- **Response**:
  ```json
  {
    "prices": [[1709856000000, 125.43], [1709942400000, 128.10]],
    "market_caps": [[1709856000000, 58000000000], ...],
    "total_volumes": [[1709856000000, 2100000000], ...]
  }
  ```
- **Example**: `curl "https://api.coingecko.com/api/v3/coins/solana/market_chart?vs_currency=usd&days=90&interval=daily"`

---

## OHLC

- **Endpoint**: `GET /coins/{id}/ohlc`
- **Description**: OHLC candle data.
- **Parameters**:
  | Param | Required | Description |
  |---|---|---|
  | `id` | Yes (path) | CoinGecko coin ID |
  | `vs_currency` | Yes | Target currency |
  | `days` | Yes | `1`, `7`, `14`, `30`, `90`, `180`, `365` |
- **Candle granularity**:
  - 1-2 days: 30-minute candles
  - 3-30 days: 4-hour candles
  - 31-365 days: 4-day candles
- **Response**: `[[timestamp, open, high, low, close], ...]`
- **Example**: `curl "https://api.coingecko.com/api/v3/coins/solana/ohlc?vs_currency=usd&days=30"`

---

## Trending

- **Endpoint**: `GET /search/trending`
- **Description**: Top-7 trending coins on CoinGecko in the last 24 hours.
- **Parameters**: None.
- **Response**:
  ```json
  {
    "coins": [{
      "item": {
        "id": "pepe",
        "coin_id": 31642,
        "name": "Pepe",
        "symbol": "PEPE",
        "market_cap_rank": 30,
        "thumb": "https://...",
        "score": 0
      }
    }]
  }
  ```
- **Example**: `curl "https://api.coingecko.com/api/v3/search/trending"`

---

## Global

- **Endpoint**: `GET /global`
- **Description**: Global crypto market statistics.
- **Response**:
  ```json
  {
    "data": {
      "active_cryptocurrencies": 13000,
      "markets": 900,
      "total_market_cap": {"usd": 2500000000000},
      "total_volume": {"usd": 85000000000},
      "market_cap_percentage": {"btc": 52.1, "eth": 16.3},
      "market_cap_change_percentage_24h_usd": 1.5,
      "updated_at": 1709856000
    }
  }
  ```
- **Example**: `curl "https://api.coingecko.com/api/v3/global"`

---

## Categories

- **Endpoint**: `GET /coins/categories`
- **Description**: Token categories with aggregate market data.
- **Parameters**: `order` — `market_cap_desc` (default), `market_cap_asc`, `name_asc`, etc.
- **Response** (array):
  ```json
  [{
    "id": "decentralized-finance-defi",
    "name": "Decentralized Finance (DeFi)",
    "market_cap": 95000000000,
    "market_cap_change_24h": 2.1,
    "volume_24h": 5000000000,
    "top_3_coins": ["https://...", "https://...", "https://..."],
    "updated_at": "2025-03-10T00:00:00Z"
  }]
  ```
- **Example**: `curl "https://api.coingecko.com/api/v3/coins/categories"`

---

## Exchanges

- **Endpoint**: `GET /exchanges`
- **Description**: Exchange rankings by volume with trust scores.
- **Parameters**: `per_page` (1-250, default 100), `page`.
- **Response** (array):
  ```json
  [{
    "id": "binance",
    "name": "Binance",
    "year_established": 2017,
    "country": "Cayman Islands",
    "trust_score": 10,
    "trust_score_rank": 1,
    "trade_volume_24h_btc": 450000
  }]
  ```
- **Example**: `curl "https://api.coingecko.com/api/v3/exchanges?per_page=10"`

---

## Search

- **Endpoint**: `GET /search`
- **Description**: Search for coins, exchanges, and categories by keyword.
- **Parameters**: `query` (required) — search string.
- **Response**:
  ```json
  {
    "coins": [{"id": "solana", "name": "Solana", "symbol": "SOL", "market_cap_rank": 5}],
    "exchanges": [...],
    "categories": [...]
  }
  ```
- **Example**: `curl "https://api.coingecko.com/api/v3/search?query=solana"`

---

## Contract Lookup

- **Endpoint**: `GET /coins/{platform_id}/contract/{contract_address}`
- **Description**: Look up a coin by its contract address on a specific platform.
- **Path params**: `platform_id` (e.g., `solana`, `ethereum`), `contract_address`.
- **Notes**: Returns the same structure as `/coins/{id}`. Use this to map Solana mint addresses to CoinGecko IDs.
- **Example**: `curl "https://api.coingecko.com/api/v3/coins/solana/contract/So11111111111111111111111111111111111111112"`
