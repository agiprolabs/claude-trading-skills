#!/usr/bin/env python3
"""Get top holders and concentration metrics for any Solana token.

Uses direct RPC calls (getTokenLargestAccounts, getTokenSupply) to
fetch holder data and compute concentration metrics: top-N percentage,
Gini coefficient, HHI, and Nakamoto coefficient.

Usage:
    python scripts/token_holders.py
    TOKEN_ADDRESS="TokenMint..." python scripts/token_holders.py

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint (default: public mainnet)
    TOKEN_ADDRESS: Token mint address (default: BONK)
"""

import os
import sys
import time
from typing import Any, Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
TOKEN_ADDRESS = os.getenv(
    "TOKEN_ADDRESS",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
)

# ── RPC Helper ──────────────────────────────────────────────────────


def rpc_call(method: str, params: Optional[list] = None) -> dict[str, Any]:
    """Make a JSON-RPC call to Solana with retry.

    Args:
        method: RPC method name.
        params: Method parameters.

    Returns:
        The 'result' field from the response.

    Raises:
        RuntimeError: On persistent RPC error.
    """
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}

    for attempt in range(3):
        try:
            resp = httpx.post(RPC_URL, json=payload, timeout=30.0)

            if resp.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue

            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                err = data["error"]
                raise RuntimeError(f"RPC error: {err.get('message')}")

            return data.get("result", {})

        except httpx.TimeoutException:
            if attempt < 2:
                time.sleep(2.0)
                continue
            raise

    raise RuntimeError(f"RPC {method} failed after retries")


# ── Data Fetching ───────────────────────────────────────────────────


def get_token_supply(mint: str) -> dict:
    """Get total supply of a token.

    Args:
        mint: Token mint address.

    Returns:
        Supply dict with amount, decimals, uiAmount.
    """
    result = rpc_call("getTokenSupply", [mint])
    return result.get("value", {})


def get_largest_accounts(mint: str) -> list[dict]:
    """Get top 20 largest token accounts.

    Args:
        mint: Token mint address.

    Returns:
        List of holder dicts sorted by amount descending.
    """
    result = rpc_call("getTokenLargestAccounts", [mint])
    return result.get("value", [])


# ── Concentration Metrics ───────────────────────────────────────────


def top_n_percentage(amounts: list[int], total_supply: int, n: int) -> float:
    """Percentage held by top N holders.

    Args:
        amounts: Sorted list of holder amounts (largest first).
        total_supply: Total token supply.
        n: Number of top holders.

    Returns:
        Percentage (0-100).
    """
    if total_supply == 0:
        return 0.0
    top_n = sum(amounts[:n])
    return top_n / total_supply * 100


def gini_coefficient(amounts: list[int]) -> float:
    """Calculate Gini coefficient for holder distribution.

    Args:
        amounts: List of holder amounts (any order).

    Returns:
        Gini coefficient (0 = equal, 1 = maximally unequal).
    """
    if not amounts or all(a == 0 for a in amounts):
        return 0.0
    sorted_a = sorted(amounts)
    n = len(sorted_a)
    total = sum(sorted_a)
    if total == 0:
        return 0.0
    cumsum = sum((i + 1) * a for i, a in enumerate(sorted_a))
    return (2 * cumsum) / (n * total) - (n + 1) / n


def hhi(amounts: list[int]) -> float:
    """Herfindahl-Hirschman Index for concentration.

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


def nakamoto_coefficient(amounts: list[int]) -> int:
    """Minimum holders needed for >50% control.

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
    for i, amount in enumerate(amounts):
        cumulative += amount
        if cumulative >= threshold:
            return i + 1
    return len(amounts)


def classify_risk(top_10_pct: float, gini_val: float, hhi_val: float) -> str:
    """Classify concentration risk level.

    Args:
        top_10_pct: Percentage held by top 10.
        gini_val: Gini coefficient.
        hhi_val: HHI value.

    Returns:
        Risk level string.
    """
    if top_10_pct > 80 or hhi_val > 5000:
        return "EXTREME"
    if top_10_pct > 50 or hhi_val > 2500:
        return "HIGH"
    if top_10_pct > 30 or hhi_val > 1500:
        return "MODERATE"
    return "LOW"


# ── Display ─────────────────────────────────────────────────────────


def print_report(
    mint: str,
    supply: dict,
    holders: list[dict],
    total_supply: int,
    amounts: list[int],
) -> None:
    """Print formatted holder analysis report.

    Args:
        mint: Token mint address.
        supply: Token supply info.
        holders: Top holder list from RPC.
        total_supply: Total supply in raw units.
        amounts: Sorted amounts (largest first).
    """
    decimals = supply.get("decimals", 0)
    ui_supply = supply.get("uiAmount", 0)

    print(f"\n{'='*60}")
    print(f"TOKEN HOLDER ANALYSIS")
    print(f"{'='*60}")
    print(f"  Mint:     {mint}")
    print(f"  Supply:   {ui_supply:,.0f} ({decimals} decimals)")

    # Top holders table
    print(f"\n--- Top 20 Holders ---")
    print(f"  {'#':>3}  {'Account':<20} {'Amount':>16} {'% Supply':>10}")
    print(f"  {'─'*3}  {'─'*20} {'─'*16} {'─'*10}")

    for i, h in enumerate(holders, 1):
        addr = h.get("address", "?")
        addr_short = addr[:8] + "..." + addr[-4:]
        amount = int(h.get("amount", 0))
        ui = h.get("uiAmount", 0)
        pct = amount / total_supply * 100 if total_supply > 0 else 0

        amount_str = f"{ui:,.2f}" if ui < 1e9 else f"{ui:,.0f}"
        print(f"  {i:>3}  {addr_short:<20} {amount_str:>16} {pct:>9.2f}%")

    # Concentration metrics
    t1 = top_n_percentage(amounts, total_supply, 1)
    t5 = top_n_percentage(amounts, total_supply, 5)
    t10 = top_n_percentage(amounts, total_supply, 10)
    t20 = top_n_percentage(amounts, total_supply, 20)
    gini_val = gini_coefficient(amounts)
    hhi_val = hhi(amounts)
    naka = nakamoto_coefficient(amounts)

    print(f"\n--- Concentration Metrics ---")
    print(f"  Top 1 holder:   {t1:.2f}%")
    print(f"  Top 5 holders:  {t5:.2f}%")
    print(f"  Top 10 holders: {t10:.2f}%")
    print(f"  Top 20 holders: {t20:.2f}%")
    print(f"  Gini coeff:     {gini_val:.4f}")
    print(f"  HHI:            {hhi_val:.1f}")
    print(f"  Nakamoto coeff: {naka} (holders for >50%)")

    # Risk assessment
    risk = classify_risk(t10, gini_val, hhi_val)
    print(f"\n--- Risk Assessment ---")
    print(f"  Concentration Risk: {risk}")

    if risk == "EXTREME":
        print("  [!!] Extremely concentrated — few wallets control majority")
        print("       High rug/dump risk. Not suitable for significant positions.")
    elif risk == "HIGH":
        print("  [!] Highly concentrated — top holders can significantly impact price")
        print("      Use small position sizes and tight stops.")
    elif risk == "MODERATE":
        print("  [i] Moderate concentration — typical for newer tokens")
        print("      Monitor top holder activity for large sells.")
    else:
        print("  [ok] Well distributed — lower concentration risk")

    # Note about limitations
    print(f"\n--- Notes ---")
    print("  - RPC returns max 20 holders (getTokenLargestAccounts)")
    print("  - Some holders may be pool/program accounts, not individuals")
    print("  - For deeper analysis (100+ holders, bundlers), use SolanaTracker API")

    print()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run token holder analysis."""
    print(f"Analyzing holders for: {TOKEN_ADDRESS}")
    print(f"RPC: {RPC_URL[:40]}...")

    print("Fetching supply...")
    supply = get_token_supply(TOKEN_ADDRESS)
    total_supply = int(supply.get("amount", "0"))

    if total_supply == 0:
        print("Could not fetch token supply. Check the mint address.")
        sys.exit(1)

    time.sleep(0.5)

    print("Fetching top holders...")
    holders = get_largest_accounts(TOKEN_ADDRESS)

    if not holders:
        print("No holder data returned.")
        sys.exit(1)

    amounts = sorted([int(h.get("amount", 0)) for h in holders], reverse=True)

    print_report(TOKEN_ADDRESS, supply, holders, total_supply, amounts)


if __name__ == "__main__":
    main()
