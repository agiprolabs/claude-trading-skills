#!/usr/bin/env python3
"""Analyze wallet PnL using SolanaTracker Data API.

Fetches wallet PnL data including win rate, realized/unrealized profit,
and per-token breakdown. Useful for evaluating wallet quality before
copy-trading or for tracking your own performance.

Usage:
    python scripts/wallet_pnl.py
    WALLET_ADDRESS="WalletPubkey..." python scripts/wallet_pnl.py

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANATRACKER_API_KEY: Your SolanaTracker API key
    WALLET_ADDRESS: Wallet to analyze
"""

import os
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

API_KEY = os.getenv("SOLANATRACKER_API_KEY", "")
if not API_KEY:
    print("Set SOLANATRACKER_API_KEY environment variable")
    print("  Get a key at https://www.solanatracker.io/data-api")
    sys.exit(1)

# Example: a known active wallet, or set your own
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")
if not WALLET_ADDRESS:
    print("Set WALLET_ADDRESS environment variable")
    print("  Example: WALLET_ADDRESS=\"YourWallet...\" python scripts/wallet_pnl.py")
    sys.exit(1)

BASE_URL = "https://data.solanatracker.io"
HEADERS = {"x-api-key": API_KEY}

# ── API Helper ──────────────────────────────────────────────────────


def st_get(endpoint: str, params: Optional[dict] = None) -> dict | list:
    """Make a GET request to SolanaTracker API with retry.

    Args:
        endpoint: API path.
        params: Query parameters.

    Returns:
        Parsed JSON response.
    """
    for attempt in range(3):
        try:
            resp = httpx.get(
                f"{BASE_URL}{endpoint}",
                headers=HEADERS,
                params=params or {},
                timeout=30.0,
            )
            if resp.status_code == 429:
                wait = 5.0 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 403:
                print("  Access denied — check API key")
                return {}
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            if attempt < 2:
                time.sleep(3.0)
                continue
            raise
    return {}


# ── Data Fetching ───────────────────────────────────────────────────


def fetch_pnl(wallet: str, historic: bool = True) -> dict:
    """Fetch wallet PnL with optional historic intervals.

    Args:
        wallet: Wallet public key.
        historic: Include 1d/7d/30d PnL intervals.

    Returns:
        PnL data dict with summary and token breakdown.
    """
    params = {}
    if historic:
        params["showHistoricPnL"] = "true"
    data = st_get(f"/pnl/{wallet}", params)
    return data if isinstance(data, dict) else {}


def fetch_wallet_trades(wallet: str) -> list[dict]:
    """Fetch recent trade history for a wallet.

    Args:
        wallet: Wallet public key.

    Returns:
        List of trade dicts.
    """
    data = st_get(f"/wallet/{wallet}/trades")
    return data if isinstance(data, list) else []


def fetch_wallet_holdings(wallet: str) -> list[dict]:
    """Fetch current token holdings for a wallet.

    Args:
        wallet: Wallet public key.

    Returns:
        List of held token dicts.
    """
    data = st_get(f"/wallet/{wallet}")
    return data if isinstance(data, list) else []


# ── Analysis ────────────────────────────────────────────────────────


def classify_trader(summary: dict) -> str:
    """Classify trader skill level from PnL summary.

    Args:
        summary: PnL summary dict.

    Returns:
        Classification string.
    """
    win_pct = summary.get("winPercentage", 0)
    total = summary.get("total", 0)
    invested = summary.get("totalInvested", 0)
    trades = summary.get("totalWins", 0) + summary.get("totalLosses", 0)

    if trades < 10:
        return "INSUFFICIENT DATA"

    roi = total / invested if invested > 0 else 0

    if win_pct >= 60 and roi > 0.5:
        return "STRONG PERFORMER"
    if win_pct >= 50 and roi > 0:
        return "PROFITABLE"
    if win_pct >= 40:
        return "MARGINAL"
    return "UNPROFITABLE"


def analyze_token_breakdown(tokens: list[dict]) -> dict:
    """Analyze per-token PnL distribution.

    Args:
        tokens: List of per-token PnL entries.

    Returns:
        Analysis summary dict.
    """
    if not tokens:
        return {}

    winners = [t for t in tokens if t.get("realized", 0) > 0]
    losers = [t for t in tokens if t.get("realized", 0) < 0]
    holding = [t for t in tokens if t.get("holdingAmount", 0) > 0]

    best_trade = max(tokens, key=lambda t: t.get("realized", 0), default={})
    worst_trade = min(tokens, key=lambda t: t.get("realized", 0), default={})

    avg_win = (
        sum(t.get("realized", 0) for t in winners) / len(winners)
        if winners else 0
    )
    avg_loss = (
        sum(t.get("realized", 0) for t in losers) / len(losers)
        if losers else 0
    )

    return {
        "total_tokens_traded": len(tokens),
        "winners": len(winners),
        "losers": len(losers),
        "still_holding": len(holding),
        "avg_win_sol": round(avg_win, 4),
        "avg_loss_sol": round(avg_loss, 4),
        "best_trade_sol": round(best_trade.get("realized", 0), 4),
        "best_trade_token": best_trade.get("tokenAddress", "?")[:12] + "...",
        "worst_trade_sol": round(worst_trade.get("realized", 0), 4),
        "worst_trade_token": worst_trade.get("tokenAddress", "?")[:12] + "...",
        "profit_factor": round(
            abs(sum(t.get("realized", 0) for t in winners)) /
            abs(sum(t.get("realized", 0) for t in losers))
            if losers and sum(t.get("realized", 0) for t in losers) != 0
            else float("inf"),
            2,
        ),
    }


# ── Display ─────────────────────────────────────────────────────────


def format_sol(value: float) -> str:
    """Format a SOL value for display."""
    if abs(value) >= 1000:
        return f"{value:,.1f} SOL"
    return f"{value:.4f} SOL"


def print_report(
    wallet: str,
    pnl_data: dict,
    classification: str,
    token_breakdown: dict,
    holdings: list[dict],
) -> None:
    """Print formatted wallet PnL report.

    Args:
        wallet: Wallet address.
        pnl_data: Full PnL response.
        classification: Trader classification.
        token_breakdown: Per-token analysis.
        holdings: Current holdings.
    """
    summary = pnl_data.get("summary", {})

    print(f"\n{'='*60}")
    print(f"WALLET PnL ANALYSIS")
    print(f"{'='*60}")
    print(f"  Wallet: {wallet}")
    print(f"  Class:  {classification}")

    # Summary
    print(f"\n--- PnL Summary ---")
    print(f"  Realized:       {format_sol(summary.get('realized', 0))}")
    print(f"  Unrealized:     {format_sol(summary.get('unrealized', 0))}")
    print(f"  Total:          {format_sol(summary.get('total', 0))}")
    print(f"  Total Invested: {format_sol(summary.get('totalInvested', 0))}")
    print(f"  Avg Buy Size:   {format_sol(summary.get('averageBuyAmount', 0))}")

    invested = summary.get("totalInvested", 0)
    total = summary.get("total", 0)
    if invested > 0:
        roi = total / invested * 100
        print(f"  ROI:            {roi:+.1f}%")

    # Win/loss
    wins = summary.get("totalWins", 0)
    losses = summary.get("totalLosses", 0)
    total_trades = wins + losses
    print(f"\n--- Win/Loss ---")
    print(f"  Wins:           {wins}")
    print(f"  Losses:         {losses}")
    print(f"  Total Trades:   {total_trades}")
    print(f"  Win Rate:       {summary.get('winPercentage', 0):.1f}%")

    # Token breakdown
    if token_breakdown:
        print(f"\n--- Trade Analysis ---")
        print(f"  Tokens Traded:  {token_breakdown['total_tokens_traded']}")
        print(f"  Still Holding:  {token_breakdown['still_holding']}")
        print(f"  Avg Win:        {format_sol(token_breakdown['avg_win_sol'])}")
        print(f"  Avg Loss:       {format_sol(token_breakdown['avg_loss_sol'])}")
        print(f"  Best Trade:     {format_sol(token_breakdown['best_trade_sol'])} ({token_breakdown['best_trade_token']})")
        print(f"  Worst Trade:    {format_sol(token_breakdown['worst_trade_sol'])} ({token_breakdown['worst_trade_token']})")
        pf = token_breakdown["profit_factor"]
        pf_str = f"{pf:.2f}" if pf != float("inf") else "∞"
        print(f"  Profit Factor:  {pf_str}")

    # Historic PnL trends
    for period, label in [("pnl_1d", "1 Day"), ("pnl_7d", "7 Days"), ("pnl_30d", "30 Days")]:
        hist = pnl_data.get(period, {})
        if hist:
            h_total = hist.get("total", 0)
            h_wins = hist.get("totalWins", 0)
            h_losses = hist.get("totalLosses", 0)
            h_trades = h_wins + h_losses
            if h_trades > 0:
                if period == "pnl_1d":
                    print(f"\n--- Historic PnL ---")
                win_rate = hist.get("winPercentage", 0)
                print(f"  {label:>7}: {format_sol(h_total):>16}  "
                      f"({h_trades} trades, {win_rate:.0f}% win)")

    # Current holdings summary
    if holdings:
        print(f"\n--- Current Holdings ({len(holdings)} tokens) ---")
        # Sort by value if available
        for h in holdings[:5]:
            token = h.get("token", h)
            symbol = token.get("symbol", "?") if isinstance(token, dict) else "?"
            amount = h.get("amount", h.get("balance", 0))
            value = h.get("value", h.get("valueUsd", 0))
            if value:
                print(f"  {symbol:<10} Value: ${value:,.2f}")
            elif amount:
                print(f"  {symbol:<10} Amount: {amount}")

    print()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run wallet PnL analysis."""
    print(f"Analyzing wallet: {WALLET_ADDRESS}")

    print("Fetching PnL data...")
    pnl_data = fetch_pnl(WALLET_ADDRESS, historic=True)

    if not pnl_data:
        print("Could not fetch PnL data. Check the wallet address and API key.")
        sys.exit(1)

    summary = pnl_data.get("summary", {})
    classification = classify_trader(summary)

    print("Fetching holdings...")
    holdings = fetch_wallet_holdings(WALLET_ADDRESS)

    # Analyze token breakdown
    tokens = pnl_data.get("tokens", [])
    token_breakdown = analyze_token_breakdown(tokens)

    # Report
    print_report(WALLET_ADDRESS, pnl_data, classification, token_breakdown, holdings)


if __name__ == "__main__":
    main()
