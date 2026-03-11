#!/usr/bin/env python3
"""Funding source tracer for Solana wallets.

Takes a list of wallet addresses and traces back their SOL funding sources
(1-2 hops). Groups wallets by common ancestor funder to identify coordinated
wallet clusters.

Usage:
    # Live mode:
    WALLET_ADDRESSES=addr1,addr2,addr3 HELIUS_API_KEY=xxx python scripts/funding_tracer.py

    # Demo mode:
    python scripts/funding_tracer.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    WALLET_ADDRESSES: Comma-separated list of Solana wallet addresses
    HELIUS_API_KEY: Helius API key for transaction lookups (optional in demo mode)
    SOLANA_RPC_URL: Solana RPC endpoint (default: https://api.mainnet-beta.solana.com)
"""

import os
import sys
import time
from collections import defaultdict
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)

# ── Configuration ───────────────────────────────────────────────────
WALLET_ADDRESSES = os.getenv("WALLET_ADDRESSES", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
SOLANA_RPC_URL = os.getenv(
    "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
)

# Tracing parameters
MAX_HOPS = 2
MIN_SOL_AMOUNT = 0.001  # Minimum SOL transfer to consider as funding
TX_FETCH_LIMIT = 50
REQUEST_DELAY = 0.2  # Seconds between API calls


# ── Data Types ─────────────────────────────────────────────────────
class FundingRecord:
    """Record of a single funding transfer."""

    def __init__(
        self,
        funder: str,
        recipient: str,
        amount_sol: float,
        timestamp: int,
        tx_sig: str = "",
        hop: int = 1,
    ):
        self.funder = funder
        self.recipient = recipient
        self.amount_sol = amount_sol
        self.timestamp = timestamp
        self.tx_sig = tx_sig
        self.hop = hop

    def __repr__(self) -> str:
        return (
            f"FundingRecord(funder={self.funder[:12]}..., "
            f"recipient={self.recipient[:12]}..., "
            f"amount={self.amount_sol:.4f} SOL, hop={self.hop})"
        )


# ── Core Tracing ───────────────────────────────────────────────────
def get_sol_funders(
    wallet: str,
    helius_key: str,
    limit: int = TX_FETCH_LIMIT,
    min_amount_sol: float = MIN_SOL_AMOUNT,
) -> list[FundingRecord]:
    """Fetch SOL funding sources for a wallet via Helius parsed transactions.

    Args:
        wallet: Wallet address to trace.
        helius_key: Helius API key.
        limit: Maximum transactions to scan.
        min_amount_sol: Minimum SOL amount to consider as funding.

    Returns:
        List of FundingRecord objects for incoming SOL transfers.
    """
    url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions"
    try:
        resp = httpx.get(
            url,
            params={"api-key": helius_key, "type": "TRANSFER", "limit": limit},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
    except httpx.RequestError:
        return []

    records = []
    for tx in resp.json():
        for transfer in tx.get("nativeTransfers", []):
            if (
                transfer["toUserAccount"] == wallet
                and transfer["amount"] > min_amount_sol * 1e9
            ):
                records.append(
                    FundingRecord(
                        funder=transfer["fromUserAccount"],
                        recipient=wallet,
                        amount_sol=transfer["amount"] / 1e9,
                        timestamp=tx.get("timestamp", 0),
                        tx_sig=tx.get("signature", ""),
                        hop=1,
                    )
                )

    return records


def trace_funding_chain(
    wallet: str,
    helius_key: str,
    max_hops: int = MAX_HOPS,
    delay: float = REQUEST_DELAY,
) -> list[list[FundingRecord]]:
    """Trace the full funding chain for a wallet up to N hops.

    Args:
        wallet: Starting wallet address.
        helius_key: Helius API key.
        max_hops: Maximum number of hops to trace back.
        delay: Delay between API calls in seconds.

    Returns:
        List of funding chains. Each chain is a list of FundingRecord
        objects from the wallet back to the earliest traced funder.
    """
    chains: list[list[FundingRecord]] = []

    # Hop 1: direct funders of the wallet
    hop1_records = get_sol_funders(wallet, helius_key)
    if not hop1_records:
        return []

    # Take top funders by amount (limit branching)
    hop1_records.sort(key=lambda r: r.amount_sol, reverse=True)
    hop1_top = hop1_records[:3]

    for record in hop1_top:
        chain = [record]

        if max_hops >= 2:
            time.sleep(delay)
            hop2_records = get_sol_funders(record.funder, helius_key)
            if hop2_records:
                hop2_records.sort(key=lambda r: r.amount_sol, reverse=True)
                for h2 in hop2_records[:2]:
                    h2.hop = 2
                    chains.append(chain + [h2])
            else:
                chains.append(chain)
        else:
            chains.append(chain)

    return chains


def trace_all_wallets(
    wallets: list[str],
    helius_key: str,
    max_hops: int = MAX_HOPS,
) -> dict[str, list[list[FundingRecord]]]:
    """Trace funding chains for multiple wallets.

    Args:
        wallets: List of wallet addresses to trace.
        helius_key: Helius API key.
        max_hops: Maximum hops per wallet.

    Returns:
        Dict mapping wallet address -> list of funding chains.
    """
    results: dict[str, list[list[FundingRecord]]] = {}

    for i, wallet in enumerate(wallets):
        print(f"  Tracing wallet {i + 1}/{len(wallets)}: {wallet[:16]}...")
        results[wallet] = trace_funding_chain(wallet, helius_key, max_hops)
        time.sleep(REQUEST_DELAY)

    return results


# ── Clustering ─────────────────────────────────────────────────────
def cluster_by_common_ancestor(
    trace_results: dict[str, list[list[FundingRecord]]],
    min_cluster_size: int = 2,
) -> dict[str, list[dict]]:
    """Group wallets by their common funding ancestors.

    Checks both hop-1 (direct funder) and hop-2 (funder's funder) for
    common addresses.

    Args:
        trace_results: Output from trace_all_wallets.
        min_cluster_size: Minimum wallets sharing a funder to report.

    Returns:
        Dict mapping ancestor address -> list of funded wallet info dicts.
    """
    ancestor_map: dict[str, list[dict]] = defaultdict(list)

    for wallet, chains in trace_results.items():
        seen_ancestors: set[str] = set()
        for chain in chains:
            for record in chain:
                ancestor = record.funder
                if ancestor not in seen_ancestors:
                    seen_ancestors.add(ancestor)
                    ancestor_map[ancestor].append({
                        "wallet": wallet,
                        "hop": record.hop,
                        "amount_sol": record.amount_sol,
                        "timestamp": record.timestamp,
                    })

    # Filter to clusters meeting minimum size
    return {
        ancestor: entries
        for ancestor, entries in ancestor_map.items()
        if len(entries) >= min_cluster_size
    }


def compute_cluster_stats(
    clusters: dict[str, list[dict]],
) -> list[dict]:
    """Compute statistics for each funding cluster.

    Args:
        clusters: Output from cluster_by_common_ancestor.

    Returns:
        List of cluster stat dicts, sorted by size descending.
    """
    stats = []
    for ancestor, entries in clusters.items():
        amounts = [e["amount_sol"] for e in entries]
        timestamps = [e["timestamp"] for e in entries if e["timestamp"] > 0]

        time_spread = 0
        if len(timestamps) >= 2:
            time_spread = max(timestamps) - min(timestamps)

        stats.append({
            "ancestor": ancestor,
            "cluster_size": len(entries),
            "wallets": [e["wallet"] for e in entries],
            "hops": [e["hop"] for e in entries],
            "total_funded_sol": sum(amounts),
            "avg_funded_sol": sum(amounts) / len(amounts),
            "min_funded_sol": min(amounts),
            "max_funded_sol": max(amounts),
            "funding_time_spread_sec": time_spread,
            "all_same_amount": len(set(round(a, 4) for a in amounts)) == 1,
        })

    stats.sort(key=lambda s: s["cluster_size"], reverse=True)
    return stats


# ── Demo Mode ──────────────────────────────────────────────────────
def generate_demo_data() -> dict[str, list[list[FundingRecord]]]:
    """Generate synthetic funding trace data.

    Simulates a scenario with:
    - 5 wallets funded by the same sybil operator (2 hops)
    - 3 wallets with independent funding
    - 2 wallets funded by same CEX withdrawal address (benign cluster)

    Returns:
        Trace results dict matching trace_all_wallets output format.
    """
    results: dict[str, list[list[FundingRecord]]] = {}

    sybil_master = "SybilMaster11111111111111111111111111111111"
    intermediaries = [f"Intermediary{i:02d}111111111111111111111111111111" for i in range(5)]
    sybil_wallets = [f"SybilHolder{i:02d}1111111111111111111111111111111" for i in range(5)]

    # Sybil cluster: all trace back to same master via intermediary
    for i, wallet in enumerate(sybil_wallets):
        hop1 = FundingRecord(
            funder=intermediaries[i],
            recipient=wallet,
            amount_sol=0.05,
            timestamp=1700000000 + i * 60,
            tx_sig=f"sybiltx1_{i:02d}",
            hop=1,
        )
        hop2 = FundingRecord(
            funder=sybil_master,
            recipient=intermediaries[i],
            amount_sol=0.1,
            timestamp=1700000000 + i * 60 - 300,
            tx_sig=f"sybiltx2_{i:02d}",
            hop=2,
        )
        results[wallet] = [[hop1, hop2]]

    # Independent wallets
    indie_funders = [f"IndieFunder{i:02d}11111111111111111111111111111111" for i in range(3)]
    indie_wallets = [f"IndieHolder{i:02d}11111111111111111111111111111111" for i in range(3)]

    for i, wallet in enumerate(indie_wallets):
        hop1 = FundingRecord(
            funder=indie_funders[i],
            recipient=wallet,
            amount_sol=0.5 + i * 0.3,
            timestamp=1699500000 + i * 86400,
            tx_sig=f"indietx_{i:02d}",
            hop=1,
        )
        results[wallet] = [[hop1]]

    # CEX cluster (benign): 2 wallets funded by same Binance hot wallet
    cex_wallet = "BinanceHotWallet111111111111111111111111111"
    cex_funded = [f"CexFundedWlt{i:02d}1111111111111111111111111111" for i in range(2)]

    for i, wallet in enumerate(cex_funded):
        hop1 = FundingRecord(
            funder=cex_wallet,
            recipient=wallet,
            amount_sol=2.0 + i * 0.5,
            timestamp=1699000000 + i * 7200,
            tx_sig=f"cextx_{i:02d}",
            hop=1,
        )
        results[wallet] = [[hop1]]

    return results


# ── Report Printing ────────────────────────────────────────────────
def print_funding_report(
    trace_results: dict[str, list[list[FundingRecord]]],
    cluster_stats: list[dict],
) -> None:
    """Print formatted funding trace and cluster report.

    Args:
        trace_results: Raw trace results from trace_all_wallets.
        cluster_stats: Computed cluster statistics.
    """
    print("=" * 70)
    print("FUNDING SOURCE TRACE REPORT")
    print("=" * 70)
    print(f"Wallets analyzed: {len(trace_results)}")
    print()

    # Individual wallet traces
    print("-" * 70)
    print("INDIVIDUAL WALLET TRACES")
    print("-" * 70)
    for wallet, chains in trace_results.items():
        print(f"\n  Wallet: {wallet[:20]}...")
        if not chains:
            print("    No funding sources found")
            continue
        for j, chain in enumerate(chains):
            path_parts = [wallet[:12] + "..."]
            for record in chain:
                path_parts.append(
                    f"{record.funder[:12]}... ({record.amount_sol:.4f} SOL, hop {record.hop})"
                )
            path_str = " <- ".join(path_parts)
            print(f"    Chain {j + 1}: {path_str}")

    print()

    # Cluster analysis
    print("-" * 70)
    print("FUNDING CLUSTERS")
    print("-" * 70)
    if not cluster_stats:
        print("  No clusters detected (all wallets have independent funding)")
    else:
        for i, stat in enumerate(cluster_stats):
            suspicion = "HIGH" if stat["cluster_size"] >= 3 else "MODERATE"
            if stat["all_same_amount"]:
                suspicion = "VERY HIGH (identical amounts)"

            print(f"\n  Cluster {i + 1}:")
            print(f"    Common ancestor: {stat['ancestor'][:20]}...")
            print(f"    Cluster size: {stat['cluster_size']} wallets")
            print(f"    Suspicion level: {suspicion}")
            print(f"    Total funded: {stat['total_funded_sol']:.4f} SOL")
            print(f"    Avg per wallet: {stat['avg_funded_sol']:.4f} SOL")
            print(f"    Amount range: {stat['min_funded_sol']:.4f} - {stat['max_funded_sol']:.4f} SOL")
            print(f"    Same amounts: {'Yes' if stat['all_same_amount'] else 'No'}")

            if stat["funding_time_spread_sec"] > 0:
                hours = stat["funding_time_spread_sec"] / 3600
                print(f"    Funding time spread: {hours:.1f} hours")

            print(f"    Hops from wallets: {stat['hops']}")
            print(f"    Wallets:")
            for w in stat["wallets"][:5]:
                print(f"      - {w[:20]}...")
            if len(stat["wallets"]) > 5:
                print(f"      ... and {len(stat['wallets']) - 5} more")

    print()

    # Summary
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    total_wallets = len(trace_results)
    clustered_wallets = set()
    for stat in cluster_stats:
        clustered_wallets.update(stat["wallets"])
    independent = total_wallets - len(clustered_wallets)

    print(f"  Total wallets: {total_wallets}")
    print(f"  In clusters: {len(clustered_wallets)}")
    print(f"  Independent: {independent}")
    print(f"  Unique funder ratio: {independent / max(total_wallets, 1):.2%}")
    print(f"  Clusters found: {len(cluster_stats)}")
    if cluster_stats:
        print(f"  Largest cluster: {cluster_stats[0]['cluster_size']} wallets")
    print()
    print("=" * 70)
    print("NOTE: This analysis is informational only. Not financial advice.")
    print("=" * 70)


# ── Main ────────────────────────────────────────────────────────────
def run_live(wallets: list[str], helius_key: str) -> None:
    """Run live funding trace against real wallets.

    Args:
        wallets: List of wallet addresses to trace.
        helius_key: Helius API key.
    """
    print(f"Tracing funding sources for {len(wallets)} wallets...")
    print(f"Max hops: {MAX_HOPS}")
    print()

    trace_results = trace_all_wallets(wallets, helius_key, MAX_HOPS)
    clusters = cluster_by_common_ancestor(trace_results, min_cluster_size=2)
    stats = compute_cluster_stats(clusters)

    print_funding_report(trace_results, stats)


def run_demo() -> None:
    """Run funding trace on synthetic demo data."""
    print("Running in DEMO mode with synthetic data...")
    print()

    trace_results = generate_demo_data()
    clusters = cluster_by_common_ancestor(trace_results, min_cluster_size=2)
    stats = compute_cluster_stats(clusters)

    print_funding_report(trace_results, stats)


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    elif WALLET_ADDRESSES and HELIUS_API_KEY:
        wallet_list = [w.strip() for w in WALLET_ADDRESSES.split(",") if w.strip()]
        if len(wallet_list) < 2:
            print("Provide at least 2 wallet addresses (comma-separated).")
            sys.exit(1)
        run_live(wallet_list, HELIUS_API_KEY)
    elif WALLET_ADDRESSES and not HELIUS_API_KEY:
        print("HELIUS_API_KEY required for live analysis.")
        print("Run with --demo flag for synthetic data demo.")
        sys.exit(1)
    else:
        print("Usage:")
        print("  Live:  WALLET_ADDRESSES=a,b,c HELIUS_API_KEY=... python scripts/funding_tracer.py")
        print("  Demo:  python scripts/funding_tracer.py --demo")
        sys.exit(1)
