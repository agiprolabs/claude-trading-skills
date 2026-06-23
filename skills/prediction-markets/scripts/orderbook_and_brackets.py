#!/usr/bin/env python3
"""Pure functions for prediction-market microstructure and bracket pricing.

No network, no API keys, no third-party deps (uses the stdlib `math.erf` for the
normal CDF so it runs anywhere). These encode the conventions that are easy to get
backwards: the Kalshi YES/NO bid-only order book, the overround, the taker fee, and
the half-integer-corrected Gaussian bracket/threshold -> P(YES) map.

Run directly for a worked example:  python orderbook_and_brackets.py
"""
from __future__ import annotations
import math


# --------------------------------------------------------------------------- #
# Order-book conventions (Kalshi: `yes` and `no` are BOTH bid ladders)
# --------------------------------------------------------------------------- #
def no_ask(best_yes_bid: float) -> float:
    """Price to TAKE the NO side now = lift the YES bid. no_ask = 1 - best_yes_bid."""
    return 1.0 - best_yes_bid


def yes_ask(best_no_bid: float) -> float:
    """Price to TAKE the YES side now = lift the NO bid. yes_ask = 1 - best_no_bid."""
    return 1.0 - best_no_bid


def p_yes_mid(best_yes_bid: float, best_no_bid: float) -> float:
    """Mid implied P(YES) from the two bid ladders: (yes_bid + (1 - no_bid)) / 2."""
    return (best_yes_bid + (1.0 - best_no_bid)) / 2.0


def overround(p_yes_by_bracket: list[float]) -> float:
    """Sum of P(YES) across an event's mutually-exclusive brackets. Fair = 1.0;
    > 1.0 means the market is overpricing the set in aggregate (favorite-longshot)."""
    return float(sum(p_yes_by_bracket))


# --------------------------------------------------------------------------- #
# Kalshi fee
# --------------------------------------------------------------------------- #
def kalshi_taker_fee(price: float, contracts: float, rate: float = 0.07) -> float:
    """Kalshi taker fee in dollars: ceil(rate * C * p * (1 - p) * 100) / 100.
    Peaks at p = 0.50; ~0 at the wings. Maker fills are 0% (plus periodic rebates)."""
    return math.ceil(rate * contracts * price * (1.0 - price) * 100.0) / 100.0


# --------------------------------------------------------------------------- #
# Forecast -> P(YES)  (normal CDF with the mandatory half-integer correction)
# --------------------------------------------------------------------------- #
def _phi(x: float) -> float:
    """Standard normal CDF via the error function (stdlib only)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bracket_p_yes(floor_int: int, cap_int: int, mu: float, sigma: float) -> float:
    """P(YES) for a 2-degree, both-ends-inclusive bracket covering integers
    {floor_int, cap_int} (e.g. B74.5 -> floor=74, cap=75) under a forecast N(mu, sigma).

    P = Phi((cap + 0.5 - mu)/sigma) - Phi((floor - 0.5 - mu)/sigma)
    The +/-0.5 continuity correction is required because settlement is on integers.
    """
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    return _phi((cap_int + 0.5 - mu) / sigma) - _phi((floor_int - 0.5 - mu) / sigma)


def threshold_p_yes(strike_int: int, mu: float, sigma: float, *, kind: str) -> float:
    """P(YES) for a threshold market. `kind` MUST come from the API `strike_type`
    field (it is NOT inferable from the ticker).
        greater: 1 - Phi((T + 0.5 - mu)/sigma)
        less:        Phi((T - 0.5 - mu)/sigma)
    """
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    if kind == "greater":
        return 1.0 - _phi((strike_int + 0.5 - mu) / sigma)
    if kind == "less":
        return _phi((strike_int - 0.5 - mu) / sigma)
    raise ValueError(f"kind must be 'greater' or 'less', got {kind!r}")


def no_buy_ev(mkt_p_yes: float, true_p_yes: float, no_entry: float,
              contracts: float = 1.0, maker: bool = True) -> float:
    """Expected $ value of BUYING NO (the longshot-sell when mkt_p_yes is small).
    EV/contract (pre-fee) = (1 - true_p_yes) - no_entry; subtract taker fee if not maker.
    A cheap longshot overpriced by the market (true_p_yes < mkt_p_yes) gives +EV to the NO buyer.
    """
    ev = ((1.0 - true_p_yes) - no_entry) * contracts
    if not maker:
        ev -= kalshi_taker_fee(no_entry, contracts)
    return ev


if __name__ == "__main__":
    # Worked example: NYC high forecast N(mu=74.0, sigma=2.5)
    mu, sigma = 74.0, 2.5
    brackets = {  # ticker -> (floor, cap)
        "B70.5": (70, 71), "B72.5": (72, 73), "B74.5": (74, 75),
        "B76.5": (76, 77), "B78.5": (78, 79),
    }
    ps = {}
    for tk, (lo, hi) in brackets.items():
        ps[tk] = bracket_p_yes(lo, hi, mu, sigma)
        print(f"{tk}  {{{lo},{hi}}}  P(YES)={ps[tk]:.3f}")
    print(f"overround (these 5 of the full set) = {overround(list(ps.values())):.3f}")

    # Order-book conversion
    yb, nb = 0.30, 0.66
    print(f"\nbest_yes_bid={yb}  best_no_bid={nb}")
    print(f"  no_ask={no_ask(yb):.2f}  yes_ask={yes_ask(nb):.2f}  P(yes) mid={p_yes_mid(yb, nb):.3f}")

    # Fee + a longshot-sell EV (market prices a tail bracket at 0.08; true ~0.03)
    print(f"\ntaker fee on 100 @ $0.50 = ${kalshi_taker_fee(0.50, 100):.2f}")
    print(f"longshot-sell EV (maker, mkt 0.08, true 0.03, NO@0.92, 100ct) = "
          f"${no_buy_ev(0.08, 0.03, 0.92, 100, maker=True):.2f}")
