# Sybil Detection — Clustering Methods

Methods for grouping wallets into coordinated clusters based on funding sources, trading timing, and transfer graph structure.

## Funding Source Clustering

The most reliable sybil signal: multiple holder wallets funded from the same SOL source.

### Algorithm

1. For each holder wallet, fetch recent SOL transfers **in** (received)
2. Extract the `fromUserAccount` for each incoming SOL transfer
3. Group holder wallets by their funder address
4. Clusters of 3+ wallets from the same funder = suspicious

### Implementation

```python
from collections import defaultdict
import httpx

def cluster_by_funding(
    holder_wallets: list[str],
    helius_key: str,
    min_cluster_size: int = 3,
    min_sol_amount: float = 0.001,
) -> dict[str, list[str]]:
    """Group holder wallets by their SOL funding source.

    Args:
        holder_wallets: List of token holder wallet addresses.
        helius_key: Helius API key for transaction lookups.
        min_cluster_size: Minimum wallets from same funder to flag.
        min_sol_amount: Minimum SOL transfer to consider as funding (in SOL).

    Returns:
        Dict mapping funder address -> list of funded holder wallets.
    """
    funder_to_holders: dict[str, list[str]] = defaultdict(list)

    for wallet in holder_wallets:
        url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions"
        resp = httpx.get(url, params={
            "api-key": helius_key,
            "type": "TRANSFER",
            "limit": 50,
        }, timeout=15)
        if resp.status_code != 200:
            continue

        for tx in resp.json():
            for transfer in tx.get("nativeTransfers", []):
                if (
                    transfer["toUserAccount"] == wallet
                    and transfer["amount"] > min_sol_amount * 1e9
                ):
                    funder_to_holders[transfer["fromUserAccount"]].append(wallet)

    # Filter to clusters meeting minimum size
    return {
        funder: wallets
        for funder, wallets in funder_to_holders.items()
        if len(wallets) >= min_cluster_size
    }
```

### Multi-Hop Tracing

Sophisticated sybils use intermediary wallets. Trace 2 hops:

```
Real Funder -> Intermediary A -> Holder Wallet 1
Real Funder -> Intermediary B -> Holder Wallet 2
Real Funder -> Intermediary C -> Holder Wallet 3
```

At hop 1, each holder has a different funder. At hop 2, all trace to the same source.

```python
def trace_funding_chain(
    wallet: str, helius_key: str, max_hops: int = 2
) -> list[list[str]]:
    """Trace funding chain back N hops. Returns list of chains.

    Each chain is [wallet, funder_hop1, funder_hop2, ...].
    """
    chains: list[list[str]] = [[wallet]]

    for hop in range(max_hops):
        new_chains = []
        for chain in chains:
            tip = chain[-1]
            funders = _get_sol_funders(tip, helius_key)
            if funders:
                for funder in funders[:3]:  # Limit branching
                    new_chains.append(chain + [funder])
            else:
                new_chains.append(chain)
        chains = new_chains

    return chains
```

### Time Window Analysis

Funding timing adds confidence to cluster detection:

| Timing | Interpretation |
|--------|---------------|
| Funded < 1h before token creation | Very likely sybil preparation |
| Funded < 24h before token creation | Suspicious, especially if clustered |
| Funded > 7 days before token creation | Lower suspicion (pre-existing wallet) |
| Funded identical amounts | Automated distribution (high confidence sybil) |

## Co-Trade Timing Analysis

Wallets buying the same token within a narrow time window indicates coordination.

### Slot-Based Grouping

Solana slots are ~400ms. Buys in the same slot from different wallets are almost certainly coordinated.

```python
from collections import defaultdict

def group_buys_by_slot(
    buy_events: list[dict], window: int = 3
) -> list[dict]:
    """Group buy events into slot-based clusters.

    Args:
        buy_events: List of {"wallet": str, "slot": int, "amount": float, "tx_sig": str}.
        window: Number of slots to consider as "same time".

    Returns:
        List of cluster dicts with wallets, slot range, and total amount.
    """
    if not buy_events:
        return []

    buy_events.sort(key=lambda x: x["slot"])
    clusters = []
    current = [buy_events[0]]

    for event in buy_events[1:]:
        if event["slot"] - current[0]["slot"] <= window:
            current.append(event)
        else:
            if len(current) >= 2:
                clusters.append({
                    "wallets": [e["wallet"] for e in current],
                    "slot_start": current[0]["slot"],
                    "slot_end": current[-1]["slot"],
                    "total_amount": sum(e["amount"] for e in current),
                    "buy_count": len(current),
                })
            current = [event]

    if len(current) >= 2:
        clusters.append({
            "wallets": [e["wallet"] for e in current],
            "slot_start": current[0]["slot"],
            "slot_end": current[-1]["slot"],
            "total_amount": sum(e["amount"] for e in current),
            "buy_count": len(current),
        })

    return clusters
```

### Statistical Baseline

To distinguish coordination from coincidence, compare observed co-occurrence against a random baseline:

- **Null hypothesis**: Buys are uniformly distributed across slots
- **Test**: Given N buys over S slots, expected buys per slot = N/S
- **Flag**: If any slot has > 3x expected density, likely coordinated

```python
def co_trade_significance(
    buy_slots: list[int], total_slot_range: int
) -> dict:
    """Test if buy timing is more clustered than random."""
    from collections import Counter
    slot_counts = Counter(buy_slots)
    n_buys = len(buy_slots)
    expected_per_slot = n_buys / max(total_slot_range, 1)

    max_in_slot = max(slot_counts.values()) if slot_counts else 0
    concentration_ratio = max_in_slot / max(expected_per_slot, 0.001)

    return {
        "max_buys_in_single_slot": max_in_slot,
        "expected_per_slot": round(expected_per_slot, 4),
        "concentration_ratio": round(concentration_ratio, 2),
        "is_suspicious": concentration_ratio > 3.0,
    }
```

## Graph-Based Methods

Build a transfer graph between token holders to find densely connected subgroups.

### Transfer Graph Construction

```python
def build_transfer_graph(
    transfers: list[dict], holder_set: set[str]
) -> dict[str, dict[str, float]]:
    """Build directed weighted graph of transfers between holders.

    Args:
        transfers: List of {"from": str, "to": str, "amount": float}.
        holder_set: Set of known holder wallet addresses.

    Returns:
        Adjacency dict: {from_wallet: {to_wallet: total_volume}}.
    """
    graph: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for t in transfers:
        if t["from"] in holder_set and t["to"] in holder_set:
            graph[t["from"]][t["to"]] += t["amount"]

    return dict(graph)
```

### Connected Components

Find groups of wallets that have transferred tokens among themselves:

```python
def find_connected_components(
    graph: dict[str, dict[str, float]]
) -> list[set[str]]:
    """Find connected components in transfer graph (undirected)."""
    all_nodes = set(graph.keys())
    for neighbors in graph.values():
        all_nodes.update(neighbors.keys())

    visited: set[str] = set()
    components: list[set[str]] = []

    for node in all_nodes:
        if node in visited:
            continue
        component: set[str] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            # Add neighbors (both directions)
            for neighbor in graph.get(current, {}):
                stack.append(neighbor)
            for src, neighbors in graph.items():
                if current in neighbors:
                    stack.append(src)
        if len(component) >= 2:
            components.append(component)

    return components
```

### Graph Density Metric

Dense subgraphs (many edges relative to nodes) indicate tightly coordinated groups:

| Density | Interpretation |
|---------|---------------|
| < 0.1 | Normal — sparse transfers between holders |
| 0.1-0.3 | Moderate — some internal circulation |
| > 0.3 | High — likely coordinated wallet cluster |

```python
def subgraph_density(component: set[str], graph: dict[str, dict[str, float]]) -> float:
    """Calculate density of a subgraph (edges / possible edges)."""
    n = len(component)
    if n < 2:
        return 0.0
    possible_edges = n * (n - 1)  # Directed graph
    actual_edges = sum(
        1 for src in component for dst in graph.get(src, {}) if dst in component
    )
    return actual_edges / possible_edges
```

## Limitations

- **Chain-hopping**: Sybils can fund wallets from CEX withdrawals (different addresses each time)
- **Mixing services**: SOL mixers break the funding chain
- **Time delays**: Patient attackers fund wallets days/weeks in advance
- **Intermediary depth**: Tracing beyond 2 hops is computationally expensive and noisy
- **False positives**: Airdrop campaigns legitimately fund many wallets from one source
- **RPC rate limits**: Tracing 100+ wallets requires significant API quota

Combine multiple signals — the intersection of funding clusters + co-trade timing + bundle detection catches most coordinated activity even when individual methods miss sophisticated sybils.
