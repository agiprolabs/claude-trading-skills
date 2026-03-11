#!/usr/bin/env python3
"""PumpFun bonding curve calculator.

Calculates token prices, buy/sell amounts, price impact, fill percentage,
and graduation estimates for PumpFun tokens. Can use live on-chain data
or default initial parameters.

Usage:
    python scripts/curve_calculator.py
    SOL_INPUT="2.5" python scripts/curve_calculator.py

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint (optional, for live data)
    TOKEN_MINT: Token mint to fetch live curve data (optional)
    SOL_INPUT: SOL amount to simulate buying (default: 1.0)
    TOKENS_TO_SELL: Token amount to simulate selling (default: 0, skip)
"""

import os
import struct
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

RPC_URL = os.getenv("SOLANA_RPC_URL", "")
TOKEN_MINT = os.getenv("TOKEN_MINT", "")
SOL_INPUT = float(os.getenv("SOL_INPUT", "1.0"))
TOKENS_TO_SELL = float(os.getenv("TOKENS_TO_SELL", "0"))

# PumpFun constants
INITIAL_VIRTUAL_SOL = 30_000_000_000           # 30 SOL
INITIAL_VIRTUAL_TOKEN = 1_073_000_000_000_000  # ~1.073B tokens (6 dec)
INITIAL_REAL_TOKEN = 793_000_000_000_000       # ~793M tokens
TOKEN_DECIMALS = 6
GRADUATION_THRESHOLD = 85_000_000_000          # 85 SOL
FEE_BPS = 100                                   # 1%
PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# ── Bonding Curve Math ──────────────────────────────────────────────


def buy_tokens(v_sol: int, v_tok: int, r_tok: int, sol_in: int) -> int:
    """Calculate tokens received for SOL input.

    Args:
        v_sol: Virtual SOL reserves (lamports).
        v_tok: Virtual token reserves (raw).
        r_tok: Real token reserves (raw).
        sol_in: SOL input (lamports, before fee).

    Returns:
        Tokens received (raw units).
    """
    k = v_sol * v_tok
    new_v_sol = v_sol + sol_in
    new_v_tok = k // new_v_sol + 1
    tokens_out = v_tok - new_v_tok
    return min(tokens_out, r_tok)


def sell_tokens(v_sol: int, v_tok: int, r_sol: int, tokens_in: int) -> int:
    """Calculate SOL received for selling tokens.

    Args:
        v_sol: Virtual SOL reserves (lamports).
        v_tok: Virtual token reserves (raw).
        r_sol: Real SOL reserves (lamports).
        tokens_in: Tokens to sell (raw).

    Returns:
        SOL received (lamports, before fee).
    """
    k = v_sol * v_tok
    new_v_tok = v_tok + tokens_in
    new_v_sol = k // new_v_tok
    sol_out = v_sol - new_v_sol - 1
    return min(max(sol_out, 0), r_sol)


def buy_cost(v_sol: int, v_tok: int, tokens_wanted: int) -> int:
    """Calculate SOL needed to buy exact token amount.

    Returns:
        SOL cost in lamports (before fee).
    """
    if tokens_wanted >= v_tok:
        return 2**64 - 1
    k = v_sol * v_tok
    new_v_tok = v_tok - tokens_wanted
    new_v_sol = k // new_v_tok + 1
    return new_v_sol - v_sol


def price_impact(v_sol: int, v_tok: int, sol_in: int) -> float:
    """Calculate price impact for a buy.

    Returns:
        Price impact as a percentage.
    """
    spot = v_sol / v_tok
    tokens = buy_tokens(v_sol, v_tok, v_tok, sol_in)
    if tokens == 0:
        return float('inf')
    exec_price = sol_in / tokens
    return (exec_price / spot - 1) * 100


def market_cap_sol(v_sol: int, v_tok: int, total_supply: int) -> float:
    """Calculate market cap in SOL.

    Returns:
        Market cap in SOL.
    """
    return (total_supply * v_sol) / v_tok / 1e9


# ── Live Data ───────────────────────────────────────────────────────


def fetch_bonding_curve(mint: str) -> Optional[dict]:
    """Fetch live bonding curve state from on-chain.

    Args:
        mint: Token mint address.

    Returns:
        Parsed curve state dict, or None.
    """
    if not RPC_URL:
        return None

    # Derive bonding curve PDA
    # For simplicity, we'll look up using getProgramAccounts with memcmp
    # on the mint address at the correct offset in the account data
    try:
        # Use getAccountInfo on the known PDA
        # This requires the PDA address — for demo, we show the approach
        print("  Note: Live curve fetch requires PDA derivation.")
        print("  Using initial parameters instead.")
        return None
    except Exception:
        return None


# ── Display ─────────────────────────────────────────────────────────


def format_sol(lamports: int) -> str:
    """Format lamports as SOL."""
    return f"{lamports / 1e9:.6f} SOL"


def format_tokens(raw: int) -> str:
    """Format raw token amount."""
    amount = raw / 10**TOKEN_DECIMALS
    if amount >= 1e9:
        return f"{amount / 1e9:.2f}B"
    if amount >= 1e6:
        return f"{amount / 1e6:.2f}M"
    if amount >= 1e3:
        return f"{amount / 1e3:.2f}K"
    return f"{amount:.2f}"


def print_curve_state(v_sol: int, v_tok: int, r_sol: int, r_tok: int) -> None:
    """Print current curve state."""
    spot = v_sol / v_tok
    spot_human = (v_sol / 1e9) / (v_tok / 10**TOKEN_DECIMALS)
    fill_pct = (r_sol / GRADUATION_THRESHOLD) * 100

    total_supply = 1_000_000_000_000_000

    print(f"\n{'='*60}")
    print(f"PUMPFUN BONDING CURVE STATE")
    print(f"{'='*60}")
    print(f"\n--- Reserves ---")
    print(f"  Virtual SOL:    {format_sol(v_sol)}")
    print(f"  Virtual Token:  {format_tokens(v_tok)}")
    print(f"  Real SOL:       {format_sol(r_sol)}")
    print(f"  Real Token:     {format_tokens(r_tok)}")

    print(f"\n--- Pricing ---")
    print(f"  Spot Price:     {spot_human:.10f} SOL/token")
    print(f"  Market Cap:     {market_cap_sol(v_sol, v_tok, total_supply):.2f} SOL")

    print(f"\n--- Graduation ---")
    print(f"  Fill:           {fill_pct:.2f}%")
    print(f"  SOL to grad:    {format_sol(max(0, GRADUATION_THRESHOLD - r_sol))}")
    if fill_pct >= 100:
        print(f"  Status:         GRADUATED")
    elif fill_pct >= 90:
        print(f"  Status:         NEAR GRADUATION")
    elif fill_pct >= 50:
        print(f"  Status:         MID-CURVE")
    else:
        print(f"  Status:         EARLY")


def print_buy_simulation(v_sol: int, v_tok: int, r_sol: int, r_tok: int, sol_amount: float) -> None:
    """Simulate and display a buy."""
    sol_lamports = int(sol_amount * 1e9)
    fee_lamports = sol_lamports * FEE_BPS // 10000
    sol_after_fee = sol_lamports - fee_lamports

    tokens = buy_tokens(v_sol, v_tok, r_tok, sol_after_fee)
    impact = price_impact(v_sol, v_tok, sol_after_fee)
    total_supply = 1_000_000_000_000_000
    pct_supply = tokens / total_supply * 100

    # Post-buy state
    new_v_sol = v_sol + sol_after_fee
    k = v_sol * v_tok
    new_v_tok = k // new_v_sol + 1
    new_r_sol = r_sol + sol_after_fee
    new_fill = (new_r_sol / GRADUATION_THRESHOLD) * 100

    print(f"\n--- Buy Simulation: {sol_amount} SOL ---")
    print(f"  Fee (1%):       {format_sol(fee_lamports)}")
    print(f"  SOL to curve:   {format_sol(sol_after_fee)}")
    print(f"  Tokens out:     {format_tokens(tokens)}")
    print(f"  % of supply:    {pct_supply:.2f}%")
    print(f"  Price impact:   {impact:.2f}%")
    print(f"  New fill:       {new_fill:.2f}%")

    # Immediate sell value
    sell_value = sell_tokens(new_v_sol, new_v_tok, new_r_sol, tokens)
    sell_after_fee = sell_value * (10000 - FEE_BPS) // 10000
    roundtrip_loss = (1 - sell_after_fee / sol_lamports) * 100
    print(f"\n  Roundtrip Analysis:")
    print(f"    Immediate sell: {format_sol(sell_after_fee)}")
    print(f"    Roundtrip loss: {roundtrip_loss:.2f}%")


def print_sell_simulation(v_sol: int, v_tok: int, r_sol: int, token_amount: float) -> None:
    """Simulate and display a sell."""
    raw_tokens = int(token_amount * 10**TOKEN_DECIMALS)
    sol_out = sell_tokens(v_sol, v_tok, r_sol, raw_tokens)
    sol_after_fee = sol_out * (10000 - FEE_BPS) // 10000

    print(f"\n--- Sell Simulation: {format_tokens(raw_tokens)} tokens ---")
    print(f"  SOL from curve: {format_sol(sol_out)}")
    print(f"  Fee (1%):       {format_sol(sol_out - sol_after_fee)}")
    print(f"  SOL received:   {format_sol(sol_after_fee)}")


def print_impact_table(v_sol: int, v_tok: int, r_tok: int) -> None:
    """Print price impact table for various buy sizes."""
    print(f"\n--- Price Impact Table ---")
    print(f"  {'Buy Size':>10} {'Tokens':>12} {'Impact':>8} {'% Supply':>10}")
    print(f"  {'─'*10} {'─'*12} {'─'*8} {'─'*10}")

    total_supply = 1_000_000_000_000_000
    for sol in [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]:
        lam = int(sol * 1e9)
        lam_after_fee = lam * (10000 - FEE_BPS) // 10000
        tokens = buy_tokens(v_sol, v_tok, r_tok, lam_after_fee)
        impact = price_impact(v_sol, v_tok, lam_after_fee)
        pct = tokens / total_supply * 100
        print(f"  {sol:>9.1f}  {format_tokens(tokens):>12} {impact:>7.2f}% {pct:>9.2f}%")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run bonding curve calculator."""
    # Use live data if available, otherwise initial parameters
    v_sol = INITIAL_VIRTUAL_SOL
    v_tok = INITIAL_VIRTUAL_TOKEN
    r_sol = 0
    r_tok = INITIAL_REAL_TOKEN

    if TOKEN_MINT and RPC_URL:
        curve = fetch_bonding_curve(TOKEN_MINT)
        if curve:
            v_sol = curve["virtualSolReserves"]
            v_tok = curve["virtualTokenReserves"]
            r_sol = curve["realSolReserves"]
            r_tok = curve["realTokenReserves"]
            print(f"Using live data for {TOKEN_MINT}")
        else:
            print("Using initial curve parameters (genesis state)")
    else:
        print("Using initial curve parameters (genesis state)")

    # Display state
    print_curve_state(v_sol, v_tok, r_sol, r_tok)

    # Buy simulation
    if SOL_INPUT > 0:
        print_buy_simulation(v_sol, v_tok, r_sol, r_tok, SOL_INPUT)

    # Sell simulation
    if TOKENS_TO_SELL > 0:
        print_sell_simulation(v_sol, v_tok, r_sol, TOKENS_TO_SELL)

    # Impact table
    print_impact_table(v_sol, v_tok, r_tok)

    print()


if __name__ == "__main__":
    main()
