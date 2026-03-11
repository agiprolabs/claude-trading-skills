#!/usr/bin/env python3
"""Kelly criterion calculator for optimal position sizing.

Computes full and fractional Kelly fractions from win rate and payoff ratio,
with sensitivity analysis and growth rate estimates.

Usage:
    python scripts/kelly_calculator.py

    # Or with custom parameters via environment variables:
    WIN_RATE=0.55 AVG_WIN=1.5 AVG_LOSS=1.0 ACCOUNT_SIZE=100 python scripts/kelly_calculator.py

Dependencies:
    None (pure Python math)

Environment Variables:
    WIN_RATE: Probability of winning (0 to 1). Default: 0.55
    AVG_WIN: Average winning trade size. Default: 1.5
    AVG_LOSS: Average losing trade size (positive number). Default: 1.0
    ACCOUNT_SIZE: Total account size in SOL. Default: 100
"""

import math
import os
import sys
from typing import Optional


# ── Configuration ───────────────────────────────────────────────────

WIN_RATE = float(os.getenv("WIN_RATE", "0.55"))
AVG_WIN = float(os.getenv("AVG_WIN", "1.5"))
AVG_LOSS = float(os.getenv("AVG_LOSS", "1.0"))
ACCOUNT_SIZE = float(os.getenv("ACCOUNT_SIZE", "100"))

FRACTIONAL_KELLYS = [0.10, 0.25, 0.33, 0.50]
SENSITIVITY_OFFSETS = [-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10]


# ── Core Functions ──────────────────────────────────────────────────


def kelly_fraction(win_rate: float, payoff_ratio: float) -> float:
    """Calculate the full Kelly fraction.

    Args:
        win_rate: Probability of winning (0 < p < 1).
        payoff_ratio: Average win / average loss (b > 0).

    Returns:
        Optimal fraction of bankroll to bet. Can be negative
        (indicating negative edge — do not bet).
    """
    if payoff_ratio <= 0:
        return 0.0
    q = 1.0 - win_rate
    return (win_rate * payoff_ratio - q) / payoff_ratio


def edge(win_rate: float, payoff_ratio: float) -> float:
    """Calculate the edge (expected value per unit risked).

    Args:
        win_rate: Probability of winning.
        payoff_ratio: Average win / average loss.

    Returns:
        Edge value. Positive means profitable in expectation.
    """
    return win_rate * payoff_ratio - (1.0 - win_rate)


def growth_rate(win_rate: float, payoff_ratio: float, fraction: float) -> float:
    """Calculate expected log growth rate per trade.

    Args:
        win_rate: Probability of winning.
        payoff_ratio: Average win / average loss.
        fraction: Fraction of bankroll to bet.

    Returns:
        Expected log growth rate G(f). Higher is better.
        Returns -inf if fraction leads to ruin.
    """
    if fraction <= 0:
        return 0.0
    if fraction >= 1.0:
        return float("-inf")

    win_term = 1.0 + fraction * payoff_ratio
    lose_term = 1.0 - fraction

    if win_term <= 0 or lose_term <= 0:
        return float("-inf")

    q = 1.0 - win_rate
    return win_rate * math.log(win_term) + q * math.log(lose_term)


def approx_max_drawdown(fraction: float, num_trades: int = 100) -> float:
    """Estimate approximate maximum drawdown for a given Kelly fraction.

    Uses the heuristic that expected max drawdown scales roughly with
    the fraction size. This is a rough approximation.

    Args:
        fraction: Fraction of bankroll bet per trade.
        num_trades: Number of trades in the evaluation period.

    Returns:
        Estimated maximum drawdown as a fraction (e.g., 0.25 = 25%).
    """
    if fraction <= 0:
        return 0.0
    # Rough heuristic: max drawdown ~ 2 * fraction * sqrt(num_trades) / sqrt(num_trades)
    # Simplified: for full Kelly, expect ~50-80% drawdown over long horizons
    # Scale linearly with fraction relative to a baseline
    baseline_dd = 0.6  # ~60% max drawdown for full Kelly over 100 trades
    return min(fraction / 0.25 * baseline_dd * 0.25, 0.95)


def classify_edge(edge_value: float) -> str:
    """Classify the strength of a trading edge.

    Args:
        edge_value: The calculated edge.

    Returns:
        Human-readable classification string.
    """
    if edge_value < 0:
        return "NEGATIVE — do not trade"
    elif edge_value < 0.02:
        return "NO MEANINGFUL EDGE — costs likely exceed edge"
    elif edge_value < 0.05:
        return "WEAK — conservative fractions only"
    elif edge_value < 0.10:
        return "MODERATE — standard fractions appropriate"
    elif edge_value < 0.20:
        return "GOOD — well-calibrated strategy"
    elif edge_value < 0.50:
        return "EXCELLENT — verify not overfitting"
    else:
        return "SUSPICIOUS — almost certainly overfitting"


def validate_inputs(win_rate: float, avg_win: float, avg_loss: float,
                    account_size: float) -> Optional[str]:
    """Validate input parameters.

    Args:
        win_rate: Probability of winning.
        avg_win: Average win size.
        avg_loss: Average loss size.
        account_size: Account size.

    Returns:
        Error message string if invalid, None if valid.
    """
    if not 0.0 < win_rate < 1.0:
        return f"WIN_RATE must be between 0 and 1 (exclusive), got {win_rate}"
    if avg_win <= 0:
        return f"AVG_WIN must be positive, got {avg_win}"
    if avg_loss <= 0:
        return f"AVG_LOSS must be positive, got {avg_loss}"
    if account_size <= 0:
        return f"ACCOUNT_SIZE must be positive, got {account_size}"
    return None


def sensitivity_table(base_win_rate: float, payoff_ratio: float,
                      offsets: list[float]) -> list[dict]:
    """Compute Kelly fractions for various win rate offsets.

    Args:
        base_win_rate: The estimated win rate.
        payoff_ratio: Average win / average loss.
        offsets: List of win rate adjustments to test.

    Returns:
        List of dicts with win_rate, kelly, edge for each offset.
    """
    results = []
    for offset in offsets:
        wr = base_win_rate + offset
        if not 0.0 < wr < 1.0:
            continue
        k = kelly_fraction(wr, payoff_ratio)
        e = edge(wr, payoff_ratio)
        results.append({
            "offset": offset,
            "win_rate": wr,
            "kelly": k,
            "edge": e,
        })
    return results


def print_separator(char: str = "─", width: int = 65) -> None:
    """Print a visual separator line."""
    print(char * width)


def print_header(title: str) -> None:
    """Print a section header."""
    print()
    print_separator()
    print(f"  {title}")
    print_separator()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run the Kelly criterion calculator and print results."""
    # Validate
    error = validate_inputs(WIN_RATE, AVG_WIN, AVG_LOSS, ACCOUNT_SIZE)
    if error:
        print(f"Input error: {error}")
        sys.exit(1)

    payoff_ratio = AVG_WIN / AVG_LOSS
    e = edge(WIN_RATE, payoff_ratio)
    k_full = kelly_fraction(WIN_RATE, payoff_ratio)

    # ── Header ──────────────────────────────────────────────────
    print_header("KELLY CRITERION CALCULATOR")
    print(f"  Win Rate:      {WIN_RATE:.1%}")
    print(f"  Avg Win:       {AVG_WIN:.4f} SOL")
    print(f"  Avg Loss:      {AVG_LOSS:.4f} SOL")
    print(f"  Payoff Ratio:  {payoff_ratio:.2f} : 1")
    print(f"  Account Size:  {ACCOUNT_SIZE:.2f} SOL")
    print(f"  Edge:          {e:.4f}")
    print(f"  Edge Class:    {classify_edge(e)}")

    # ── Edge Check ──────────────────────────────────────────────
    if e <= 0:
        print()
        print("  ** No positive edge detected. Kelly fraction is zero. **")
        print("  ** Do not trade this strategy. **")
        print_separator()
        return

    # ── Full Kelly ──────────────────────────────────────────────
    print_header("FULL KELLY")
    g_full = growth_rate(WIN_RATE, payoff_ratio, k_full)
    print(f"  Kelly Fraction:     {k_full:.4f} ({k_full:.1%})")
    print(f"  Position Size:      {k_full * ACCOUNT_SIZE:.4f} SOL")
    print(f"  Growth Rate/Trade:  {g_full:.6f}")
    print()
    print("  ** Full Kelly is NOT recommended for live trading. **")
    print("  ** Use fractional Kelly below. **")

    # ── Fractional Kelly Table ──────────────────────────────────
    print_header("FRACTIONAL KELLY RECOMMENDATIONS")
    print(f"  {'Fraction':<12} {'Kelly %':<10} {'Size (SOL)':<12} "
          f"{'Growth Rate':<14} {'Est. Max DD':<12}")
    print(f"  {'--------':<12} {'-------':<10} {'----------':<12} "
          f"{'───────────':<14} {'───────────':<12}")

    for alpha in FRACTIONAL_KELLYS:
        frac = k_full * alpha
        pos_size = frac * ACCOUNT_SIZE
        g = growth_rate(WIN_RATE, payoff_ratio, frac)
        dd = approx_max_drawdown(frac)
        g_pct = (g / g_full * 100) if g_full > 0 else 0
        label = f"{alpha:.2f}x Kelly"
        print(f"  {label:<12} {frac:>8.2%}  {pos_size:>10.4f}  "
              f"  {g:.6f} ({g_pct:4.0f}%)  {dd:>8.1%}")

    # ── Sensitivity Analysis ────────────────────────────────────
    print_header("SENSITIVITY ANALYSIS (Win Rate Uncertainty)")
    print(f"  {'Win Rate':<12} {'Offset':<10} {'Edge':<10} "
          f"{'Full Kelly':<12} {'Half Kelly':<12}")
    print(f"  {'--------':<12} {'------':<10} {'----':<10} "
          f"{'──────────':<12} {'──────────':<12}")

    sens = sensitivity_table(WIN_RATE, payoff_ratio, SENSITIVITY_OFFSETS)
    for row in sens:
        marker = " <-- base" if row["offset"] == 0.0 else ""
        offset_str = f"{row['offset']:+.0%}"
        half_k = max(row["kelly"] * 0.5, 0)
        print(f"  {row['win_rate']:>8.1%}    {offset_str:>6}    "
              f"{row['edge']:>8.4f}  {row['kelly']:>10.2%}  "
              f"{half_k:>10.2%}{marker}")

    # ── Recommendation ──────────────────────────────────────────
    print_header("RECOMMENDATION")

    if k_full > 0.50:
        print("  WARNING: Full Kelly > 50%. Your edge estimate is likely")
        print("  inflated. Cap effective Kelly at 25% before applying fraction.")
        effective_kelly = min(k_full, 0.25)
    else:
        effective_kelly = k_full

    rec_fraction = 0.25  # default recommendation
    rec_reason = "default conservative"

    if e < 0.05:
        rec_fraction = 0.10
        rec_reason = "weak edge"
    elif e < 0.10:
        rec_fraction = 0.25
        rec_reason = "moderate edge"
    elif e < 0.20:
        rec_fraction = 0.33
        rec_reason = "good edge, but verify with more trades"
    else:
        rec_fraction = 0.25
        rec_reason = "high edge (suspicious — stay conservative)"

    rec_kelly = effective_kelly * rec_fraction
    rec_size = rec_kelly * ACCOUNT_SIZE
    rec_cap = min(rec_size, ACCOUNT_SIZE * 0.25)  # hard cap at 25%

    print(f"  Suggested fraction:  {rec_fraction:.2f}x Kelly ({rec_reason})")
    print(f"  Effective Kelly:     {rec_kelly:.2%}")
    print(f"  Position size:       {rec_cap:.4f} SOL per trade")
    print(f"  Max portfolio cap:   {ACCOUNT_SIZE * 0.25:.4f} SOL (25% hard cap)")
    print()
    print("  NOTE: This is a mathematical calculation, not financial advice.")
    print("  Always apply additional risk limits from your risk management rules.")
    print_separator()
    print()


if __name__ == "__main__":
    main()
