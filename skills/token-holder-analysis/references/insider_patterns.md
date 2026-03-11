# Insider Detection Patterns

## Overview

"Insider" in Solana token trading refers to wallets that have an unfair advantage — they bought before public availability, used transaction bundles for guaranteed early execution, or are connected to the token creator. Detecting these patterns is a critical pre-trade safety check.

## Pattern 1: Bundler Detection

### What is bundling?
Bundlers use Jito or similar services to submit multiple transactions atomically in a single block. This guarantees execution order, allowing coordinated buys at token launch.

### Detection signals
1. **Multiple buys in the same block/slot as token creation**
2. **Multiple wallets buying the exact same amount** in the first slots
3. **Wallets that share funding sources** (funded from the same parent wallet)
4. **High holding percentage from first-block buyers**

### Data sources
- **SolanaTracker** `/tokens/{token}/bundlers` — pre-computed bundler detection
- **SolanaTracker** `/first-buyers/{token}` — first buyers with PnL
- **Helius** Enhanced Transactions — parse early transactions for patterns

### Risk interpretation

| Bundler Holding % | Risk |
|-------------------|------|
| < 5% | Low — bundlers exited or hold small amounts |
| 5-15% | Moderate — some coordinated buying |
| 15-30% | High — significant coordinated control |
| > 30% | Extreme — likely orchestrated launch |

## Pattern 2: Sniper Detection

### What is sniping?
Snipers use automated bots to buy tokens within the first few seconds of liquidity being added. They achieve near-zero entry prices on bonding curves or DEX launches.

### Detection signals
1. **Buy transactions within first 1-10 seconds** of pool creation
2. **Wallet has many "first buy" patterns** across different tokens
3. **Bot-like transaction patterns** (fixed amounts, consistent timing)
4. **Currently holding large % of supply** from initial snipe

### Analysis approach
```python
def is_sniper_wallet(wallet_trades: list[dict], token_created_at: int) -> bool:
    """Check if wallet sniped the token launch."""
    first_buy = next(
        (t for t in wallet_trades if t["type"] == "buy"),
        None
    )
    if first_buy is None:
        return False
    # Bought within 10 seconds of creation
    return first_buy["timestamp"] - token_created_at < 10
```

## Pattern 3: Developer / Creator Analysis

### Risk factors
1. **Creator still holds tokens** — can dump at any time
2. **Mint authority not renounced** — creator can mint more tokens
3. **Freeze authority active** — creator can freeze token accounts
4. **Creator wallet funded by known rug accounts**
5. **Creator deployed multiple tokens** that failed (serial deployer)

### Data sources
- **Birdeye** `/defi/token_security` — mint authority, freeze authority, creator balance
- **SolanaTracker** `/tokens/{token}` — risk score includes these checks
- **SolanaTracker** `/tokens/deployer/{addr}` — all tokens by the same deployer
- **Direct RPC** — check mint account for authority fields

### Serial deployer detection
```python
def check_deployer_history(deployer: str, api_key: str) -> dict:
    """Check deployer's track record."""
    resp = httpx.get(
        f"https://data.solanatracker.io/tokens/deployer/{deployer}",
        headers={"x-api-key": api_key},
    )
    tokens = resp.json()

    rugged = sum(1 for t in tokens if t.get("risk", {}).get("rugged"))
    low_risk = sum(1 for t in tokens if t.get("risk", {}).get("score", 0) >= 7)

    return {
        "total_deployments": len(tokens),
        "rugged_count": rugged,
        "low_risk_count": low_risk,
        "serial_rug": rugged > 3,
    }
```

## Pattern 4: Connected Wallet Clusters

### What to look for
- Wallets funded from the same source around token launch
- Wallets that only ever trade the same tokens
- Wallets that buy and sell in coordinated timing patterns

### Analysis approach
This requires transaction history analysis:
1. For each top holder, trace their funding source (SOL origin)
2. Cluster wallets that share the same funding source
3. Flag clusters that collectively hold >10% of supply

```python
def trace_funding_source(wallet: str, depth: int = 2) -> list[str]:
    """Trace SOL funding sources for a wallet.

    Use Helius Enhanced Transactions to find incoming SOL transfers.
    Returns list of funding source addresses.
    """
    sources = []
    resp = httpx.get(
        f"https://api.helius.xyz/v0/addresses/{wallet}/transactions",
        params={"api-key": HELIUS_KEY, "type": "TRANSFER"},
    )
    for tx in resp.json()[:20]:
        for transfer in tx.get("nativeTransfers", []):
            if transfer.get("toUserAccount") == wallet:
                sources.append(transfer["fromUserAccount"])
    return sources
```

## Pattern 5: Wash Trading Detection

### Signals
- Same wallet appearing as both buyer and seller (self-trades)
- High volume but low unique wallet count
- Volume spikes with no corresponding price movement
- Buy/sell ratio extremely close to 1.0 across many time periods

### Quick check
```python
def wash_trading_check(pair_data: dict) -> dict:
    """Quick wash trading heuristic from DexScreener data."""
    txns = pair_data.get("txns", {}).get("h24", {})
    buys = txns.get("buys", 0)
    sells = txns.get("sells", 0)
    total = buys + sells

    volume = pair_data.get("volume", {}).get("h24", 0)
    liquidity = pair_data.get("liquidity", {}).get("usd", 0)

    flags = []
    if total > 0 and abs(buys - sells) / total < 0.05:
        flags.append("Buy/sell count suspiciously balanced")
    if liquidity > 0 and volume / liquidity > 50:
        flags.append(f"Volume/liquidity ratio extremely high ({volume/liquidity:.0f}x)")

    return {"flags": flags, "suspicious": len(flags) > 0}
```

## Combining Insider Signals

Weight multiple signals for a composite insider risk score:

| Signal | Weight | Max Score |
|--------|--------|-----------|
| Bundler holding > 15% | High | 3 |
| Sniper holding > 10% | High | 3 |
| Creator holds > 10% | Medium | 2 |
| Mint authority active | High | 3 |
| Freeze authority active | Medium | 2 |
| Serial deployer (3+ rugs) | Critical | 4 |
| Connected wallet cluster | Medium | 2 |
| Wash trading signals | Low | 1 |

Score 0-3: Low insider risk
Score 4-7: Moderate — proceed with caution
Score 8-12: High — small positions only
Score 13+: Extreme — avoid
