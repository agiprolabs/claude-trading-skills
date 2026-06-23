#!/usr/bin/env python3
"""Edge selection, sizing, and settlement resolution for Kalshi-style binary brackets.

Pure stdlib, no network, no keys. Encodes the rules that decide whether a trade is taken
(fee-aware net edge + theta gate + fractional Kelly + slippage guard) and how a contract
actually settles against an integer NWS-CLI value. Run directly for a worked example.
"""
from __future__ import annotations
import math


# --------------------------------------------------------------------------- #
# Fee + edge selection
# --------------------------------------------------------------------------- #
def kalshi_fee(price: float, contracts: float = 1.0, rate: float = 0.07) -> float:
    """Kalshi taker fee in dollars: ceil(rate * C * p * (1-p) * 100) / 100. Polymarket = 0."""
    return math.ceil(rate * contracts * price * (1.0 - price) * 100.0) / 100.0


def net_edge(p_model: float, ask: float, *, fee: bool = True) -> float:
    """Fee-aware net edge per contract = p_model - ask - fee(ask). Select on THIS, never raw win-rate."""
    return p_model - ask - (kalshi_fee(ask) if fee else 0.0)


def theta_for_account(bankroll: float) -> float:
    """Minimum net-edge gate: 15% under $2k, 20% at/above (Kalshi). Polymarket ~5%."""
    return 0.15 if bankroll < 2000 else 0.20


def limit_price_cents(p_model: float, theta: float) -> int:
    """Post your bid theta below model fair value: floor((p_model - theta) * 100) cents."""
    return math.floor((p_model - theta) * 100)


def kelly_contracts(p_model: float, entry: float, bankroll: float,
                    *, kelly_frac: float = 0.25,
                    max_bet_fraction: float = 0.015) -> float:
    """Fractional-Kelly size (contracts) on the net-edge odds, capped by max_bet_fraction of bankroll.
    f* = edge / (1 - entry); stake = kelly_frac * f* * bankroll; contracts = stake / entry."""
    edge = net_edge(p_model, entry)
    if edge <= 0 or not (0 < entry < 1):
        return 0.0
    f = max(0.0, min(1.0, edge / (1.0 - entry)))
    stake = min(kelly_frac * f * bankroll, max_bet_fraction * bankroll)
    return stake / entry


def slippage_ok(edge: float, slip: float, *, max_frac: float = 0.50) -> bool:
    """Abort if walking the ladder eats more than max_frac of the edge."""
    return edge > 0 and slip <= max_frac * edge


# --------------------------------------------------------------------------- #
# Settlement resolution against an integer NWS-CLI value
# --------------------------------------------------------------------------- #
def bracket_settles_yes(cli_value: int, floor_int: int, cap_int: int) -> bool:
    """2-degree, both-ends-inclusive bracket: YES iff the integer CLI value is floor OR cap."""
    return cli_value == floor_int or cli_value == cap_int


def threshold_settles_yes(cli_value: int, strike: int, *, kind: str) -> bool:
    """Threshold: greater -> YES iff cli >= strike+1; less -> YES iff cli <= strike-1.
    `kind` MUST come from the API `strike_type` field — it is NOT inferable from the ticker."""
    if kind == "greater":
        return cli_value >= strike + 1
    if kind == "less":
        return cli_value <= strike - 1
    raise ValueError(f"kind must be 'greater' or 'less', got {kind!r}")


# --------------------------------------------------------------------------- #
# Forecast quantiles -> (mu, sigma)
# --------------------------------------------------------------------------- #
def mu_sigma_from_quantiles(p10: float, p50: float, p90: float,
                            *, sigma_scale: float = 1.0, sigma_mult: float = 1.0) -> tuple[float, float]:
    """(p90-p10)/2.56 is the 10-90 span of a standard normal (2*1.28). Floors guard overconfidence."""
    sigma_raw = max((p90 - p10) / 2.56, 0.5) * sigma_scale * sigma_mult
    return p50, max(sigma_raw, 0.1)


if __name__ == "__main__":
    bankroll = 5000.0
    theta = theta_for_account(bankroll)
    print(f"theta gate for ${bankroll:.0f} account: {theta:.0%}")

    # Model says a bracket is worth 0.30; best ask is 0.18.
    p_model, ask = 0.30, 0.18
    e = net_edge(p_model, ask)
    print(f"\nbracket: p_model={p_model}  ask={ask}")
    print(f"  fee@ask={kalshi_fee(ask):.4f}  net_edge={e:.4f}  passes theta? {e > theta}")
    print(f"  limit price = {limit_price_cents(p_model, theta)}c")
    print(f"  fractional-Kelly contracts = {kelly_contracts(p_model, ask, bankroll):.1f}")
    print(f"  slippage 0.03 ok? {slippage_ok(e, 0.03)}   slippage 0.09 ok? {slippage_ok(e, 0.09)}")

    # Settlement: CLI high came in at 75F.
    cli = 75
    print(f"\nCLI high = {cli}F")
    print(f"  B74.5 {{74,75}} settles YES? {bracket_settles_yes(cli, 74, 75)}")   # True
    print(f"  B76.5 {{76,77}} settles YES? {bracket_settles_yes(cli, 76, 77)}")   # False
    print(f"  T74 greater settles YES? {threshold_settles_yes(cli, 74, kind='greater')}")  # 75>=75 True
    print(f"  T76 less    settles YES? {threshold_settles_yes(cli, 76, kind='less')}")     # 75<=75 True

    # Forecast quantiles -> mu, sigma
    mu, sigma = mu_sigma_from_quantiles(71.0, 74.0, 77.0)
    print(f"\nquantiles (71,74,77) -> mu={mu:.2f} sigma={sigma:.2f}")
