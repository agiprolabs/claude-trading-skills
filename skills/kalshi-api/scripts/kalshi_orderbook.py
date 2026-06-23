#!/usr/bin/env python3
"""Kalshi order-book and fee helpers.

Pure functions — no network, no API keys, no third-party dependencies.
Encodes the YES/NO bid-only convention that is easy to get backwards.

Run directly for a worked example:
    python3 kalshi_orderbook.py
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Order-book conventions
# ---------------------------------------------------------------------------
# On Kalshi, `yes` and `no` are both RESTING BID ladders — there is no
# separate ask side. To take the opposing side, you lift the other bid.
#
#   no_ask  = 1 - best_yes_bid   (cost to buy NO immediately)
#   yes_ask = 1 - best_no_bid    (cost to buy YES immediately)
#
# Getting this backwards silently inverts every signal.
# ---------------------------------------------------------------------------

def no_ask(best_yes_bid: float) -> float:
    """Price to TAKE the NO side now (lift the YES bids).
    no_ask = 1 - best_yes_bid.
    """
    return 1.0 - best_yes_bid


def yes_ask(best_no_bid: float) -> float:
    """Price to TAKE the YES side now (lift the NO bids).
    yes_ask = 1 - best_no_bid.
    """
    return 1.0 - best_no_bid


def p_yes_mid(best_yes_bid: float, best_no_bid: float) -> float:
    """Mid implied P(YES) from the two bid ladders.
    mid = (yes_bid + (1 - no_bid)) / 2
    """
    return (best_yes_bid + (1.0 - best_no_bid)) / 2.0


def overround(p_yes_by_bracket: list[float]) -> float:
    """Sum of P(YES) across an event's mutually-exclusive brackets.

    Fair market = 1.0.
    > 1.0 means the market overprices the set in aggregate (favorite-longshot bias).
    """
    return float(sum(p_yes_by_bracket))


# ---------------------------------------------------------------------------
# Kalshi fee
# ---------------------------------------------------------------------------

def kalshi_fee(price: float, contracts: float) -> float:
    """Approximate Kalshi taker fee (~7% of max profit per contract).

    price     -- entry price in dollars [0.0, 1.0]
    contracts -- number of contracts

    Returns the fee in dollars. Maker (resting limit) orders pay no fee.
    Verify the exact rate at https://docs.kalshi.com before sizing.
    """
    max_profit_per_contract = 1.0 - price
    return 0.07 * max_profit_per_contract * contracts


# ---------------------------------------------------------------------------
# Orderbook normalization
# ---------------------------------------------------------------------------

def normalize_price(price: float) -> float:
    """Convert integer-cent prices to dollar floats.

    Kalshi returns prices in two formats depending on the API tier:
      - dollar float: 0.42  (already correct)
      - integer cents: 42   (divide by 100)

    Normalize before computing mid or fee.
    """
    return price / 100.0 if price > 1.0 else price


def best_bid(ladder: list[list[float]], normalize: bool = True) -> float | None:
    """Return the best (highest) bid price from a resting bid ladder.

    ladder   -- list of [price, size] pairs as returned by the orderbook endpoint
    normalize -- if True, auto-convert integer-cent prices to dollar floats
    """
    if not ladder:
        return None
    price = max(row[0] for row in ladder)
    return normalize_price(price) if normalize else price


# ---------------------------------------------------------------------------
# Worked example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Kalshi order-book helpers — worked example ===\n")

    # Hypothetical book: YES bids at 0.30, NO bids at 0.66
    yb, nb = 0.30, 0.66
    print(f"best_yes_bid = {yb}  best_no_bid = {nb}")
    print(f"  no_ask     = {no_ask(yb):.2f}   (cost to buy NO immediately)")
    print(f"  yes_ask    = {yes_ask(nb):.2f}   (cost to buy YES immediately)")
    print(f"  P(YES) mid = {p_yes_mid(yb, nb):.3f}")

    print()

    # Fee example
    price, contracts = 0.50, 100.0
    print(f"Taker fee on {contracts:.0f} contracts @ ${price:.2f}: ${kalshi_fee(price, contracts):.2f}")

    print()

    # Overround: 5 brackets of an event
    ps = [0.08, 0.18, 0.30, 0.25, 0.12]
    print(f"Bracket P(YES) values: {ps}")
    print(f"Overround (these 5): {overround(ps):.3f}  (1.0 = fair)")

    print()

    # Normalization
    ladder_cents = [[75, 100], [73, 250]]    # integer-cent prices
    ladder_float = [[0.75, 100], [0.73, 250]]  # dollar-float prices
    print(f"Integer-cent ladder best bid: {best_bid(ladder_cents):.2f} (auto-normalized)")
    print(f"Dollar-float ladder best bid: {best_bid(ladder_float):.2f}")
