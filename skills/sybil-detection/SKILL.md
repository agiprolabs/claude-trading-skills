---
name: sybil-detection
description: Coordinated wallet cluster detection, wash trading identification, and fake activity analysis for Solana tokens
---

# Sybil Detection — Coordinated Wallet & Fake Activity Analysis

Sybil attacks in Solana token markets involve a single entity operating many wallets to create the illusion of organic activity. This skill covers detecting coordinated wallet clusters, wash trading, bundled transactions, and fake holder inflation — critical for evaluating whether a token's metrics reflect real demand or manufactured signals.

## Why Sybil Detection Matters

Token markets on Solana are rife with manufactured signals:

- **Inflated holder counts**: 500 "holders" that are really 10 entities with 50 wallets each
- **Fake volume**: Wash trading between self-controlled wallets to simulate demand
- **Artificial social proof**: Many wallets holding small amounts to appear broadly distributed
- **Rug preparation**: Creator distributes supply across many wallets, then sells coordinated
- **Bundled launches**: PumpFun tokens where creator buys via Jito bundle in first slot

A token showing 1,000 holders with 80% funded from 3 wallets is fundamentally different from one with 1,000 independently-funded holders. Sybil detection separates real demand from theater.

## Detection Categories

### 1. Funding Source Analysis

Trace each holder wallet back 1-2 hops to find who sent them SOL:

```python
import httpx

def trace_funding_source(wallet: str, api_key: str, max_hops: int = 2) -> list[str]:
    """Trace SOL funding sources for a wallet via Helius parsed transactions."""
    url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions"
    resp = httpx.get(url, params={"api-key": api_key, "type": "TRANSFER", "limit": 50})
    transfers = resp.json()

    funders = []
    for tx in transfers:
        for transfer in tx.get("nativeTransfers", []):
            if transfer["toUserAccount"] == wallet and transfer["amount"] > 0.001 * 1e9:
                funders.append(transfer["fromUserAccount"])
    return funders
```

**Key signals:**
- 3+ holder wallets funded from the same source = cluster
- Funding within 24h of token creation = high suspicion
- Funding amounts are identical (e.g., 0.05 SOL to each) = automated distribution

### 2. Co-Trading Patterns

Wallets that buy the same token at nearly the same time are likely coordinated:

```python
def detect_co_trades(buy_events: list[dict], slot_window: int = 3) -> list[list[str]]:
    """Group wallets that bought within the same slot window."""
    buy_events.sort(key=lambda x: x["slot"])
    clusters = []
    current_cluster = [buy_events[0]]

    for i in range(1, len(buy_events)):
        if buy_events[i]["slot"] - current_cluster[0]["slot"] <= slot_window:
            current_cluster.append(buy_events[i])
        else:
            if len(current_cluster) >= 3:
                clusters.append([b["wallet"] for b in current_cluster])
            current_cluster = [buy_events[i]]

    if len(current_cluster) >= 3:
        clusters.append([b["wallet"] for b in current_cluster])
    return clusters
```

**Interpretation:**
- Same slot, different transactions = coordinated (bot-driven)
- Same transaction = bundled (definite sybil)
- First 3 slots after token creation = launch sniping cluster

### 3. Bundled Transactions

Multiple buys packed into a single Solana transaction or Jito bundle:

```python
def check_bundle_ratio(early_buys: list[dict], bundle_window_slots: int = 5) -> dict:
    """Calculate the ratio of bundled vs independent early buys."""
    bundled = [b for b in early_buys if b.get("is_bundled", False)]
    first_slot = min(b["slot"] for b in early_buys) if early_buys else 0
    early = [b for b in early_buys if b["slot"] - first_slot <= bundle_window_slots]

    return {
        "total_early_buys": len(early),
        "bundled_buys": len(bundled),
        "bundle_ratio": len(bundled) / max(len(early), 1),
        "bundled_supply_pct": sum(b["amount"] for b in bundled) / max(sum(b["amount"] for b in early), 1),
    }
```

See `references/bundler_detection.md` for PumpFun-specific patterns and Jito bundle mechanics.

### 4. Wash Trading Detection

Same entity buying and selling through multiple wallets to inflate volume:

**Signals:**
- Wallet A buys token, transfers to Wallet B, Wallet B sells — circular flow
- Multiple wallets trading back and forth with no net position change
- Volume concentrated in wallet pairs with funding links

```python
def detect_wash_cycles(transfers: list[dict], holder_set: set[str]) -> list[tuple]:
    """Find circular transfer patterns among known holders."""
    # Build directed graph of transfers between holders
    edges: dict[tuple, float] = {}
    for t in transfers:
        if t["from"] in holder_set and t["to"] in holder_set:
            key = (t["from"], t["to"])
            edges[key] = edges.get(key, 0) + t["amount"]

    # Find reciprocal pairs (A->B and B->A both exist)
    wash_pairs = []
    for (a, b), vol_ab in edges.items():
        vol_ba = edges.get((b, a), 0)
        if vol_ba > 0:
            wash_pairs.append((a, b, vol_ab, vol_ba))
    return wash_pairs
```

### 5. Creator Network Analysis

Identify wallets controlled by the token creator:

- Creator wallet's funding history reveals other wallets it funded
- Those wallets holding token supply = insider distribution
- Creator selling from "different" wallets = disguised dump

## Key Metrics

| Metric | Formula | Healthy | Suspicious | Critical |
|--------|---------|---------|------------|----------|
| Unique funder ratio | unique_funders / total_holders | > 0.8 | 0.4-0.8 | < 0.4 |
| Funding cluster size | max(cluster_sizes) | < 5 | 5-20 | > 20 |
| Co-trade score | wallets_in_first_3_slots / total_holders | < 0.1 | 0.1-0.3 | > 0.3 |
| Bundle ratio | bundled_buys / total_early_buys | < 0.1 | 0.1-0.4 | > 0.4 |
| Bundled supply % | bundled_token_amount / total_supply_sold | < 5% | 5-20% | > 20% |
| Transfer density | internal_transfers / total_transfers | < 0.1 | 0.1-0.3 | > 0.3 |
| Wash trade pairs | reciprocal_pairs / total_holder_pairs | 0 | 1-3 pairs | > 3 pairs |

## Composite Risk Score

Combine individual signals into a single sybil risk score (0-100):

```python
def compute_sybil_score(metrics: dict) -> dict:
    """Compute composite sybil risk score from individual metrics."""
    weights = {
        "funding_cluster": 25,    # Wallets from same funder
        "co_trade": 20,           # Coordinated buy timing
        "bundle_ratio": 20,       # Bundled early transactions
        "unique_funder": 15,      # Diversity of funding sources
        "transfer_density": 10,   # Internal transfers between holders
        "wash_trade": 10,         # Circular trading patterns
    }

    scores = {}
    # Each sub-score normalized to 0-1, then weighted
    scores["funding_cluster"] = min(metrics.get("max_cluster_size", 0) / 20, 1.0)
    scores["co_trade"] = min(metrics.get("co_trade_pct", 0) / 0.3, 1.0)
    scores["bundle_ratio"] = min(metrics.get("bundle_ratio", 0) / 0.5, 1.0)
    scores["unique_funder"] = 1.0 - min(metrics.get("unique_funder_ratio", 1.0), 1.0)
    scores["transfer_density"] = min(metrics.get("transfer_density", 0) / 0.3, 1.0)
    scores["wash_trade"] = min(metrics.get("wash_pairs", 0) / 5, 1.0)

    composite = sum(scores[k] * weights[k] for k in weights)
    risk_level = "LOW" if composite < 30 else "MEDIUM" if composite < 60 else "HIGH"

    return {"score": round(composite, 1), "risk_level": risk_level, "components": scores}
```

## Data Sources

| Source | What It Provides | Auth Required |
|--------|-----------------|---------------|
| Helius parsed transactions | Funding history, transfer details, parsed instruction data | API key (free tier: 30 req/s) |
| SolanaTracker API | Bundler detection, holder lists, token metadata | API key |
| Solana RPC (getSignaturesForAddress) | Raw transaction signatures for any wallet | RPC URL |
| Solana RPC (getTokenLargestAccounts) | Top holders by balance | RPC URL |
| DexScreener | Basic token/pair data for cross-referencing | None |

## Workflow: Evaluate a Token

```python
# 1. Get top holders
holders = get_top_holders(token_mint, rpc_url)

# 2. Trace funding sources for each holder
funding_map = {}
for wallet in holders[:30]:  # Top 30 is usually sufficient
    funding_map[wallet] = trace_funding_source(wallet, helius_key)

# 3. Cluster by common funder
clusters = cluster_by_funder(funding_map)

# 4. Check co-trade timing
early_buys = get_early_buy_events(token_mint, helius_key)
co_trade_groups = detect_co_trades(early_buys)

# 5. Check for bundles
bundle_stats = check_bundle_ratio(early_buys)

# 6. Check wash trading
transfers = get_token_transfers(token_mint, helius_key)
wash_pairs = detect_wash_cycles(transfers, set(holders))

# 7. Compute composite score
metrics = {
    "max_cluster_size": max(len(c) for c in clusters) if clusters else 0,
    "co_trade_pct": sum(len(g) for g in co_trade_groups) / len(holders),
    "bundle_ratio": bundle_stats["bundle_ratio"],
    "unique_funder_ratio": len(set(f for fs in funding_map.values() for f in fs)) / len(holders),
    "transfer_density": len(wash_pairs) / max(len(holders), 1),
    "wash_pairs": len(wash_pairs),
}
result = compute_sybil_score(metrics)
print(f"Sybil Risk: {result['risk_level']} ({result['score']}/100)")
```

## Integration with Other Skills

- **token-holder-analysis**: Use holder list as input; sybil detection adds cluster context
- **helius-api**: Primary data source for parsed transaction history
- **jito-bundles**: Detailed bundle detection and MEV context
- **liquidity-analysis**: Combine with sybil score — low liquidity + high sybil = extreme risk
- **whale-tracking**: Distinguish real whales from sybil cluster aggregates

## Files

| File | Description |
|------|-------------|
| `references/clustering_methods.md` | Funding source clustering, co-trade timing analysis, graph-based detection methods |
| `references/bundler_detection.md` | Bundled transaction detection, PumpFun patterns, Jito bundle mechanics |
| `scripts/detect_sybils.py` | Full sybil detection pipeline: holders -> funding -> clusters -> risk score |
| `scripts/funding_tracer.py` | Trace funding sources for a set of wallets, group by common ancestor |
