#!/usr/bin/env python3
"""Scan multiple tokens for holder concentration risk.

Takes a list of token mint addresses and computes concentration metrics
for each, producing a comparative summary table. Useful for screening
a watchlist of tokens before trading.

Usage:
    python scripts/concentration_scanner.py
    TOKENS="mint1,mint2,mint3" python scripts/concentration_scanner.py

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint (default: public mainnet)
    TOKENS: Comma-separated token mint addresses to scan
"""

import os
import sys
import time
from typing import Any, Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# Default: scan some well-known tokens
DEFAULT_TOKENS = ",".join([
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",   # JUP
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
])

TOKENS = os.getenv("TOKENS", DEFAULT_TOKENS).split(",")
TOKENS = [t.strip() for t in TOKENS if t.strip()]

# ── RPC Helper ──────────────────────────────────────────────────────


def rpc_call(method: str, params: Optional[list] = None) -> dict[str, Any]:
    """Make a JSON-RPC call with retry."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    for attempt in range(3):
        try:
            resp = httpx.post(RPC_URL, json=payload, timeout=30.0)
            if resp.status_code == 429:
                time.sleep(3.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                return {}
            return data.get("result", {})
        except (httpx.TimeoutException, httpx.HTTPError):
            if attempt < 2:
                time.sleep(2.0)
                continue
    return {}


# ── Metrics ─────────────────────────────────────────────────────────


def gini(amounts: list[int]) -> float:
    """Gini coefficient."""
    if not amounts or all(a == 0 for a in amounts):
        return 0.0
    s = sorted(amounts)
    n = len(s)
    total = sum(s)
    if total == 0:
        return 0.0
    c = sum((i + 1) * a for i, a in enumerate(s))
    return (2 * c) / (n * total) - (n + 1) / n


def hhi(amounts: list[int], total: int) -> float:
    """HHI index."""
    if total == 0:
        return 0.0
    shares = [a / total * 100 for a in amounts]
    return sum(s ** 2 for s in shares)


def nakamoto(amounts: list[int]) -> int:
    """Nakamoto coefficient."""
    total = sum(amounts)
    if total == 0:
        return 0
    threshold = total * 0.51
    cumulative = 0
    for i, a in enumerate(amounts):
        cumulative += a
        if cumulative >= threshold:
            return i + 1
    return len(amounts)


def risk_level(top10_pct: float, hhi_val: float) -> str:
    """Classify risk level."""
    if top10_pct > 80 or hhi_val > 5000:
        return "EXTREME"
    if top10_pct > 50 or hhi_val > 2500:
        return "HIGH"
    if top10_pct > 30 or hhi_val > 1500:
        return "MODERATE"
    return "LOW"


# ── Scanner ─────────────────────────────────────────────────────────


def scan_token(mint: str) -> Optional[dict]:
    """Scan a single token for concentration metrics.

    Args:
        mint: Token mint address.

    Returns:
        Dict with metrics, or None on failure.
    """
    # Get supply
    supply_result = rpc_call("getTokenSupply", [mint])
    supply_val = supply_result.get("value", {})
    total = int(supply_val.get("amount", "0"))
    if total == 0:
        return None

    time.sleep(0.3)

    # Get holders
    holder_result = rpc_call("getTokenLargestAccounts", [mint])
    holders = holder_result.get("value", [])
    if not holders:
        return None

    amounts = sorted([int(h.get("amount", 0)) for h in holders], reverse=True)

    top1 = sum(amounts[:1]) / total * 100
    top5 = sum(amounts[:5]) / total * 100
    top10 = sum(amounts[:10]) / total * 100
    top20 = sum(amounts[:20]) / total * 100

    hhi_val = hhi(amounts, total)

    # Get mint/freeze authority
    acct_result = rpc_call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    acct_data = acct_result.get("value", {})
    mint_auth = False
    freeze_auth = False
    if acct_data:
        parsed = acct_data.get("data", {}).get("parsed", {}).get("info", {})
        mint_auth = parsed.get("mintAuthority") is not None
        freeze_auth = parsed.get("freezeAuthority") is not None

    return {
        "mint": mint,
        "supply": supply_val.get("uiAmount", 0),
        "decimals": supply_val.get("decimals", 0),
        "holders_sampled": len(holders),
        "top1_pct": round(top1, 2),
        "top5_pct": round(top5, 2),
        "top10_pct": round(top10, 2),
        "top20_pct": round(top20, 2),
        "gini": round(gini(amounts), 4),
        "hhi": round(hhi_val, 1),
        "nakamoto": nakamoto(amounts),
        "mint_authority": mint_auth,
        "freeze_authority": freeze_auth,
        "risk": risk_level(top10, hhi_val),
    }


# ── Display ─────────────────────────────────────────────────────────


def print_results(results: list[dict]) -> None:
    """Print comparative concentration table.

    Args:
        results: List of scan results.
    """
    print(f"\n{'='*90}")
    print(f"CONCENTRATION SCANNER — {len(results)} tokens analyzed")
    print(f"{'='*90}")

    # Summary table
    print(f"\n  {'Token':<16} {'Top1%':>6} {'Top5%':>6} {'Top10%':>7} {'Gini':>6} "
          f"{'HHI':>7} {'Naka':>5} {'Mint':>5} {'Frz':>5} {'Risk':<8}")
    print(f"  {'─'*16} {'─'*6} {'─'*6} {'─'*7} {'─'*6} "
          f"{'─'*7} {'─'*5} {'─'*5} {'─'*5} {'─'*8}")

    for r in results:
        mint_short = r["mint"][:6] + "..." + r["mint"][-4:]
        mint_flag = "YES" if r["mint_authority"] else "no"
        frz_flag = "YES" if r["freeze_authority"] else "no"

        print(f"  {mint_short:<16} {r['top1_pct']:>5.1f}% {r['top5_pct']:>5.1f}% "
              f"{r['top10_pct']:>6.1f}% {r['gini']:>6.4f} {r['hhi']:>7.0f} "
              f"{r['nakamoto']:>5} {mint_flag:>5} {frz_flag:>5} {r['risk']:<8}")

    # Risk summary
    risk_counts = {}
    for r in results:
        risk_counts[r["risk"]] = risk_counts.get(r["risk"], 0) + 1

    print(f"\n--- Risk Distribution ---")
    for level in ["EXTREME", "HIGH", "MODERATE", "LOW"]:
        count = risk_counts.get(level, 0)
        if count > 0:
            bar = "█" * (count * 3)
            print(f"  {level:<10} {count:>3}  {bar}")

    # Flag tokens with authority risks
    auth_risks = [r for r in results if r["mint_authority"] or r["freeze_authority"]]
    if auth_risks:
        print(f"\n--- Authority Warnings ---")
        for r in auth_risks:
            flags = []
            if r["mint_authority"]:
                flags.append("MINTABLE")
            if r["freeze_authority"]:
                flags.append("FREEZEABLE")
            mint_short = r["mint"][:12] + "..."
            print(f"  [!] {mint_short}: {', '.join(flags)}")

    print()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run concentration scanner."""
    print(f"Scanning {len(TOKENS)} tokens...")
    print(f"RPC: {RPC_URL[:40]}...")

    results = []
    for i, mint in enumerate(TOKENS, 1):
        print(f"  [{i}/{len(TOKENS)}] {mint[:16]}...", end=" ")
        result = scan_token(mint)
        if result:
            print(f"Top10: {result['top10_pct']:.1f}%, Risk: {result['risk']}")
            results.append(result)
        else:
            print("FAILED")
        time.sleep(0.5)  # Rate limit courtesy

    if not results:
        print("No tokens could be analyzed.")
        sys.exit(1)

    # Sort by risk (worst first)
    risk_order = {"EXTREME": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3}
    results.sort(key=lambda r: (risk_order.get(r["risk"], 9), -r["top10_pct"]))

    print_results(results)


if __name__ == "__main__":
    main()
