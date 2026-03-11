# Holder Analysis — Data Sources

## Source Comparison

| Data Point | Solana RPC | Helius DAS | SolanaTracker | Birdeye |
|-----------|-----------|------------|---------------|---------|
| Top holders | Top 20 | Via token accts | Top 100 | Top 10 % |
| Total supply | Yes | Yes | Yes | Partial |
| Holder count | No | No | Yes | No |
| Mint authority | Via getAccountInfo | Via getAsset | In risk score | Yes |
| Freeze authority | Via getAccountInfo | Via getAsset | In risk score | Yes |
| Creator balance | No | No | Yes | Yes |
| Bundler detection | No | No | Yes | No |
| Sniper detection | No | No | Yes | No |
| Risk score | No | No | Yes (1-10) | Partial |
| Auth required | RPC key | API key | API key | API key |
| Cost | Free (public) | 50K/day free | €50/mo | Free tier |

## Method 1: Solana RPC (Free, Basic)

Best for: Quick top-20 check, total supply, mint/freeze authority status.

```python
# Top 20 holders
result = rpc_call("getTokenLargestAccounts", [mint])
holders = result["value"]  # [{address, amount, decimals, uiAmount}]

# Total supply
result = rpc_call("getTokenSupply", [mint])
supply = result["value"]  # {amount, decimals, uiAmount}

# Mint/freeze authority (from mint account data)
result = rpc_call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
mint_info = result["value"]["data"]["parsed"]["info"]
# mint_info["mintAuthority"] — None if renounced
# mint_info["freezeAuthority"] — None if disabled
```

**Limitations**: Only top 20 holders. No holder count. No insider detection.

## Method 2: Helius DAS API

Best for: Token metadata, parsed account data, fungible token details.

```python
# Token metadata via DAS
resp = httpx.post(f"https://mainnet.helius-rpc.com/?api-key={KEY}", json={
    "jsonrpc": "2.0", "id": 1,
    "method": "getAsset",
    "params": {"id": mint},
})
asset = resp.json()["result"]
# asset["authorities"] — mint/freeze authority info
# asset["token_info"]["supply"] — total supply
# asset["content"]["metadata"] — name, symbol, image
```

**Limitations**: Doesn't directly provide holder lists. Use with RPC for complete picture.

## Method 3: SolanaTracker API (Most Complete)

Best for: Full holder analysis including bundlers, snipers, risk scoring.

```python
HEADERS = {"x-api-key": ST_KEY}

# Top 100 holders
resp = httpx.get(f"https://data.solanatracker.io/tokens/{mint}/holders/top", headers=HEADERS)
holders = resp.json()

# Top 20 (lighter call)
resp = httpx.get(f"https://data.solanatracker.io/tokens/{mint}/holders/top20", headers=HEADERS)

# Bundler detection
resp = httpx.get(f"https://data.solanatracker.io/tokens/{mint}/bundlers", headers=HEADERS)
bundlers = resp.json()

# First buyers with PnL
resp = httpx.get(f"https://data.solanatracker.io/first-buyers/{mint}", headers=HEADERS)
first_buyers = resp.json()

# Full token info with risk score
resp = httpx.get(f"https://data.solanatracker.io/tokens/{mint}", headers=HEADERS)
token = resp.json()
risk_score = token["risk"]["score"]  # 1-10
```

## Method 4: Birdeye API

Best for: Quick security check (mint/freeze authority, top 10 concentration).

```python
# Token security info
resp = httpx.get("https://public-api.birdeye.so/defi/token_security",
    headers={"X-API-KEY": BE_KEY, "x-chain": "solana"},
    params={"address": mint})
security = resp.json()["data"]
# security["top10HolderPercent"]
# security["ownerAddress"] — mint authority (None if renounced)
# security["freezeable"]
# security["mutableMetadata"]
# security["creatorBalance"]
```

## Recommended Pipeline

For a thorough pre-trade holder analysis:

```python
def full_holder_check(mint: str) -> dict:
    """Complete holder analysis using best available data sources."""

    # 1. Quick check via RPC (free, always available)
    supply = get_token_supply(mint)
    top_20 = get_largest_accounts(mint)

    # 2. Risk score from SolanaTracker (if key available)
    if ST_KEY:
        token_data = st_get(f"/tokens/{mint}")
        risk_score = token_data.get("risk", {}).get("score", 0)
        bundlers = st_get(f"/tokens/{mint}/bundlers")

    # 3. Security check from Birdeye (if key available)
    if BE_KEY:
        security = birdeye_get("/defi/token_security", {"address": mint})

    # 4. Compute concentration metrics from RPC data
    amounts = [int(h["amount"]) for h in top_20]
    metrics = compute_concentration(amounts, int(supply["amount"]))

    return {
        "supply": supply,
        "top_holders": top_20,
        "concentration": metrics,
        "risk_score": risk_score,
        "bundlers": bundlers,
        "security": security,
    }
```

## Caching Considerations

Holder data changes slowly compared to price data. Reasonable cache TTLs:

| Data | Cache TTL | Reason |
|------|-----------|--------|
| Top holders | 5-15 minutes | Positions change via trades |
| Total supply | 1 hour | Rarely changes (unless mintable) |
| Mint/freeze authority | 1 hour | Almost never changes |
| Risk score | 15-30 minutes | Recalculated periodically |
| Bundler data | 1 hour | Historical, doesn't change |
