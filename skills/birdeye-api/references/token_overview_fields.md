# Birdeye Token Overview — Field Reference

Response from `GET /defi/token_overview?address=TOKEN_MINT` (30 CU).

## Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `address` | string | Token mint address |
| `decimals` | int | Token decimals |
| `symbol` | string | Token symbol |
| `name` | string | Token name |
| `logoURI` | string | Token logo URL |
| `liquidity` | float | Total liquidity across all pools (USD) |
| `price` | float | Current price (USD) |
| `supply` | float | Circulating supply |
| `mc` | float | Market cap (USD) |
| `numberMarkets` | int | Number of DEX markets |
| `lastTradeUnixTime` | int | Last trade timestamp |
| `lastTradeHumanTime` | string | Last trade human-readable |

## Social / Extension Fields

| Field | Type | Description |
|-------|------|-------------|
| `coingeckoId` | string | CoinGecko ID |
| `website` | string | Project website |
| `twitter` | string | Twitter/X URL |
| `discord` | string | Discord URL |
| `telegram` | string | Telegram URL |
| `medium` | string | Medium URL |
| `description` | string | Token description |

## Price Change Fields (per interval)

For each interval (30m, 1h, 2h, 4h, 6h, 8h, 12h, 24h):

| Field Pattern | Example (1h) | Description |
|---------------|-------------|-------------|
| `history{X}Price` | `history1hPrice` | Price X ago |
| `priceChange{X}Percent` | `priceChange1hPercent` | % change over X |

## Trading Metrics (per interval)

For each interval (30m, 1h, 2h, 4h, 6h, 8h, 12h, 24h):

| Field Pattern | Example (24h) | Description |
|---------------|--------------|-------------|
| `trade{X}` | `trade24h` | Total trades in period |
| `tradeHistory{X}` | `tradeHistory24h` | Trades in previous period |
| `trade{X}ChangePercent` | `trade24hChangePercent` | Trade count % change |
| `buy{X}` | `buy24h` | Buy trades |
| `sell{X}` | `sell24h` | Sell trades |
| `v{X}` | `v24h` | Volume (native) |
| `v{X}USD` | `v24hUSD` | Volume (USD) |
| `vBuy{X}` | `vBuy24h` | Buy volume (native) |
| `vSell{X}` | `vSell24h` | Sell volume (native) |
| `vBuy{X}USD` | `vBuy24hUSD` | Buy volume (USD) |
| `vSell{X}USD` | `vSell24hUSD` | Sell volume (USD) |

## Unique Wallet Metrics (per interval)

| Field Pattern | Example (24h) | Description |
|---------------|--------------|-------------|
| `uniqueWallet{X}` | `uniqueWallet24h` | Unique wallets in period |
| `uniqueWalletHistory{X}` | `uniqueWalletHistory24h` | Previous period |
| `uniqueWallet{X}ChangePercent` | `uniqueWallet24hChangePercent` | % change |

## Using Token Overview for Analysis

### Quick Health Check

```python
overview = fetch_token_overview(mint)

# Liquidity check
if overview["liquidity"] < 10_000:
    print("LOW LIQUIDITY — dangerous")

# Volume check
buy_sell_ratio = overview.get("vBuy24hUSD", 0) / max(overview.get("vSell24hUSD", 1), 1)

# Wallet diversity
unique_wallets = overview.get("uniqueWallet24h", 0)

# Momentum
price_change_1h = overview.get("priceChange1hPercent", 0)
price_change_24h = overview.get("priceChange24hPercent", 0)

# Trade activity
trades_24h = overview.get("trade24h", 0)
```

### Compare Current vs Historical Activity

```python
# Is activity increasing or decreasing?
trade_change = overview.get("trade24hChangePercent", 0)
wallet_change = overview.get("uniqueWallet24hChangePercent", 0)
volume_change_pct = (
    (overview.get("v24hUSD", 0) - overview.get("vHistory24hUSD", 0))
    / max(overview.get("vHistory24hUSD", 1), 1)
    * 100
)

if trade_change > 50 and wallet_change > 50:
    print("Increasing interest — new wallet inflow")
elif trade_change < -50:
    print("Declining activity — interest fading")
```

### Multi-Timeframe Analysis

```python
# Compare short-term vs long-term price action
pct_30m = overview.get("priceChange30mPercent", 0)
pct_1h = overview.get("priceChange1hPercent", 0)
pct_4h = overview.get("priceChange4hPercent", 0)
pct_24h = overview.get("priceChange24hPercent", 0)

# Accelerating momentum
if pct_30m > pct_1h > 0:
    print("Accelerating upward momentum")

# Reverting from pump
if pct_30m < 0 and pct_4h > 50:
    print("Reverting after pump — caution")
```
