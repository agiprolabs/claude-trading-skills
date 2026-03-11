# CoinGecko API — ID Mapping Guide

CoinGecko uses slug-style string IDs (e.g., `bitcoin`, `solana`, `usd-coin`) rather
than ticker symbols. Since many tokens share the same symbol, you must resolve the
correct CoinGecko ID before making API calls.

## Common Solana Token IDs

| Token | Symbol | CoinGecko ID | Solana Mint Address |
|---|---|---|---|
| Solana | SOL | `solana` | `So11111111111111111111111111111111111111112` |
| Bonk | BONK | `bonk` | `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` |
| Jupiter | JUP | `jupiter-exchange-solana` | `JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN` |
| Raydium | RAY | `raydium` | `4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R` |
| Marinade SOL | mSOL | `msol` | `mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So` |
| Jito SOL | JitoSOL | `jito-staked-sol` | `J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn` |
| Pyth Network | PYTH | `pyth-network` | `HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3` |
| Render | RENDER | `render-token` | `rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof` |
| Helium | HNT | `helium` | `hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux` |
| dogwifhat | WIF | `dogwifcoin` | `EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm` |

## Method 1: Search by Name or Symbol

Use the `/search` endpoint to find a coin's ID:

```python
import httpx

def search_coin(query: str) -> list[dict]:
    """Search CoinGecko for coins matching a query string."""
    resp = httpx.get(
        "https://api.coingecko.com/api/v3/search",
        params={"query": query},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["coins"]

results = search_coin("jupiter")
for coin in results[:5]:
    print(f"  {coin['id']:<35} {coin['symbol']:<8} rank={coin.get('market_cap_rank')}")
```

**Gotcha**: Searching "SOL" returns dozens of results. Filter by `market_cap_rank`
to find the real one — the token with the lowest rank number is almost always correct.

## Method 2: Lookup by Contract Address

Map a Solana mint address directly to a CoinGecko coin:

```python
import httpx

def lookup_by_contract(
    contract: str, platform: str = "solana"
) -> dict | None:
    """Look up a CoinGecko coin by its contract/mint address."""
    url = (
        f"https://api.coingecko.com/api/v3/coins/{platform}"
        f"/contract/{contract}"
    )
    resp = httpx.get(url, timeout=15.0)
    if resp.status_code == 404:
        return None  # Token not listed on CoinGecko
    resp.raise_for_status()
    data = resp.json()
    return {"id": data["id"], "name": data["name"], "symbol": data["symbol"]}

# Example: look up wrapped SOL
result = lookup_by_contract("So11111111111111111111111111111111111111112")
print(result)  # {'id': 'solana', 'name': 'Solana', 'symbol': 'sol'}
```

**Gotcha**: Many newer Solana tokens (especially meme coins launched in the last
few weeks) are not yet listed on CoinGecko. A 404 means the token is unlisted.

## Method 3: Coins List (Full Mapping)

Download the complete list of all CoinGecko IDs (~14,000 entries):

```python
import httpx

def get_all_coins(include_platform: bool = True) -> list[dict]:
    """Fetch the full CoinGecko coins list with platform addresses."""
    resp = httpx.get(
        "https://api.coingecko.com/api/v3/coins/list",
        params={"include_platform": str(include_platform).lower()},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()

coins = get_all_coins()
# Build a lookup from Solana mint to CoinGecko ID
sol_map = {}
for c in coins:
    addr = c.get("platforms", {}).get("solana")
    if addr:
        sol_map[addr] = c["id"]

# Now look up any Solana mint instantly
mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
print(f"BONK CoinGecko ID: {sol_map.get(mint)}")  # "bonk"
```

**Tip**: Cache this list locally — it changes infrequently and costs 1 API call.
Re-fetch at most once per day.

## Common Gotchas

### Symbol Collisions
Many tokens share the same ticker symbol. For example, "SOL" matches both Solana
and several other tokens. Always verify by checking `market_cap_rank` or the
contract address.

### Wrapped vs Native
CoinGecko often maps wrapped tokens to the same ID as the native token. For example,
wrapped SOL (`So11111111111111111111111111111111111111112`) maps to the `solana` ID.

### ID Format
IDs are always lowercase, hyphen-separated slugs. They do not change once assigned.
Examples: `bitcoin`, `usd-coin`, `jupiter-exchange-solana`.

### Unlisted Tokens
CoinGecko requires a listing application and review process. Tokens launched in the
last few days or with very low liquidity may not be listed. For unlisted Solana
tokens, use the Birdeye or DexScreener APIs instead.

### Platform IDs
When using contract lookups, the platform ID for Solana is `solana`, for Ethereum
it is `ethereum`, for BSC it is `binance-smart-chain`. The full list is available
at `GET /asset_platforms`.
