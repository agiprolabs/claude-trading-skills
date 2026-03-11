---
name: token-holder-analysis
description: Token holder distribution, concentration metrics, insider detection, and supply analysis for Solana tokens
---

# Token Holder Analysis — Concentration, Distribution & Risk

Analyze who holds a token, how concentrated ownership is, and whether insider patterns suggest risk. This is a critical pre-trade safety check — high concentration means a few wallets can crash the price.

## Quick Start

```python
import httpx
import math

# Using Helius DAS API for holder data
HELIUS_KEY = os.getenv("HELIUS_API_KEY", "")
HELIUS = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

# Or using SolanaTracker for holder + risk data
ST_KEY = os.getenv("SOLANATRACKER_API_KEY", "")
ST = "https://data.solanatracker.io"

# Get top holders via RPC
def get_top_holders(mint: str) -> list[dict]:
    resp = httpx.post(HELIUS, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenLargestAccounts",
        "params": [mint],
    })
    return resp.json()["result"]["value"]

holders = get_top_holders("TOKEN_MINT")
```

## Data Sources

| Source | What It Provides | Auth |
|--------|-----------------|------|
| **Solana RPC** (`getTokenLargestAccounts`) | Top 20 holders, supply | RPC key |
| **Helius DAS** (`getAsset`, token accounts) | Parsed holder data, metadata | API key |
| **SolanaTracker** (`/tokens/{t}/holders/top`) | Top 100 holders, bundler detection | API key |
| **Birdeye** (`/defi/token_security`) | Top 10 %, creator balance, freeze/mint auth | API key |

## Concentration Metrics

### Top-N Holder Percentage

The simplest measure — what % of supply do the top N holders control?

```python
def top_n_percentage(holders: list[dict], supply: int, n: int = 10) -> float:
    """Calculate percentage held by top N holders.

    Args:
        holders: Sorted list of holders (largest first).
        supply: Total token supply.
        n: Number of top holders.

    Returns:
        Percentage (0-100) held by top N.
    """
    top_n_amount = sum(int(h.get("amount", 0)) for h in holders[:n])
    return top_n_amount / supply * 100 if supply > 0 else 0
```

**Risk thresholds**:
- Top 10 < 30%: Well distributed
- Top 10 30-50%: Moderate concentration
- Top 10 50-80%: High concentration — significant dump risk
- Top 10 > 80%: Extreme — likely controlled by a few wallets

### Gini Coefficient

Measures inequality of token distribution (0 = perfectly equal, 1 = one holder owns everything).

```python
def gini_coefficient(amounts: list[float]) -> float:
    """Calculate Gini coefficient for holder distribution.

    Args:
        amounts: List of holder amounts (any order).

    Returns:
        Gini coefficient between 0 and 1.
    """
    if not amounts or all(a == 0 for a in amounts):
        return 0.0
    sorted_amounts = sorted(amounts)
    n = len(sorted_amounts)
    cumsum = sum((i + 1) * a for i, a in enumerate(sorted_amounts))
    total = sum(sorted_amounts)
    return (2 * cumsum) / (n * total) - (n + 1) / n
```

**Interpretation for crypto tokens**:
- Gini < 0.6: Unusual, very well distributed
- Gini 0.6-0.8: Typical for established tokens
- Gini 0.8-0.95: Common for newer tokens
- Gini > 0.95: Extreme concentration, high risk

### Herfindahl-Hirschman Index (HHI)

Measures market concentration — sum of squared market shares.

```python
def hhi(amounts: list[float]) -> float:
    """Calculate HHI for holder concentration.

    Args:
        amounts: List of holder amounts.

    Returns:
        HHI value (0-10000). Higher = more concentrated.
    """
    total = sum(amounts)
    if total == 0:
        return 0.0
    shares = [a / total * 100 for a in amounts]
    return sum(s ** 2 for s in shares)
```

**Interpretation**:
- HHI < 1500: Competitive (unconcentrated)
- HHI 1500-2500: Moderately concentrated
- HHI > 2500: Highly concentrated

### Nakamoto Coefficient

Minimum number of holders needed to control >50% of supply.

```python
def nakamoto_coefficient(amounts: list[float]) -> int:
    """Calculate Nakamoto coefficient (holders needed for 51%).

    Args:
        amounts: Sorted list of holder amounts (largest first).

    Returns:
        Number of holders needed for majority control.
    """
    total = sum(amounts)
    if total == 0:
        return 0
    threshold = total * 0.51
    cumulative = 0
    for i, amount in enumerate(sorted(amounts, reverse=True)):
        cumulative += amount
        if cumulative >= threshold:
            return i + 1
    return len(amounts)
```

## Insider Detection Patterns

### Bundler Detection

Bundlers use atomic transaction bundles (via Jito) to execute coordinated buys at token launch. Detection signals:

```python
def detect_bundler_patterns(holders: list[dict], first_buyers: list[dict]) -> dict:
    """Identify potential bundler activity.

    Args:
        holders: Current top holders.
        first_buyers: Early buyers from SolanaTracker /first-buyers endpoint.

    Returns:
        Bundler risk analysis.
    """
    early_still_holding = [
        b for b in first_buyers
        if b.get("holdingAmount", 0) > 0
    ]
    early_holder_pct = sum(
        b.get("holdingPercentage", 0) for b in early_still_holding
    )

    return {
        "early_buyers_count": len(first_buyers),
        "still_holding_count": len(early_still_holding),
        "early_holder_pct": round(early_holder_pct, 2),
        "risk": "HIGH" if early_holder_pct > 20 else
                "MODERATE" if early_holder_pct > 10 else "LOW",
    }
```

### Developer Holdings

Creator wallet retention is a risk signal:

```python
def check_developer_risk(token_data: dict) -> dict:
    """Check developer wallet holdings and authority.

    Args:
        token_data: Token info from SolanaTracker or Birdeye.

    Returns:
        Developer risk assessment.
    """
    risk = token_data.get("risk", {})
    flags = []

    # Check creator balance (from Birdeye security endpoint)
    creator_balance = token_data.get("creatorBalance", 0)
    if creator_balance > 10:
        flags.append(f"Creator holds {creator_balance:.1f}% of supply")

    # Check mint authority
    if token_data.get("mintAuthority") or token_data.get("ownerAddress"):
        flags.append("Mint authority NOT renounced — supply can increase")

    # Check freeze authority
    if token_data.get("freezeAuthority") or token_data.get("freezeable"):
        flags.append("Freeze authority enabled — tokens can be frozen")

    return {
        "flags": flags,
        "risk_level": "HIGH" if len(flags) >= 2 else
                      "MODERATE" if len(flags) == 1 else "LOW",
    }
```

### Sniper Detection

Snipers buy in the first few seconds/blocks after token creation:

```python
def analyze_sniper_concentration(first_buyers: list[dict], total_supply: float) -> dict:
    """Analyze sniper impact on holder distribution.

    Args:
        first_buyers: First buyers data from SolanaTracker.
        total_supply: Total token supply.

    Returns:
        Sniper concentration analysis.
    """
    # Snipers typically buy in first 10 seconds
    snipers = first_buyers[:10]  # first N buyers are potential snipers
    sniper_holding = sum(b.get("holdingAmount", 0) for b in snipers)
    sniper_pct = sniper_holding / total_supply * 100 if total_supply > 0 else 0

    return {
        "sniper_count": len(snipers),
        "sniper_holding_pct": round(sniper_pct, 2),
        "sniper_still_holding": sum(1 for s in snipers if s.get("holdingAmount", 0) > 0),
        "risk": "HIGH" if sniper_pct > 15 else
                "MODERATE" if sniper_pct > 5 else "LOW",
    }
```

## Complete Analysis Pipeline

```python
def full_holder_analysis(mint: str) -> dict:
    """Run complete holder analysis for a token.

    Combines RPC, SolanaTracker, and computed metrics.
    """
    # 1. Get supply and top holders via RPC
    supply_result = rpc_call("getTokenSupply", [mint])
    total_supply = int(supply_result["result"]["value"]["amount"])

    holders = get_top_holders(mint)
    amounts = [int(h["amount"]) for h in holders]

    # 2. Compute concentration metrics
    metrics = {
        "total_supply": total_supply,
        "holder_count": len(holders),
        "top_1_pct": top_n_percentage(holders, total_supply, 1),
        "top_5_pct": top_n_percentage(holders, total_supply, 5),
        "top_10_pct": top_n_percentage(holders, total_supply, 10),
        "top_20_pct": top_n_percentage(holders, total_supply, 20),
        "gini": round(gini_coefficient(amounts), 4),
        "hhi": round(hhi(amounts), 1),
        "nakamoto": nakamoto_coefficient(amounts),
    }

    # 3. Risk classification
    t10 = metrics["top_10_pct"]
    if t10 > 80:
        metrics["risk"] = "EXTREME"
    elif t10 > 50:
        metrics["risk"] = "HIGH"
    elif t10 > 30:
        metrics["risk"] = "MODERATE"
    else:
        metrics["risk"] = "LOW"

    return metrics
```

## Risk Classification Summary

| Metric | Low Risk | Moderate | High | Extreme |
|--------|----------|----------|------|---------|
| Top 10 % | <30% | 30-50% | 50-80% | >80% |
| Gini | <0.7 | 0.7-0.85 | 0.85-0.95 | >0.95 |
| HHI | <1500 | 1500-2500 | 2500-5000 | >5000 |
| Nakamoto | >10 | 5-10 | 2-4 | 1 |
| Mint Auth | Renounced | — | Active | Active + high dev % |
| Freeze Auth | Disabled | — | Enabled | Enabled + low liq |

## Known Exclusions

When computing holder concentration, exclude these addresses which are programs/pools, not individual holders:

- DEX pool addresses (Raydium, Orca, Meteora pools)
- Token program vaults
- Bridge escrow accounts
- Known burn addresses

```python
KNOWN_PROGRAMS = {
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  # Raydium authority
    "GThUX1Atko4tqhN2NaiTazWSeFWMuiUvfFnyJyUghFMJ",  # Orca authority
    # Add more as needed
}

def filter_real_holders(holders: list[dict]) -> list[dict]:
    """Remove known program/pool accounts from holder list."""
    return [h for h in holders if h.get("address") not in KNOWN_PROGRAMS]
```

## Files

### References
- `references/concentration_metrics.md` — Mathematical formulas and derivations for Gini, HHI, Nakamoto
- `references/insider_patterns.md` — Bundler, sniper, and developer detection methodology
- `references/data_sources.md` — How to fetch holder data from each API source

### Scripts
- `scripts/analyze_holders.py` — Full holder analysis: fetch holders, compute metrics, generate risk report
- `scripts/concentration_scanner.py` — Scan multiple tokens for concentration risk
