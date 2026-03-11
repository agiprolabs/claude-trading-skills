# Sybil Detection — Bundler Detection

How to detect bundled transactions on Solana, with focus on PumpFun token launches and Jito bundle mechanics.

## What Are Bundled Transactions?

On Solana, bundled transactions take two forms:

### 1. Single-Transaction Bundles

Multiple swap instructions packed into one Solana transaction. One signer executes buys for multiple destination wallets in a single atomic operation.

**Detection signals:**
- Transaction has multiple token transfer instructions to different wallets
- Single fee payer for all instructions
- All transfers are for the same token mint

### 2. Jito Bundles

Multiple separate transactions submitted together to a Jito validator. They execute sequentially in the same slot with guaranteed ordering.

**Detection signals:**
- Multiple transactions in the same slot buying the same token
- Transactions appear sequential (consecutive within the slot)
- Often include a Jito tip transaction to the tip program

## Detecting Bundled Buys from Transaction Data

### Via Helius Parsed Transactions

```python
import httpx

def detect_single_tx_bundles(
    token_mint: str, helius_key: str, limit: int = 100
) -> list[dict]:
    """Find transactions that contain multiple buys of the same token.

    These are single transactions where one signer buys tokens
    and distributes to multiple wallets.
    """
    url = f"https://api.helius.xyz/v0/addresses/{token_mint}/transactions"
    resp = httpx.get(url, params={"api-key": helius_key, "limit": limit}, timeout=15)
    if resp.status_code != 200:
        return []

    bundled_txs = []
    for tx in resp.json():
        token_transfers = [
            t for t in tx.get("tokenTransfers", [])
            if t.get("mint") == token_mint
        ]
        unique_recipients = set(t["toUserAccount"] for t in token_transfers)

        if len(unique_recipients) >= 2:
            bundled_txs.append({
                "signature": tx.get("signature", ""),
                "slot": tx.get("slot", 0),
                "recipient_count": len(unique_recipients),
                "recipients": list(unique_recipients),
                "total_amount": sum(t.get("tokenAmount", 0) for t in token_transfers),
                "fee_payer": tx.get("feePayer", ""),
            })

    return bundled_txs
```

### Via Slot-Based Jito Bundle Detection

```python
from collections import defaultdict

def detect_jito_bundles(
    buy_events: list[dict], max_slot_gap: int = 0
) -> list[dict]:
    """Detect likely Jito bundles by grouping buys in the same slot.

    Jito bundles execute multiple transactions in the same slot with
    guaranteed sequential ordering.

    Args:
        buy_events: List of {"wallet": str, "slot": int, "tx_sig": str, "amount": float}.
        max_slot_gap: Maximum slot gap to consider as same bundle (0 = same slot only).

    Returns:
        List of detected bundle groups.
    """
    slot_groups: dict[int, list[dict]] = defaultdict(list)
    for event in buy_events:
        slot_groups[event["slot"]].append(event)

    bundles = []
    for slot, events in sorted(slot_groups.items()):
        if len(events) >= 2:
            unique_wallets = set(e["wallet"] for e in events)
            unique_sigs = set(e["tx_sig"] for e in events)
            bundles.append({
                "slot": slot,
                "tx_count": len(unique_sigs),
                "wallet_count": len(unique_wallets),
                "wallets": list(unique_wallets),
                "total_amount": sum(e["amount"] for e in events),
                "is_single_tx": len(unique_sigs) == 1,
                "is_jito_bundle": len(unique_sigs) > 1,
            })

    return bundles
```

### Via SolanaTracker Bundler API

SolanaTracker provides a dedicated bundler detection endpoint:

```python
def check_bundler_solanatracker(
    token_mint: str, api_key: str
) -> dict:
    """Check for bundled transactions via SolanaTracker API."""
    url = f"https://data.solanatracker.io/tokens/{token_mint}/bundled"
    resp = httpx.get(url, headers={"x-api-key": api_key}, timeout=15)
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}"}
    return resp.json()
```

## PumpFun-Specific Patterns

PumpFun tokens are the most common target for sybil attacks. Common patterns:

### Creator Self-Buy Bundle

1. Creator calls PumpFun `create` instruction
2. In the same transaction (or same slot via Jito), creator buys tokens through multiple wallets
3. These wallets now appear as "early holders"

**Detection:**
- Check if any early buyer wallets were funded by the token creator
- Check if buys in slots 0-2 (relative to creation) came from related wallets
- First-slot buys from multiple wallets = almost always bundled

### Supply Concentration from Bundles

```python
def pumpfun_bundle_analysis(
    early_buys: list[dict], creation_slot: int
) -> dict:
    """Analyze bundling patterns for a PumpFun token.

    Args:
        early_buys: Buy events with slot, wallet, amount, is_bundled fields.
        creation_slot: The slot where the token was created.

    Returns:
        Analysis dict with bundle metrics.
    """
    first_3_slots = [b for b in early_buys if b["slot"] - creation_slot <= 3]
    bundled_early = [b for b in first_3_slots if b.get("is_bundled", False)]

    total_early_supply = sum(b["amount"] for b in first_3_slots)
    bundled_supply = sum(b["amount"] for b in bundled_early)

    unique_early_wallets = set(b["wallet"] for b in first_3_slots)
    bundled_wallets = set(b["wallet"] for b in bundled_early)

    return {
        "creation_slot": creation_slot,
        "first_3_slot_buys": len(first_3_slots),
        "bundled_buys": len(bundled_early),
        "unique_early_wallets": len(unique_early_wallets),
        "bundled_wallets": len(bundled_wallets),
        "total_early_supply": total_early_supply,
        "bundled_supply": bundled_supply,
        "bundled_supply_pct": bundled_supply / max(total_early_supply, 1) * 100,
    }
```

## Metrics and Risk Interpretation

### Bundle Ratio

`bundle_ratio = bundled_buys / total_early_buys`

| Bundle Ratio | Risk Level | Interpretation |
|-------------|------------|----------------|
| 0.0 | None | No bundled activity detected |
| 0.01 - 0.10 | Low | Minor bundling, possibly MEV bots |
| 0.10 - 0.25 | Moderate | Significant bundling, review clusters |
| 0.25 - 0.50 | High | Heavy bundling, likely coordinated launch |
| > 0.50 | Critical | Majority of early buys bundled, probable sybil |

### Bundled Supply Percentage

`bundled_supply_pct = bundled_token_amount / total_circulating_supply * 100`

| Bundled Supply % | Risk Level | Interpretation |
|-----------------|------------|----------------|
| < 2% | Low | Negligible bundled holdings |
| 2-10% | Moderate | Notable bundled position |
| 10-30% | High | Large coordinated position |
| > 30% | Critical | Dominant supply held by bundlers |

### Bundler Wallet Count

| Bundler Wallets | Interpretation |
|----------------|----------------|
| 1-2 | Single actor with modest distribution |
| 3-10 | Organized sybil operation |
| 10-30 | Large-scale fake holder inflation |
| > 30 | Industrial sybil farming |

## Combining Bundle Detection with Funding Analysis

Bundle detection alone identifies the mechanism. Combining with funding source analysis identifies the actor:

```python
def correlate_bundles_with_funding(
    bundle_wallets: list[str],
    funding_clusters: dict[str, list[str]],
) -> list[dict]:
    """Find overlap between bundled wallets and funding clusters.

    When bundled wallets also share a funding source, confidence
    in sybil detection is very high.
    """
    results = []
    bundle_set = set(bundle_wallets)

    for funder, funded_wallets in funding_clusters.items():
        overlap = bundle_set.intersection(set(funded_wallets))
        if overlap:
            results.append({
                "funder": funder,
                "bundled_and_funded": list(overlap),
                "overlap_count": len(overlap),
                "total_funded": len(funded_wallets),
                "confidence": "HIGH" if len(overlap) >= 3 else "MODERATE",
            })

    return results
```

## Edge Cases

- **MEV bots**: Legitimate MEV searchers also use bundles — not all bundles are sybil
- **Aggregator routers**: Jupiter and other aggregators may route through multiple accounts
- **Partial detection**: Some bundles only detectable via Jito-specific APIs, not standard RPC
- **Historical data**: Jito bundle metadata may not be available for older transactions
- **False negatives**: Sophisticated operators use separate wallets with no on-chain link
