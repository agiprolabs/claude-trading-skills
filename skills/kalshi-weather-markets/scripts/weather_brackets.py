#!/usr/bin/env python3
"""Gaussian bracket/threshold P(YES) and settlement-resolution functions for
Kalshi daily temperature high/low markets.

Pure stdlib — no network, no API keys, no third-party deps (uses math.erf for the
normal CDF so it runs anywhere offline).

Run directly for a worked example:  python3 weather_brackets.py
"""
from __future__ import annotations
import math


# --------------------------------------------------------------------------- #
# Normal CDF (stdlib only)
# --------------------------------------------------------------------------- #

def _phi(x: float) -> float:
    """Standard normal CDF via the error function (stdlib only).

    Φ(x) = 0.5 · (1 + erf(x / √2))
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# --------------------------------------------------------------------------- #
# Forecast → P(YES)  (Gaussian with mandatory half-integer continuity correction)
# --------------------------------------------------------------------------- #

def bracket_p_yes(floor_int: int, cap_int: int, mu: float, sigma: float) -> float:
    """P(YES) for a 2-degree, both-ends-inclusive bracket covering integers
    {floor_int, cap_int} (e.g. B74.5 → floor=74, cap=75) under a forecast N(mu, sigma).

        P = Φ((cap + 0.5 − μ)/σ) − Φ((floor − 0.5 − μ)/σ)

    The ±0.5 continuity correction is REQUIRED — settlement is on integers, not a
    continuous scale. Dropping it biases every bracket. Using 1°F half-open windows
    instead produced a +1640% phantom backtest in one project.
    """
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    return _phi((cap_int + 0.5 - mu) / sigma) - _phi((floor_int - 0.5 - mu) / sigma)


def threshold_p_yes(strike_int: int, mu: float, sigma: float, *, kind: str) -> float:
    """P(YES) for a threshold market under a forecast N(mu, sigma).

    `kind` MUST come from the API `strike_type` field — it is NOT inferable from
    the ticker symbol.

        greater: P = 1 − Φ((T + 0.5 − μ)/σ)   # YES iff cli >= strike + 1
        less:    P =     Φ((T − 0.5 − μ)/σ)    # YES iff cli <= strike - 1
    """
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    if kind == "greater":
        return 1.0 - _phi((strike_int + 0.5 - mu) / sigma)
    if kind == "less":
        return _phi((strike_int - 0.5 - mu) / sigma)
    raise ValueError(f"kind must be 'greater' or 'less', got {kind!r}")


# --------------------------------------------------------------------------- #
# Settlement resolution against an integer NWS-CLI value
# --------------------------------------------------------------------------- #

def bracket_settles_yes(cli_value: int, floor_int: int, cap_int: int) -> bool:
    """2-degree, both-ends-inclusive bracket: YES iff the integer CLI value is floor OR cap.

    Kalshi settles on the NWS CLI integer °F for the LST day (no DST adjustment).
    """
    return cli_value == floor_int or cli_value == cap_int


def threshold_settles_yes(cli_value: int, strike: int, *, kind: str) -> bool:
    """Threshold settlement against an integer NWS-CLI value.

        greater → YES iff cli >= strike + 1
        less    → YES iff cli <= strike - 1

    `kind` MUST come from the API `strike_type` field — it is NOT inferable from
    the ticker symbol.
    """
    if kind == "greater":
        return cli_value >= strike + 1
    if kind == "less":
        return cli_value <= strike - 1
    raise ValueError(f"kind must be 'greater' or 'less', got {kind!r}")


# --------------------------------------------------------------------------- #
# Forecast quantiles → (mu, sigma)
# --------------------------------------------------------------------------- #

def mu_sigma_from_quantiles(p10: float, p50: float, p90: float,
                            *, sigma_scale: float = 1.0,
                            sigma_mult: float = 1.0) -> tuple[float, float]:
    """Convert ensemble quantiles to (mu, sigma) for the Gaussian bracket map.

    The 2.56 divisor is the 10th–90th span of a standard normal (2 × 1.28σ).
    sigma_scale and sigma_mult allow per-city / per-season calibration adjustments.
    Floors guard against overconfident degenerate distributions.

    Returns (mu, sigma) ready to pass into bracket_p_yes / threshold_p_yes.
    """
    sigma_raw = max((p90 - p10) / 2.56, 0.5) * sigma_scale * sigma_mult
    return p50, max(sigma_raw, 0.1)


# --------------------------------------------------------------------------- #
# Overround diagnostic
# --------------------------------------------------------------------------- #

def overround(p_yes_by_bracket: list[float]) -> float:
    """Sum of P(YES) across an event's mutually-exclusive brackets.

    Fair market = 1.0. Typical Kalshi = 1.05–1.15. >> 1.1 signals mispricing or
    data error. Favorite–longshot bias inflates tail brackets above fair value.
    """
    return float(sum(p_yes_by_bracket))


# --------------------------------------------------------------------------- #
# Worked example
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print("=== Bracket P(YES) — NYC high N(mu=74.0, sigma=2.5) ===")
    mu, sigma = 74.0, 2.5
    brackets = {          # ticker → (floor, cap)
        "B70.5": (70, 71),
        "B72.5": (72, 73),
        "B74.5": (74, 75),
        "B76.5": (76, 77),
        "B78.5": (78, 79),
    }
    ps = {}
    for ticker, (lo, hi) in brackets.items():
        ps[ticker] = bracket_p_yes(lo, hi, mu, sigma)
        print(f"  {ticker}  {{{lo},{hi}}}  P(YES)={ps[ticker]:.4f}")
    print(f"  overround (these 5 of full set) = {overround(list(ps.values())):.4f}")

    print("\n=== Threshold P(YES) ===")
    print(f"  T74 greater  P(YES)={threshold_p_yes(74, mu, sigma, kind='greater'):.4f}")
    print(f"  T76 less     P(YES)={threshold_p_yes(76, mu, sigma, kind='less'):.4f}")

    print("\n=== Settlement (CLI high = 75°F) ===")
    cli = 75
    print(f"  B74.5 {{74,75}} settles YES? {bracket_settles_yes(cli, 74, 75)}")   # True
    print(f"  B76.5 {{76,77}} settles YES? {bracket_settles_yes(cli, 76, 77)}")   # False
    print(f"  T74 greater   settles YES? {threshold_settles_yes(cli, 74, kind='greater')}")  # True  (75 >= 75)
    print(f"  T76 less      settles YES? {threshold_settles_yes(cli, 76, kind='less')}")     # True  (75 <= 75)

    print("\n=== Quantiles → (mu, sigma) ===")
    mu2, sigma2 = mu_sigma_from_quantiles(71.0, 74.0, 77.0)
    print(f"  quantiles (71, 74, 77) → mu={mu2:.2f}  sigma={sigma2:.4f}")
