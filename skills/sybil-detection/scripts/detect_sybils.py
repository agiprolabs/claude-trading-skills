#!/usr/bin/env python3
"""Sybil detection pipeline for Solana tokens.

Analyzes a token's holder base for coordinated wallet clusters, bundled
transactions, wash trading, and fake holder inflation. Produces a composite
sybil risk score with detailed breakdown.

Usage:
    # Live mode (requires API keys):
    TOKEN_MINT=So11... HELIUS_API_KEY=xxx python scripts/detect_sybils.py

    # Demo mode (synthetic data, no API keys needed):
    python scripts/detect_sybils.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    TOKEN_MINT: Solana token mint address to analyze
    HELIUS_API_KEY: Helius API key for transaction lookups (optional in demo mode)
    SOLANA_RPC_URL: Solana RPC endpoint (default: https://api.mainnet-beta.solana.com)
"""

import json
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
TOKEN_MINT = os.getenv("TOKEN_MINT", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
SOLANA_RPC_URL = os.getenv(
    "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
)

# Detection parameters
TOP_HOLDERS_LIMIT = 30
FUNDING_TRACE_LIMIT = 50
CO_TRADE_SLOT_WINDOW = 3
MIN_CLUSTER_SIZE = 3
MIN_SOL_FUNDING = 0.001  # SOL


# ── Data Fetching ──────────────────────────────────────────────────
def get_top_holders(token_mint: str, rpc_url: str, limit: int = 20) -> list[dict]:
    """Fetch top token holders via Solana RPC getTokenLargestAccounts.

    Args:
        token_mint: Token mint address.
        rpc_url: Solana RPC endpoint URL.
        limit: Maximum holders to return (API max is 20).

    Returns:
        List of dicts with 'address' (token account) and 'amount' fields.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenLargestAccounts",
        "params": [token_mint],
    }
    resp = httpx.post(rpc_url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        print(f"RPC error: {data['error']}")
        return []

    accounts = data.get("result", {}).get("value", [])
    return [
        {
            "address": acc["address"],
            "amount": float(acc.get("uiAmount", 0) or 0),
            "amount_raw": acc.get("amount", "0"),
        }
        for acc in accounts[:limit]
    ]


def get_token_account_owner(token_account: str, rpc_url: str) -> Optional[str]:
    """Resolve a token account address to its owner wallet address.

    Args:
        token_account: SPL token account address.
        rpc_url: Solana RPC endpoint URL.

    Returns:
        Owner wallet address, or None if lookup fails.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [token_account, {"encoding": "jsonParsed"}],
    }
    resp = httpx.post(rpc_url, json=payload, timeout=15)
    if resp.status_code != 200:
        return None

    data = resp.json()
    try:
        parsed = data["result"]["value"]["data"]["parsed"]["info"]
        return parsed.get("owner")
    except (KeyError, TypeError):
        return None


def trace_funding_source(
    wallet: str, helius_key: str, limit: int = 50
) -> list[dict]:
    """Trace SOL funding sources for a wallet via Helius parsed transactions.

    Args:
        wallet: Wallet address to trace.
        helius_key: Helius API key.
        limit: Maximum transactions to scan.

    Returns:
        List of dicts with 'funder', 'amount_sol', and 'timestamp' fields.
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

    funders = []
    for tx in resp.json():
        for transfer in tx.get("nativeTransfers", []):
            if (
                transfer["toUserAccount"] == wallet
                and transfer["amount"] > MIN_SOL_FUNDING * 1e9
            ):
                funders.append({
                    "funder": transfer["fromUserAccount"],
                    "amount_sol": transfer["amount"] / 1e9,
                    "timestamp": tx.get("timestamp", 0),
                })
    return funders


def get_early_buy_events(
    token_mint: str, helius_key: str, limit: int = 100
) -> list[dict]:
    """Fetch early buy events for a token via Helius.

    Args:
        token_mint: Token mint address.
        helius_key: Helius API key.
        limit: Maximum transactions to fetch.

    Returns:
        List of buy event dicts with wallet, slot, amount, tx_sig, is_bundled.
    """
    url = f"https://api.helius.xyz/v0/addresses/{token_mint}/transactions"
    try:
        resp = httpx.get(
            url,
            params={"api-key": helius_key, "limit": limit},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
    except httpx.RequestError:
        return []

    buy_events = []
    for tx in resp.json():
        token_transfers = [
            t for t in tx.get("tokenTransfers", [])
            if t.get("mint") == token_mint and t.get("tokenAmount", 0) > 0
        ]
        if not token_transfers:
            continue

        recipients = set(t["toUserAccount"] for t in token_transfers)
        is_bundled = len(recipients) >= 2

        for t in token_transfers:
            buy_events.append({
                "wallet": t["toUserAccount"],
                "slot": tx.get("slot", 0),
                "amount": t.get("tokenAmount", 0),
                "tx_sig": tx.get("signature", ""),
                "is_bundled": is_bundled,
                "timestamp": tx.get("timestamp", 0),
            })

    buy_events.sort(key=lambda x: x["slot"])
    return buy_events


# ── Analysis Functions ─────────────────────────────────────────────
def cluster_by_funder(
    funding_map: dict[str, list[dict]], min_size: int = 3
) -> dict[str, list[str]]:
    """Group wallets by common funding source.

    Args:
        funding_map: Dict mapping wallet -> list of funder records.
        min_size: Minimum cluster size to report.

    Returns:
        Dict mapping funder address -> list of funded holder wallets.
    """
    funder_to_holders: dict[str, list[str]] = defaultdict(list)

    for wallet, funders in funding_map.items():
        for f in funders:
            funder_to_holders[f["funder"]].append(wallet)

    # Deduplicate and filter
    return {
        funder: list(set(wallets))
        for funder, wallets in funder_to_holders.items()
        if len(set(wallets)) >= min_size
    }


def detect_co_trades(
    buy_events: list[dict], slot_window: int = 3
) -> list[dict]:
    """Detect co-trading clusters — wallets buying in the same slot window.

    Args:
        buy_events: Sorted list of buy events with 'wallet' and 'slot'.
        slot_window: Maximum slot gap to consider as coordinated.

    Returns:
        List of cluster dicts with wallets, slot range, and buy count.
    """
    if not buy_events:
        return []

    clusters = []
    current = [buy_events[0]]

    for event in buy_events[1:]:
        if event["slot"] - current[0]["slot"] <= slot_window:
            current.append(event)
        else:
            if len(current) >= 2:
                wallets = list(set(e["wallet"] for e in current))
                if len(wallets) >= 2:
                    clusters.append({
                        "wallets": wallets,
                        "slot_start": current[0]["slot"],
                        "slot_end": current[-1]["slot"],
                        "buy_count": len(current),
                        "total_amount": sum(e["amount"] for e in current),
                    })
            current = [event]

    if len(current) >= 2:
        wallets = list(set(e["wallet"] for e in current))
        if len(wallets) >= 2:
            clusters.append({
                "wallets": wallets,
                "slot_start": current[0]["slot"],
                "slot_end": current[-1]["slot"],
                "buy_count": len(current),
                "total_amount": sum(e["amount"] for e in current),
            })

    return clusters


def check_bundle_ratio(early_buys: list[dict], window_slots: int = 5) -> dict:
    """Calculate bundled vs independent buy ratio for early transactions.

    Args:
        early_buys: List of buy events with 'is_bundled' and 'slot' fields.
        window_slots: Number of slots from first buy to consider as "early".

    Returns:
        Dict with bundle metrics.
    """
    if not early_buys:
        return {
            "total_early_buys": 0,
            "bundled_buys": 0,
            "bundle_ratio": 0.0,
            "bundled_supply_pct": 0.0,
        }

    first_slot = min(b["slot"] for b in early_buys)
    early = [b for b in early_buys if b["slot"] - first_slot <= window_slots]
    bundled = [b for b in early if b.get("is_bundled", False)]

    total_amount = sum(b["amount"] for b in early) or 1
    bundled_amount = sum(b["amount"] for b in bundled)

    return {
        "total_early_buys": len(early),
        "bundled_buys": len(bundled),
        "bundle_ratio": len(bundled) / max(len(early), 1),
        "bundled_supply_pct": bundled_amount / total_amount,
        "bundled_wallets": list(set(b["wallet"] for b in bundled)),
    }


def detect_wash_cycles(
    transfers: list[dict], holder_set: set[str]
) -> list[tuple[str, str, float, float]]:
    """Find reciprocal transfer patterns suggesting wash trading.

    Args:
        transfers: List of {"from": str, "to": str, "amount": float}.
        holder_set: Set of known holder wallet addresses.

    Returns:
        List of (wallet_a, wallet_b, vol_a_to_b, vol_b_to_a) tuples.
    """
    edges: dict[tuple[str, str], float] = defaultdict(float)

    for t in transfers:
        if t["from"] in holder_set and t["to"] in holder_set:
            edges[(t["from"], t["to"])] += t["amount"]

    wash_pairs = []
    seen: set[tuple[str, str]] = set()

    for (a, b), vol_ab in edges.items():
        if (b, a) in seen:
            continue
        vol_ba = edges.get((b, a), 0)
        if vol_ba > 0:
            wash_pairs.append((a, b, vol_ab, vol_ba))
            seen.add((a, b))

    return wash_pairs


def compute_sybil_score(metrics: dict) -> dict:
    """Compute composite sybil risk score from individual metrics.

    Args:
        metrics: Dict with keys: max_cluster_size, co_trade_pct,
                 bundle_ratio, unique_funder_ratio, transfer_density,
                 wash_pairs.

    Returns:
        Dict with 'score' (0-100), 'risk_level', and 'components'.
    """
    weights = {
        "funding_cluster": 25,
        "co_trade": 20,
        "bundle_ratio": 20,
        "unique_funder": 15,
        "transfer_density": 10,
        "wash_trade": 10,
    }

    scores = {
        "funding_cluster": min(metrics.get("max_cluster_size", 0) / 20, 1.0),
        "co_trade": min(metrics.get("co_trade_pct", 0) / 0.3, 1.0),
        "bundle_ratio": min(metrics.get("bundle_ratio", 0) / 0.5, 1.0),
        "unique_funder": 1.0 - min(metrics.get("unique_funder_ratio", 1.0), 1.0),
        "transfer_density": min(metrics.get("transfer_density", 0) / 0.3, 1.0),
        "wash_trade": min(metrics.get("wash_pairs", 0) / 5, 1.0),
    }

    composite = sum(scores[k] * weights[k] for k in weights)

    if composite < 30:
        risk_level = "LOW"
    elif composite < 60:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    return {
        "score": round(composite, 1),
        "risk_level": risk_level,
        "components": {k: round(v, 3) for k, v in scores.items()},
    }


# ── Demo Mode ──────────────────────────────────────────────────────
def generate_demo_data() -> dict:
    """Generate synthetic data showing a typical sybil pattern.

    Returns:
        Dict with holders, funding_map, buy_events, and transfers.
    """
    # Simulated sybil scenario: 15 holders, 8 funded from same source
    sybil_funder = "SybilFunder1111111111111111111111111111111"
    creator = "TokenCreator1111111111111111111111111111111"

    # Sybil cluster: 8 wallets funded by same entity
    sybil_wallets = [f"SybilWallet{i:04d}1111111111111111111111111111" for i in range(8)]

    # Organic wallets: 7 wallets with independent funding
    organic_wallets = [f"OrganicWlt{i:04d}1111111111111111111111111111" for i in range(7)]
    organic_funders = [f"IndepFunder{i:04d}1111111111111111111111111111" for i in range(7)]

    all_wallets = sybil_wallets + organic_wallets
    creation_slot = 250_000_000

    # Funding map
    funding_map: dict[str, list[dict]] = {}
    for w in sybil_wallets:
        funding_map[w] = [{"funder": sybil_funder, "amount_sol": 0.05, "timestamp": 1700000000}]
    for i, w in enumerate(organic_wallets):
        funding_map[w] = [{"funder": organic_funders[i], "amount_sol": 0.5 + i * 0.1, "timestamp": 1699000000 + i * 86400}]

    # Buy events: sybil wallets buy in first 2 slots, organic spread over 100 slots
    buy_events = []
    for i, w in enumerate(sybil_wallets):
        buy_events.append({
            "wallet": w,
            "slot": creation_slot + (i % 2),  # Slots 0-1
            "amount": 1_000_000 + i * 50_000,
            "tx_sig": f"sybiltx{i:04d}",
            "is_bundled": i < 4,  # First 4 are bundled
            "timestamp": 1700000100 + i,
        })
    for i, w in enumerate(organic_wallets):
        buy_events.append({
            "wallet": w,
            "slot": creation_slot + 10 + i * 15,  # Spread across many slots
            "amount": 200_000 + i * 30_000,
            "tx_sig": f"organictx{i:04d}",
            "is_bundled": False,
            "timestamp": 1700000200 + i * 60,
        })
    buy_events.sort(key=lambda x: x["slot"])

    # Internal transfers among sybil wallets (wash trading)
    transfers = []
    for i in range(0, len(sybil_wallets) - 1, 2):
        transfers.append({"from": sybil_wallets[i], "to": sybil_wallets[i + 1], "amount": 500_000})
        transfers.append({"from": sybil_wallets[i + 1], "to": sybil_wallets[i], "amount": 450_000})

    return {
        "holders": all_wallets,
        "funding_map": funding_map,
        "buy_events": buy_events,
        "transfers": transfers,
        "creation_slot": creation_slot,
        "token_mint": "DemoMint1111111111111111111111111111111111111",
    }


# ── Report Printing ────────────────────────────────────────────────
def print_report(
    token_mint: str,
    holders: list[str],
    clusters: dict[str, list[str]],
    co_trade_groups: list[dict],
    bundle_stats: dict,
    wash_pairs: list[tuple],
    score_result: dict,
) -> None:
    """Print formatted sybil detection report.

    Args:
        token_mint: Token mint address.
        holders: List of holder wallet addresses.
        clusters: Funding clusters (funder -> wallets).
        co_trade_groups: Co-trade timing clusters.
        bundle_stats: Bundle ratio metrics.
        wash_pairs: Detected wash trading pairs.
        score_result: Composite sybil score result.
    """
    print("=" * 70)
    print("SYBIL DETECTION REPORT")
    print("=" * 70)
    print(f"Token: {token_mint}")
    print(f"Holders analyzed: {len(holders)}")
    print()

    # Overall score
    risk = score_result["risk_level"]
    score = score_result["score"]
    bar = "#" * int(score) + "-" * (100 - int(score))
    print(f"  SYBIL RISK: {risk} ({score}/100)")
    print(f"  [{bar[:50]}] {score}%")
    print()

    # Component breakdown
    print("  Score Components:")
    for component, value in score_result["components"].items():
        label = component.replace("_", " ").title()
        print(f"    {label:<22} {value:.3f}")
    print()

    # Funding clusters
    print("-" * 70)
    print("FUNDING CLUSTERS")
    print("-" * 70)
    if clusters:
        for funder, wallets in clusters.items():
            print(f"  Funder: {funder[:16]}...")
            print(f"  Funded wallets: {len(wallets)}")
            for w in wallets[:5]:
                print(f"    - {w[:16]}...")
            if len(wallets) > 5:
                print(f"    ... and {len(wallets) - 5} more")
            print()
    else:
        print("  No funding clusters detected (min size: 3)")
    print()

    # Co-trade groups
    print("-" * 70)
    print("CO-TRADE TIMING CLUSTERS")
    print("-" * 70)
    if co_trade_groups:
        for i, group in enumerate(co_trade_groups):
            print(f"  Cluster {i + 1}: {group['buy_count']} buys in slots {group['slot_start']}-{group['slot_end']}")
            print(f"    Wallets: {len(group['wallets'])}")
            print(f"    Total amount: {group['total_amount']:,.0f}")
            for w in group["wallets"][:3]:
                print(f"      - {w[:16]}...")
            if len(group["wallets"]) > 3:
                print(f"      ... and {len(group['wallets']) - 3} more")
            print()
    else:
        print("  No co-trade clusters detected")
    print()

    # Bundle analysis
    print("-" * 70)
    print("BUNDLE ANALYSIS")
    print("-" * 70)
    print(f"  Total early buys: {bundle_stats['total_early_buys']}")
    print(f"  Bundled buys: {bundle_stats['bundled_buys']}")
    print(f"  Bundle ratio: {bundle_stats['bundle_ratio']:.2%}")
    print(f"  Bundled supply %: {bundle_stats['bundled_supply_pct']:.2%}")
    bundled_wallets = bundle_stats.get("bundled_wallets", [])
    if bundled_wallets:
        print(f"  Bundled wallets ({len(bundled_wallets)}):")
        for w in bundled_wallets[:5]:
            print(f"    - {w[:16]}...")
    print()

    # Wash trading
    print("-" * 70)
    print("WASH TRADING")
    print("-" * 70)
    if wash_pairs:
        print(f"  Reciprocal transfer pairs found: {len(wash_pairs)}")
        for a, b, vol_ab, vol_ba in wash_pairs[:5]:
            print(f"    {a[:12]}... <-> {b[:12]}...")
            print(f"      A->B: {vol_ab:,.0f}  B->A: {vol_ba:,.0f}")
        if len(wash_pairs) > 5:
            print(f"    ... and {len(wash_pairs) - 5} more pairs")
    else:
        print("  No wash trading patterns detected")
    print()
    print("=" * 70)
    print("NOTE: This analysis is informational only. Not financial advice.")
    print("=" * 70)


# ── Main ────────────────────────────────────────────────────────────
def run_live(token_mint: str, helius_key: str) -> None:
    """Run live sybil detection against a real token.

    Args:
        token_mint: Solana token mint address.
        helius_key: Helius API key.
    """
    print(f"Analyzing token: {token_mint}")
    print(f"Fetching top holders...")

    # Step 1: Get holders
    holder_accounts = get_top_holders(token_mint, SOLANA_RPC_URL)
    if not holder_accounts:
        print("ERROR: Could not fetch holders. Check token mint address.")
        sys.exit(1)

    # Resolve token accounts to owner wallets
    print(f"Resolving {len(holder_accounts)} token accounts to owner wallets...")
    holders = []
    for acc in holder_accounts:
        owner = get_token_account_owner(acc["address"], SOLANA_RPC_URL)
        if owner:
            holders.append(owner)
        time.sleep(0.1)  # Rate limit courtesy

    if not holders:
        print("ERROR: Could not resolve any holder wallets.")
        sys.exit(1)

    print(f"Resolved {len(holders)} holder wallets.")

    # Step 2: Trace funding sources
    print("Tracing funding sources...")
    funding_map: dict[str, list[dict]] = {}
    for wallet in holders:
        funding_map[wallet] = trace_funding_source(wallet, helius_key)
        time.sleep(0.2)  # Rate limit

    # Step 3: Cluster by funder
    clusters = cluster_by_funder(funding_map, min_size=MIN_CLUSTER_SIZE)

    # Step 4: Get early buy events
    print("Fetching early buy events...")
    buy_events = get_early_buy_events(token_mint, helius_key)

    # Step 5: Detect co-trades
    co_trade_groups = detect_co_trades(buy_events, CO_TRADE_SLOT_WINDOW)

    # Step 6: Check bundles
    bundle_stats = check_bundle_ratio(buy_events)

    # Step 7: Check wash trading (using buy events as proxy for transfers)
    holder_set = set(holders)
    # Approximate: treat sequential buys/sells as transfers
    transfers = [
        {"from": e["wallet"], "to": holders[(i + 1) % len(holders)], "amount": e["amount"]}
        for i, e in enumerate(buy_events)
        if e["wallet"] in holder_set
    ]
    wash_pairs = detect_wash_cycles(transfers, holder_set)

    # Step 8: Compute metrics and score
    all_funders = set()
    for funders in funding_map.values():
        for f in funders:
            all_funders.add(f["funder"])

    metrics = {
        "max_cluster_size": max((len(w) for w in clusters.values()), default=0),
        "co_trade_pct": sum(len(g["wallets"]) for g in co_trade_groups) / max(len(holders), 1),
        "bundle_ratio": bundle_stats["bundle_ratio"],
        "unique_funder_ratio": len(all_funders) / max(len(holders), 1),
        "transfer_density": len(wash_pairs) / max(len(holders), 1),
        "wash_pairs": len(wash_pairs),
    }

    score_result = compute_sybil_score(metrics)

    print_report(
        token_mint, holders, clusters, co_trade_groups,
        bundle_stats, wash_pairs, score_result,
    )


def run_demo() -> None:
    """Run sybil detection on synthetic demo data."""
    print("Running in DEMO mode with synthetic data...")
    print()

    demo = generate_demo_data()
    holders = demo["holders"]
    funding_map = demo["funding_map"]
    buy_events = demo["buy_events"]
    transfers = demo["transfers"]

    # Cluster by funder
    clusters = cluster_by_funder(funding_map, min_size=MIN_CLUSTER_SIZE)

    # Detect co-trades
    co_trade_groups = detect_co_trades(buy_events, CO_TRADE_SLOT_WINDOW)

    # Check bundles
    bundle_stats = check_bundle_ratio(buy_events)

    # Wash trading
    holder_set = set(holders)
    wash_pairs = detect_wash_cycles(transfers, holder_set)

    # Compute metrics
    all_funders = set()
    for funders in funding_map.values():
        for f in funders:
            all_funders.add(f["funder"])

    metrics = {
        "max_cluster_size": max((len(w) for w in clusters.values()), default=0),
        "co_trade_pct": sum(len(g["wallets"]) for g in co_trade_groups) / max(len(holders), 1),
        "bundle_ratio": bundle_stats["bundle_ratio"],
        "unique_funder_ratio": len(all_funders) / max(len(holders), 1),
        "transfer_density": len(wash_pairs) / max(len(holders), 1),
        "wash_pairs": len(wash_pairs),
    }

    score_result = compute_sybil_score(metrics)

    print_report(
        demo["token_mint"], holders, clusters, co_trade_groups,
        bundle_stats, wash_pairs, score_result,
    )


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    elif TOKEN_MINT and HELIUS_API_KEY:
        run_live(TOKEN_MINT, HELIUS_API_KEY)
    elif TOKEN_MINT and not HELIUS_API_KEY:
        print("HELIUS_API_KEY required for live analysis.")
        print("Run with --demo flag for synthetic data demo.")
        sys.exit(1)
    else:
        print("Usage:")
        print("  Live:  TOKEN_MINT=... HELIUS_API_KEY=... python scripts/detect_sybils.py")
        print("  Demo:  python scripts/detect_sybils.py --demo")
        sys.exit(1)
