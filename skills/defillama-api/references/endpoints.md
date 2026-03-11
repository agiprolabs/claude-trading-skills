# DeFiLlama API — Endpoints Reference

All free endpoints require no authentication. Pro endpoints use key in URL path.

---

## TVL & Protocols (`https://api.llama.fi`)

### GET /protocols
All protocols with current TVL. Returns array of objects with: `name`, `slug`, `tvl`, `chainTvls`, `change_1h`, `change_1d`, `change_7d`, `category`, `chains`, `symbol`, `twitter`, `url`.

### GET /protocol/{slug}
Detailed protocol data with historical TVL arrays, token breakdowns, chain-specific TVL.

### GET /tvl/{slug}
Simple number — current TVL in USD.

### GET /v2/chains
All chains with TVL. Returns: `[{name, tvl, tokenSymbol, chainId, gecko_id}]`

### GET /v2/historicalChainTvl
Historical TVL summed across all chains. Returns: `[{date, tvl}]`

### GET /v2/historicalChainTvl/{chain}
Historical TVL for specific chain. Chain names: `Ethereum`, `Solana`, `Arbitrum`, etc.

---

## Coin Prices (`https://coins.llama.fi`)

**Coin ID format**: `{chain}:{address}` — e.g., `solana:So11111111111111111111111111111111111111112`

Supported chains: `ethereum`, `solana`, `bsc`, `polygon`, `arbitrum`, `optimism`, `avalanche`, `base`, `fantom`, `coingecko` (for non-chain lookups).

### GET /prices/current/{coins}
Current prices. Comma-separated coin IDs. Optional: `searchWidth` (default `4h`).

```json
{"coins": {"solana:So11...": {"price": 147.23, "decimals": 9, "symbol": "SOL", "timestamp": 1709251200, "confidence": 0.99}}}
```

### GET /prices/historical/{timestamp}/{coins}
Prices at unix timestamp. Same response schema.

### POST /batchHistorical
Batch multiple timestamps: `{"coins": {"solana:So11...": [ts1, ts2]}}`

### GET /chart/{coins}
Price chart. Query params: `period` (1d, 4h, 1h), `span` (number of periods).

### GET /percentage/{coins}
Price change percentage. Optional: `timestamp`, `lookForward`.

### GET /prices/first/{coins}
First recorded price for tokens.

### GET /block/{chain}/{timestamp}
Block number closest to timestamp.

---

## DEX Volumes (`https://api.llama.fi`)

### GET /overview/dexs
Aggregated DEX volumes. Optional: `excludeTotalDataChart=true`, `dataType=dailyVolume`.

### GET /overview/dexs/{chain}
Chain-specific DEX volumes.

### GET /summary/dexs/{protocol}
Specific DEX detail: `total24h`, `total7d`, `total30d`, `totalAllTime`, `totalDataChart[]`.

---

## Fees & Revenue (`https://api.llama.fi`)

### GET /overview/fees
All protocol fees. Optional: `dataType` = `dailyFees`, `dailyRevenue`, `dailyUserFees`.

### GET /overview/fees/{chain}
Chain-specific fees.

### GET /summary/fees/{protocol}
Specific protocol with methodology: `{total24h, methodology{UserFees, Fees, Revenue, ProtocolRevenue}, totalDataChart[]}`.

---

## Stablecoins (`https://stablecoins.llama.fi`)

### GET /stablecoins
All stablecoins: `{name, symbol, pegType, circulating, chainCirculating, price}`.

### GET /stablecoincharts/all
Historical aggregated stablecoin market cap.

### GET /stablecoincharts/{chain}
Chain-specific. Optional: `stablecoin` (filter by stablecoin ID).

### GET /stablecoinprices
Historical stablecoin price deviations.

### GET /stablecoinchains
All chains with stablecoin data.

---

## Bridges (`https://bridges.llama.fi`)

### GET /bridges
List all bridges. Optional: `includeChains=true`.
Returns: `{bridges: [{name, last24hVolume, weeklyVolume, monthlyVolume, chains}]}`

---

## Options (`https://api.llama.fi`)

### GET /overview/options
Options trading volumes. Optional: `excludeTotalDataChart`.

### GET /overview/options/{chain}
Chain-specific options.

### GET /summary/options/{protocol}
Specific protocol detail.

---

## Pro-Only Endpoints

All require API key in URL path: `https://pro-api.llama.fi/{KEY}/api/...`

| Endpoint | Description |
|----------|-------------|
| `/pools` | All yield pools with APY |
| `/chart/{pool}` | Historical APY/TVL for pool |
| `/poolsBorrow` | Borrowing rates |
| `/perps` | Perpetual funding rates |
| `/lsdRates` | Liquid staking rates |
| `/bridge/{id}` | Bridge detail |
| `/bridgevolume/{chain}` | Bridge volume by chain |
| `/api/categories` | TVL by category |
| `/api/treasuries` | Protocol treasuries |
| `/api/hacks` | Exploit database |
| `/api/raises` | Funding rounds |
| `/api/emissions` | Token unlock schedules |
| `/api/emission/{protocol}` | Specific vesting |
| `/etfs/overview` | Crypto ETF data |
| `/usage/APIKEY` | API usage stats |

---

## Response Size Warning

`/protocols`, `/overview/dexs`, and `/overview/fees` return very large payloads (10MB+). Always use `excludeTotalDataChart=true` and `excludeTotalDataChartBreakdown=true` to reduce response size.
