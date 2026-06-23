#!/usr/bin/env python3
"""Fee-aware edge selection and fractional-Kelly sizing for binary prediction markets.

Pure stdlib — no network calls, no API keys. Run directly for a worked example.

Covers: Kalshi taker fee, net_edge, theta gate, maker limit price, Kelly contracts,
and slippage guard. Contract settlement resolution belongs in the market-type skills
(kalshi-weather-markets, kalshi-crypto-index-markets), not here.
"""
from __future__ import annotations
import math


# ---------------------------------------------------------------------------
# Fee calculation
# ---------------------------------------------------------------------------

def kalshi_fee(price: float, contracts: float = 1.0, rate: float = 0.07) -> float:
    """Kalshi taker fee in dollars per contract.

    Formula: ceil(rate × contracts × price × (1 − price) × 100) / 100

    The fee is quadratic in price — maximal near $0.50 (~$1.75/contract),
    approaching zero at $0.01 and $0.99.

    For Polymarket, fee = 0.0 (no explicit taker fee; spread and gas are the cost).
    """
    return math.ceil(rate * contracts * price * (1.0 - price) * 100.0) / 100.0


# ---------------------------------------------------------------------------
# Edge selection
# ---------------------------------------------------------------------------

def net_edge(p_model: float, ask: float, *, fee: bool = True) -> float:
    """Fee-aware net edge per contract.

    net_edge = p_model − ask − kalshi_fee(ask)

    This is the ONLY valid selection metric. Never select on raw win-rate,
    return on notional, or Brier score — they do not account for fees or
    the price you paid.

    Args:
        p_model: calibrated model probability (0 < p_model < 1)
        ask: depth-weighted entry price after walking the ladder to target size
        fee: if True, deduct Kalshi taker fee; set False for Polymarket

    Returns:
        Net edge per contract (negative means skip the trade)
    """
    return p_model - ask - (kalshi_fee(ask) if fee else 0.0)


def theta_for_account(bankroll: float) -> float:
    """Minimum net-edge gate (θ) by account size.

    Kalshi:
        < $2,000  → 15%  (small account; fee drag proportionally higher)
        ≥ $2,000  → 20%  (standard gate covering fee + execution uncertainty)

    Polymarket: use ~5% (no explicit taker fee).

    Args:
        bankroll: current account balance in dollars

    Returns:
        Minimum acceptable net_edge for a trade to be taken
    """
    return 0.15 if bankroll < 2000.0 else 0.20


# ---------------------------------------------------------------------------
# Limit price posting (maker orders)
# ---------------------------------------------------------------------------

def limit_price_cents(p_model: float, theta: float) -> int:
    """Maker bid price in cents, posted theta below model fair value.

    limit_price = floor((p_model − theta) × 100)

    Ensures you only fill when the market moves in your favor by at least theta.
    If the market never reaches your bid, you don't fill — which is correct.

    Args:
        p_model: calibrated model probability
        theta: edge gate (from theta_for_account or manual)

    Returns:
        Integer cent price (post this as the limit order price)
    """
    return math.floor((p_model - theta) * 100)


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------

def kelly_contracts(
    p_model: float,
    entry: float,
    bankroll: float,
    *,
    kelly_frac: float = 0.25,
    max_bet_fraction: float = 0.015,
) -> float:
    """Fractional-Kelly contract size, capped by max_bet_fraction of bankroll.

    Derivation:
        f* = net_edge / (1 − entry)          # full Kelly fraction on these odds
        stake = min(kelly_frac × f* × bankroll, max_bet_fraction × bankroll)
        contracts = stake / entry

    Defaults:
        kelly_frac = 0.25    (quarter-Kelly — standard for uncertain, correlated signals)
        max_bet_fraction = 0.015  (1.5% of bankroll per contract — usually the binding cap)

    Returns 0.0 if net_edge ≤ 0 (should not trade).

    Args:
        p_model: calibrated model probability
        entry: depth-weighted entry price (after ladder walk)
        bankroll: current account balance in dollars
        kelly_frac: fraction of full Kelly to bet (default 0.25)
        max_bet_fraction: hard cap as fraction of bankroll (default 0.015)

    Returns:
        Number of contracts to buy/sell (float; round down in practice)
    """
    edge = net_edge(p_model, entry)
    if edge <= 0 or not (0.0 < entry < 1.0):
        return 0.0
    f = max(0.0, min(1.0, edge / (1.0 - entry)))
    stake = min(kelly_frac * f * bankroll, max_bet_fraction * bankroll)
    return stake / entry


# ---------------------------------------------------------------------------
# Slippage guard
# ---------------------------------------------------------------------------

def slippage_ok(edge: float, slip: float, *, max_frac: float = 0.50) -> bool:
    """Return True if slippage is acceptable relative to the net edge.

    Abort the trade if walking the ladder to target size consumes more than
    max_frac of the net edge (default 50%).

    Args:
        edge: fee-aware net edge per contract (from net_edge())
        slip: slippage cost per contract (depth-weighted entry minus best ask)
        max_frac: maximum allowable slippage as a fraction of edge

    Returns:
        True if slippage is within tolerance, False if the trade should be skipped
    """
    return edge > 0 and slip <= max_frac * edge


# ---------------------------------------------------------------------------
# Worked example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bankroll = 5_000.0
    theta = theta_for_account(bankroll)
    print(f"theta gate for ${bankroll:,.0f} account: {theta:.0%}")

    # Scenario: model says a bracket is worth 0.30; best ask (depth-weighted) is 0.18.
    p_model, ask = 0.30, 0.18
    e = net_edge(p_model, ask)
    fee = kalshi_fee(ask)
    print(f"\nbracket: p_model={p_model}  ask={ask}")
    print(f"  kalshi_fee={fee:.4f}")
    print(f"  net_edge={e:.4f}")
    print(f"  passes theta ({theta:.0%})? {e > theta}")
    print(f"  maker limit price = {limit_price_cents(p_model, theta)}c")
    k = kelly_contracts(p_model, ask, bankroll)
    print(f"  fractional-Kelly contracts = {k:.1f}")
    print(f"  slippage 0.03 ok? {slippage_ok(e, 0.03)}")
    print(f"  slippage 0.09 ok? {slippage_ok(e, 0.09)}")

    # Scenario: model says 0.08, ask is 0.12 — price above model, skip.
    p2, ask2 = 0.08, 0.12
    e2 = net_edge(p2, ask2)
    print(f"\nbracket: p_model={p2}  ask={ask2}")
    print(f"  net_edge={e2:.4f}  → skip (model below ask)")

    # Scenario: small account.
    small_bankroll = 1_000.0
    theta_small = theta_for_account(small_bankroll)
    print(f"\ntheta gate for ${small_bankroll:,.0f} account: {theta_small:.0%}")
    print(f"  limit price for same bracket = {limit_price_cents(p_model, theta_small)}c")
