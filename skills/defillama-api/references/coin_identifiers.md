# DeFiLlama — Coin Identifier Reference

## Format

All coin price endpoints use the format `{chain}:{address}`.

## Supported Chain Prefixes

| Prefix | Chain | Example Address |
|--------|-------|----------------|
| `solana` | Solana | `So11111111111111111111111111111111111111112` |
| `ethereum` | Ethereum | `0xdAC17F958D2ee523a2206206994597C13D831ec7` |
| `bsc` | BNB Smart Chain | `0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c` |
| `polygon` | Polygon | `0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270` |
| `arbitrum` | Arbitrum | `0x912CE59144191C1204E64559FE8253a0e49E6548` |
| `optimism` | Optimism | `0x4200000000000000000000000000000000000042` |
| `avalanche` | Avalanche | `0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7` |
| `base` | Base | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| `fantom` | Fantom | `0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83` |
| `coingecko` | CoinGecko ID | `bitcoin`, `ethereum`, `solana` |

## Common Solana Tokens

```python
SOLANA_COINS = {
    "SOL":  "solana:So11111111111111111111111111111111111111112",
    "USDC": "solana:EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "solana:Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "JUP":  "solana:JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "BONK": "solana:DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF":  "solana:EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "RAY":  "solana:4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "ORCA": "solana:orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
}
```

## Batch Lookup Patterns

### Current Prices (up to 50+ coins)

```python
coins = ",".join(SOLANA_COINS.values())
resp = httpx.get(f"https://coins.llama.fi/prices/current/{coins}")
prices = resp.json()["coins"]
for name, coin_id in SOLANA_COINS.items():
    if coin_id in prices:
        print(f"{name}: ${prices[coin_id]['price']:.4f}")
```

### Historical Comparison

```python
from datetime import datetime, timezone, timedelta

now = int(datetime.now(tz=timezone.utc).timestamp())
week_ago = int((datetime.now(tz=timezone.utc) - timedelta(days=7)).timestamp())

# Current vs 7 days ago
current = httpx.get(f"https://coins.llama.fi/prices/current/{coin}").json()
historical = httpx.get(f"https://coins.llama.fi/prices/historical/{week_ago}/{coin}").json()
```

### Using coingecko: prefix for non-chain lookups

For tokens without a specific chain address (BTC, or when you don't know the address):

```python
# Use CoinGecko IDs
resp = httpx.get("https://coins.llama.fi/prices/current/coingecko:bitcoin,coingecko:ethereum,coingecko:solana")
```

## Confidence Score

Price responses include a `confidence` field (0-1):
- **0.99**: High confidence, multiple sources agree
- **0.90-0.98**: Good confidence
- **< 0.90**: Low confidence, price may be stale or unreliable

Filter out low-confidence prices for reliable data:

```python
def get_reliable_price(coin: str) -> float | None:
    resp = httpx.get(f"https://coins.llama.fi/prices/current/{coin}")
    data = resp.json().get("coins", {}).get(coin, {})
    if data.get("confidence", 0) < 0.9:
        return None
    return data.get("price")
```

## searchWidth Parameter

Controls how far back to look for a valid price (default: `4h`):

```python
# For illiquid tokens, increase searchWidth
resp = httpx.get(f"https://coins.llama.fi/prices/current/{coin}?searchWidth=24h")
```

Values: `4h`, `12h`, `24h`, `48h`, `1w`
