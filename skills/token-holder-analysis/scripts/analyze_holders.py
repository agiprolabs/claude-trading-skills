#!/usr/bin/env python3
"""Full holder analysis for a Solana token.

Fetches top holders via RPC, computes concentration metrics (Gini, HHI,
Nakamoto coefficient), checks mint/freeze authority, and produces a
comprehensive risk report.

Usage:
    python scripts/analyze_holders.py
    TOKEN_ADDRESS="TokenMint..." python scripts/analyze_holders.py

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint (default: public mainnet)
    TOKEN_ADDRESS: Token mint address to analyze
    SOLANATRACKER_API_KEY: Optional — enables bundler/sniper detection
"""

import os
import sys
import time
from typing import Any, Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
ST_KEY = os.getenv("SOLANATRACKER_API_KEY", "")
TOKEN_ADDRESS = os.getenv(
    "TOKEN_ADDRESS",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
)

# ── RPC Helper ──────────────────────────────────────────────────────


def rpc_call(method: str, params: Optional[list] = None) -> dict[str, Any]:
    """Make a JSON-RPC call to Solana with retry."""
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
                raise RuntimeError(f"RPC error: {data['error'].get('message')}")
            return data.get("result", {})
        except httpx.TimeoutException:
            if attempt < 2:
                time.sleep(2.0)
                continue
            raise
    raise RuntimeError(f"RPC {method} failed after retries")


def st_get(endpoint: str) -> Any:
    """Make a GET request to SolanaTracker API."""
    if not ST_KEY:
        return None
    try:
        resp = httpx.get(
            f"https://data.solanatracker.io{endpoint}",
            headers={"x-api-key": ST_KEY},
            timeout=30.0,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


# ── Data Fetching ───────────────────────────────────────────────────


def get_supply_and_authority(mint: str) -> dict:
    """Get token supply and authority info.

    Args:
        mint: Token mint address.

    Returns:
        Dict with supply, decimals, mint_authority, freeze_authority.
    """
    supply_result = rpc_call("getTokenSupply", [mint])
    supply = supply_result.get("value", {})

    # Get mint account for authority info
    acct_result = rpc_call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    acct_data = acct_result.get("value", {})

    mint_authority = None
    freeze_authority = None
    if acct_data:
        parsed = acct_data.get("data", {}).get("parsed", {}).get("info", {})
        mint_authority = parsed.get("mintAuthority")
        freeze_authority = parsed.get("freezeAuthority")

    return {
        "total_amount": int(supply.get("amount", "0")),
        "decimals": supply.get("decimals", 0),
        "ui_amount": supply.get("uiAmount", 0),
        "mint_authority": mint_authority,
        "freeze_authority": freeze_authority,
    }


def get_top_holders(mint: str) -> list[dict]:
    """Get top 20 holders via RPC."""
    result = rpc_call("getTokenLargestAccounts", [mint])
    return result.get("value", [])


# ── Concentration Metrics ───────────────────────────────────────────


def top_n_pct(amounts: list[int], total: int, n: int) -> float:
    """Percentage held by top N holders."""
    return sum(amounts[:n]) / total * 100 if total > 0 else 0


def gini_coefficient(amounts: list[int]) -> float:
    """Gini coefficient (0=equal, 1=concentrated)."""
    if not amounts or all(a == 0 for a in amounts):
        return 0.0
    sorted_a = sorted(amounts)
    n = len(sorted_a)
    total = sum(sorted_a)
    if total == 0:
        return 0.0
    cumsum = sum((i + 1) * a for i, a in enumerate(sorted_a))
    return (2 * cumsum) / (n * total) - (n + 1) / n


def hhi(amounts: list[int], total: int) -> float:
    """Herfindahl-Hirschman Index (0-10000)."""
    if total == 0:
        return 0.0
    shares = [a / total * 100 for a in amounts]
    return sum(s ** 2 for s in shares)


def nakamoto_coefficient(amounts: list[int]) -> int:
    """Minimum holders for >50% control."""
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


# ── Analysis ────────────────────────────────────────────────────────


def analyze_authority(supply_info: dict) -> list[str]:
    """Analyze mint and freeze authority status.

    Args:
        supply_info: From get_supply_and_authority().

    Returns:
        List of flag strings.
    """
    flags = []

    mint_auth = supply_info.get("mint_authority")
    if mint_auth:
        flags.append(f"[!!] MINT AUTHORITY ACTIVE: {mint_auth[:16]}...")
        flags.append("     Supply can be increased — dilution risk")
    else:
        flags.append("[ok] Mint authority renounced")

    freeze_auth = supply_info.get("freeze_authority")
    if freeze_auth:
        flags.append(f"[!!] FREEZE AUTHORITY ACTIVE: {freeze_auth[:16]}...")
        flags.append("     Token accounts can be frozen")
    else:
        flags.append("[ok] Freeze authority disabled")

    return flags


def analyze_bundlers(bundlers: list[dict]) -> list[str]:
    """Analyze bundler data from SolanaTracker.

    Args:
        bundlers: Bundler response list.

    Returns:
        List of flag strings.
    """
    if not bundlers:
        return ["[ok] No bundler activity detected"]

    total_pct = sum(b.get("holdingPercentage", 0) for b in bundlers)
    flags = [f"[i] {len(bundlers)} bundler wallets detected"]
    flags.append(f"    Combined holding: {total_pct:.1f}%")

    if total_pct > 20:
        flags.append("[!!] High bundler concentration — coordinated launch buying")
    elif total_pct > 10:
        flags.append("[!] Moderate bundler concentration")

    return flags


# ── Display ─────────────────────────────────────────────────────────


def print_report(
    mint: str,
    supply_info: dict,
    holders: list[dict],
    amounts: list[int],
    authority_flags: list[str],
    bundler_flags: list[str],
    risk_score: Optional[int],
) -> None:
    """Print comprehensive holder analysis report."""
    total = supply_info["total_amount"]
    decimals = supply_info["decimals"]

    # Metrics
    t1 = top_n_pct(amounts, total, 1)
    t5 = top_n_pct(amounts, total, 5)
    t10 = top_n_pct(amounts, total, 10)
    t20 = top_n_pct(amounts, total, 20)
    gini = gini_coefficient(amounts)
    hhi_val = hhi(amounts, total)
    naka = nakamoto_coefficient(amounts)

    print(f"\n{'='*65}")
    print(f"TOKEN HOLDER ANALYSIS")
    print(f"{'='*65}")
    print(f"  Mint:        {mint}")
    print(f"  Supply:      {supply_info['ui_amount']:,.0f} ({decimals} decimals)")
    if risk_score is not None:
        print(f"  Risk Score:  {risk_score}/10 (SolanaTracker)")

    # Authority
    print(f"\n--- Authority Status ---")
    for flag in authority_flags:
        print(f"  {flag}")

    # Top holders
    print(f"\n--- Top 20 Holders ---")
    print(f"  {'#':>3}  {'Account':<20} {'Amount':>16} {'% Supply':>10}")
    print(f"  {'─'*3}  {'─'*20} {'─'*16} {'─'*10}")

    for i, h in enumerate(holders[:20], 1):
        addr = h.get("address", "?")
        short = addr[:8] + "..." + addr[-4:]
        amt = int(h.get("amount", 0))
        ui = h.get("uiAmount", 0)
        pct = amt / total * 100 if total > 0 else 0

        amt_str = f"{ui:,.2f}" if ui < 1e9 else f"{ui:,.0f}"
        print(f"  {i:>3}  {short:<20} {amt_str:>16} {pct:>9.2f}%")

    # Concentration metrics
    print(f"\n--- Concentration Metrics ---")
    print(f"  Top 1:       {t1:.2f}%")
    print(f"  Top 5:       {t5:.2f}%")
    print(f"  Top 10:      {t10:.2f}%")
    print(f"  Top 20:      {t20:.2f}%")
    print(f"  Gini:        {gini:.4f}")
    print(f"  HHI:         {hhi_val:.1f}")
    print(f"  Nakamoto:    {naka} holders for >50%")

    # Bundlers
    if bundler_flags:
        print(f"\n--- Bundler Analysis ---")
        for flag in bundler_flags:
            print(f"  {flag}")

    # Overall risk
    print(f"\n--- Overall Assessment ---")

    # Concentration risk
    if t10 > 80 or hhi_val > 5000:
        conc_risk = "EXTREME"
    elif t10 > 50 or hhi_val > 2500:
        conc_risk = "HIGH"
    elif t10 > 30 or hhi_val > 1500:
        conc_risk = "MODERATE"
    else:
        conc_risk = "LOW"

    print(f"  Concentration: {conc_risk}")

    # Authority risk
    has_mint = supply_info.get("mint_authority") is not None
    has_freeze = supply_info.get("freeze_authority") is not None
    if has_mint and has_freeze:
        auth_risk = "HIGH"
    elif has_mint or has_freeze:
        auth_risk = "MODERATE"
    else:
        auth_risk = "LOW"
    print(f"  Authority:     {auth_risk}")

    # Combined
    risks = {"EXTREME": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}
    combined = max(risks.get(conc_risk, 0), risks.get(auth_risk, 0))
    overall = {4: "EXTREME", 3: "HIGH", 2: "MODERATE", 1: "LOW"}.get(combined, "UNKNOWN")
    print(f"  Overall:       {overall}")

    if overall == "EXTREME":
        print("\n  [!!] Token has critical risk factors. Avoid or use minimal size.")
    elif overall == "HIGH":
        print("\n  [!] Significant risk factors present. Use small positions and tight stops.")

    print()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run holder analysis."""
    print(f"Analyzing: {TOKEN_ADDRESS}")

    print("Fetching supply and authority...")
    supply_info = get_supply_and_authority(TOKEN_ADDRESS)
    total = supply_info["total_amount"]
    if total == 0:
        print("Could not fetch token supply. Check the mint address.")
        sys.exit(1)

    time.sleep(0.5)

    print("Fetching top holders...")
    holders = get_top_holders(TOKEN_ADDRESS)
    amounts = sorted([int(h.get("amount", 0)) for h in holders], reverse=True)

    authority_flags = analyze_authority(supply_info)

    # Optional: SolanaTracker enrichment
    risk_score = None
    bundler_flags = []
    if ST_KEY:
        print("Fetching SolanaTracker data...")
        token_data = st_get(f"/tokens/{TOKEN_ADDRESS}")
        if token_data:
            risk_score = token_data.get("risk", {}).get("score")
        time.sleep(0.5)

        bundlers = st_get(f"/tokens/{TOKEN_ADDRESS}/bundlers")
        if bundlers and isinstance(bundlers, list):
            bundler_flags = analyze_bundlers(bundlers)
    else:
        print("  (Set SOLANATRACKER_API_KEY for bundler/sniper detection)")

    print_report(
        TOKEN_ADDRESS, supply_info, holders, amounts,
        authority_flags, bundler_flags, risk_score,
    )


if __name__ == "__main__":
    main()
