#!/usr/bin/env python3
"""Estimate Kelly criterion parameters from a list of trade P&L values.

Computes win rate, payoff ratio, edge, confidence intervals, rolling
stability analysis, and recommends an appropriate Kelly fraction.

Usage:
    # Demo mode with synthetic trades:
    python scripts/kelly_from_trades.py

    # Or provide trades as comma-separated P&L values:
    TRADES="0.5,-0.3,0.8,-0.2,0.4,-0.35,1.2,-0.25" python scripts/kelly_from_trades.py

Dependencies:
    uv pip install numpy

Environment Variables:
    TRADES: Comma-separated P&L values (optional; uses demo data if not set).
    DEMO_SEED: Random seed for demo data generation (default: 42).
    DEMO_COUNT: Number of synthetic trades in demo mode (default: 100).
"""

import math
import os
import sys
from typing import Optional

try:
    import numpy as np
except ImportError:
    print("numpy is required. Install with: uv pip install numpy")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────

TRADES_ENV = os.getenv("TRADES", "")
DEMO_SEED = int(os.getenv("DEMO_SEED", "42"))
DEMO_COUNT = int(os.getenv("DEMO_COUNT", "100"))

ROLLING_WINDOW = 30  # trades per rolling window


# ── Data Generation ─────────────────────────────────────────────────


def generate_demo_trades(count: int = 100, seed: int = 42) -> list[float]:
    """Generate synthetic trade P&L data for demonstration.

    Simulates a strategy with ~55% win rate and ~1.5:1 payoff ratio,
    plus some noise and occasional outliers.

    Args:
        count: Number of trades to generate.
        seed: Random seed for reproducibility.

    Returns:
        List of P&L values (positive = win, negative = loss).
    """
    rng = np.random.default_rng(seed)
    trades = []
    for _ in range(count):
        if rng.random() < 0.55:
            # Winner: base 0.4 SOL, with some variance and occasional big win
            pnl = rng.exponential(0.4)
            if rng.random() < 0.05:  # 5% chance of big winner
                pnl *= 3.0
            trades.append(round(pnl, 4))
        else:
            # Loser: base 0.3 SOL, less variance (stops hit more consistently)
            pnl = rng.exponential(0.25) + 0.05
            trades.append(round(-pnl, 4))
    return trades


def parse_trades(trades_str: str) -> list[float]:
    """Parse comma-separated trade P&L string into list of floats.

    Args:
        trades_str: Comma-separated P&L values.

    Returns:
        List of float P&L values.

    Raises:
        ValueError: If any value cannot be parsed as float.
    """
    values = []
    for part in trades_str.split(","):
        part = part.strip()
        if part:
            values.append(float(part))
    return values


# ── Statistics ──────────────────────────────────────────────────────


def wilson_interval(wins: int, total: int,
                    z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a proportion.

    Args:
        wins: Number of successes.
        total: Total trials.
        z: Z-score (1.96 for 95% CI, 1.645 for 90% CI).

    Returns:
        (lower_bound, upper_bound) of the proportion.
    """
    if total == 0:
        return (0.0, 1.0)
    p = wins / total
    denominator = 1.0 + z ** 2 / total
    centre = p + z ** 2 / (2.0 * total)
    spread = z * math.sqrt(
        (p * (1.0 - p) + z ** 2 / (4.0 * total)) / total
    )
    lower = (centre - spread) / denominator
    upper = (centre + spread) / denominator
    return (max(0.0, lower), min(1.0, upper))


def compute_trade_stats(trades: list[float]) -> dict:
    """Compute trading statistics from P&L data.

    Args:
        trades: List of P&L values.

    Returns:
        Dictionary with win_rate, payoff_ratio, edge, kelly, and more.
    """
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    flat = [t for t in trades if t == 0]

    total = len(trades)
    n_wins = len(wins)
    n_losses = len(losses)

    if n_wins == 0 or n_losses == 0:
        return {
            "total": total,
            "wins": n_wins,
            "losses": n_losses,
            "flat": len(flat),
            "win_rate": n_wins / total if total > 0 else 0.0,
            "avg_win": float(np.mean(wins)) if wins else 0.0,
            "avg_loss": abs(float(np.mean(losses))) if losses else 0.0,
            "payoff_ratio": 0.0,
            "edge": 0.0 if n_wins == 0 else float("inf"),
            "kelly_full": 0.0,
            "total_pnl": sum(trades),
            "error": "Need both wins and losses to compute Kelly.",
        }

    win_rate = n_wins / total
    avg_win = float(np.mean(wins))
    avg_loss = abs(float(np.mean(losses)))
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")
    edge_val = win_rate * payoff_ratio - (1.0 - win_rate)
    kelly_full = edge_val / payoff_ratio if payoff_ratio > 0 else 0.0

    # Confidence intervals
    ci_lower, ci_upper = wilson_interval(n_wins, total)
    conservative_edge = ci_lower * payoff_ratio - (1.0 - ci_lower)
    conservative_kelly = (
        conservative_edge / payoff_ratio if conservative_edge > 0 else 0.0
    )

    return {
        "total": total,
        "wins": n_wins,
        "losses": n_losses,
        "flat": len(flat),
        "win_rate": win_rate,
        "win_rate_ci": (ci_lower, ci_upper),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "median_win": float(np.median(wins)),
        "median_loss": abs(float(np.median(losses))),
        "max_win": max(wins),
        "max_loss": abs(min(losses)),
        "payoff_ratio": payoff_ratio,
        "edge": edge_val,
        "kelly_full": kelly_full,
        "conservative_kelly": conservative_kelly,
        "total_pnl": sum(trades),
        "avg_pnl": float(np.mean(trades)),
        "std_pnl": float(np.std(trades)),
    }


def rolling_kelly(trades: list[float],
                  window: int = 30) -> list[Optional[float]]:
    """Compute Kelly fraction using a rolling window.

    Args:
        trades: Full list of P&L values.
        window: Number of trades per window.

    Returns:
        List of Kelly fractions (None where insufficient data).
    """
    results: list[Optional[float]] = []
    for i in range(len(trades)):
        if i < window - 1:
            results.append(None)
            continue
        window_trades = trades[i - window + 1: i + 1]
        stats = compute_trade_stats(window_trades)
        if "error" in stats:
            results.append(None)
        else:
            results.append(stats["kelly_full"])
    return results


def kelly_stability_score(rolling_values: list[Optional[float]]) -> float:
    """Compute stability score for rolling Kelly values.

    A score of 1.0 means perfectly stable. Lower values indicate
    more volatility in the Kelly estimate, suggesting less reliable edge.

    Args:
        rolling_values: Output from rolling_kelly().

    Returns:
        Stability score between 0 and 1.
    """
    valid = [v for v in rolling_values if v is not None]
    if len(valid) < 5:
        return 0.0
    arr = np.array(valid)
    mean_val = np.mean(arr)
    if mean_val == 0:
        return 0.0
    cv = float(np.std(arr) / abs(mean_val))  # coefficient of variation
    # Map CV to 0-1 score: CV=0 → 1.0, CV=2 → 0.0
    return max(0.0, min(1.0, 1.0 - cv / 2.0))


def recommend_fraction(stats: dict, stability: float) -> tuple[float, str]:
    """Recommend a Kelly fraction based on stats and stability.

    Args:
        stats: Output from compute_trade_stats().
        stability: Output from kelly_stability_score().

    Returns:
        (recommended_fraction, explanation_string)
    """
    total = stats["total"]
    edge_val = stats["edge"]

    if edge_val <= 0:
        return (0.0, "Negative or zero edge — do not use Kelly sizing.")

    reasons = []

    # Sample size factor
    if total < 30:
        size_frac = 0.10
        reasons.append(f"small sample ({total} trades)")
    elif total < 50:
        size_frac = 0.15
        reasons.append(f"limited sample ({total} trades)")
    elif total < 100:
        size_frac = 0.25
        reasons.append(f"moderate sample ({total} trades)")
    elif total < 200:
        size_frac = 0.33
        reasons.append(f"good sample ({total} trades)")
    else:
        size_frac = 0.50
        reasons.append(f"large sample ({total} trades)")

    # Stability factor
    if stability < 0.3:
        stab_frac = 0.10
        reasons.append(f"unstable Kelly (score {stability:.2f})")
    elif stability < 0.5:
        stab_frac = 0.20
        reasons.append(f"moderately stable (score {stability:.2f})")
    elif stability < 0.7:
        stab_frac = 0.30
        reasons.append(f"fairly stable (score {stability:.2f})")
    else:
        stab_frac = 0.50
        reasons.append(f"stable Kelly (score {stability:.2f})")

    # Edge plausibility
    if edge_val > 0.30:
        edge_frac = 0.15
        reasons.append("suspiciously high edge")
    elif edge_val > 0.15:
        edge_frac = 0.30
        reasons.append("high edge (verify)")
    else:
        edge_frac = 0.50
        reasons.append("plausible edge level")

    # Take the minimum (most conservative)
    rec = min(size_frac, stab_frac, edge_frac)
    reason_str = "; ".join(reasons)
    return (rec, reason_str)


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
    """Run Kelly analysis on trade data and print report."""
    # Load or generate trades
    if TRADES_ENV:
        try:
            trades = parse_trades(TRADES_ENV)
        except ValueError as exc:
            print(f"Error parsing TRADES: {exc}")
            sys.exit(1)
        data_source = "user-provided"
    else:
        trades = generate_demo_trades(DEMO_COUNT, DEMO_SEED)
        data_source = f"demo (seed={DEMO_SEED}, count={DEMO_COUNT})"

    if len(trades) < 5:
        print("Need at least 5 trades for analysis.")
        sys.exit(1)

    # Compute stats
    stats = compute_trade_stats(trades)

    # Rolling analysis
    rolling = rolling_kelly(trades, ROLLING_WINDOW)
    stability = kelly_stability_score(rolling)

    # ── Report ──────────────────────────────────────────────────
    print_header("KELLY FROM TRADES — ANALYSIS REPORT")
    print(f"  Data source:   {data_source}")
    print(f"  Total trades:  {stats['total']}")

    # ── Basic Stats ─────────────────────────────────────────────
    print_header("TRADE STATISTICS")
    print(f"  Wins:          {stats['wins']} ({stats['win_rate']:.1%})")
    print(f"  Losses:        {stats['losses']} ({1 - stats['win_rate']:.1%})")
    if stats["flat"] > 0:
        print(f"  Flat:          {stats['flat']}")
    print(f"  Total P&L:     {stats['total_pnl']:+.4f}")
    print(f"  Avg P&L:       {stats['avg_pnl']:+.4f}")
    print(f"  Std P&L:       {stats['std_pnl']:.4f}")

    if "error" in stats:
        print(f"\n  {stats['error']}")
        print_separator()
        return

    print(f"\n  Avg Win:       {stats['avg_win']:.4f}")
    print(f"  Avg Loss:      {stats['avg_loss']:.4f}")
    print(f"  Median Win:    {stats['median_win']:.4f}")
    print(f"  Median Loss:   {stats['median_loss']:.4f}")
    print(f"  Max Win:       {stats['max_win']:.4f}")
    print(f"  Max Loss:      {stats['max_loss']:.4f}")
    print(f"  Payoff Ratio:  {stats['payoff_ratio']:.3f}")

    # ── Edge & Kelly ────────────────────────────────────────────
    print_header("EDGE & KELLY ANALYSIS")
    print(f"  Edge:                  {stats['edge']:.4f}")

    # Edge classification
    if stats["edge"] < 0:
        edge_class = "NEGATIVE — do not trade"
    elif stats["edge"] < 0.02:
        edge_class = "NO MEANINGFUL EDGE"
    elif stats["edge"] < 0.05:
        edge_class = "WEAK"
    elif stats["edge"] < 0.10:
        edge_class = "MODERATE"
    elif stats["edge"] < 0.20:
        edge_class = "GOOD"
    elif stats["edge"] < 0.50:
        edge_class = "EXCELLENT (verify)"
    else:
        edge_class = "SUSPICIOUS"
    print(f"  Edge Class:            {edge_class}")

    print(f"\n  Full Kelly:            {stats['kelly_full']:.4f} ({stats['kelly_full']:.1%})")

    # Confidence intervals
    ci_lo, ci_hi = stats["win_rate_ci"]
    print(f"\n  Win Rate 95% CI:       [{ci_lo:.3f}, {ci_hi:.3f}]")
    print(f"  Conservative Kelly:    {stats['conservative_kelly']:.4f} "
          f"({stats['conservative_kelly']:.1%})  [using CI lower bound]")

    if stats["edge"] <= 0:
        print("\n  No positive edge. Kelly sizing not applicable.")
        print_separator()
        return

    # ── Fractional Kelly ────────────────────────────────────────
    print_header("FRACTIONAL KELLY OPTIONS")
    print(f"  {'Fraction':<14} {'Kelly %':<10} {'Notes'}")
    print(f"  {'--------':<14} {'-------':<10} {'-----'}")
    for alpha in [0.10, 0.25, 0.33, 0.50]:
        frac = stats["kelly_full"] * alpha
        note = ""
        if alpha == 0.10:
            note = "very conservative"
        elif alpha == 0.25:
            note = "standard conservative"
        elif alpha == 0.33:
            note = "moderate"
        elif alpha == 0.50:
            note = "aggressive (needs 100+ trades)"
        print(f"  {alpha:.2f}x Kelly    {frac:>8.2%}    {note}")

    conservative_half = stats["conservative_kelly"] * 0.50
    print(f"\n  Conservative 0.50x:  {conservative_half:>8.2%}  "
          f"[CI lower bound + half Kelly]")

    # ── Rolling Stability ───────────────────────────────────────
    print_header(f"ROLLING STABILITY (window = {ROLLING_WINDOW} trades)")

    valid_rolling = [v for v in rolling if v is not None]
    if len(valid_rolling) >= 3:
        arr = np.array(valid_rolling)
        print(f"  Rolling Kelly mean:    {np.mean(arr):.4f}")
        print(f"  Rolling Kelly std:     {np.std(arr):.4f}")
        print(f"  Rolling Kelly min:     {np.min(arr):.4f}")
        print(f"  Rolling Kelly max:     {np.max(arr):.4f}")
        print(f"  Stability score:       {stability:.3f} (0=unstable, 1=stable)")

        # Show a few rolling values
        n_show = min(8, len(valid_rolling))
        step = max(1, len(valid_rolling) // n_show)
        print(f"\n  Sample rolling Kelly (every {step} values):")
        for i in range(0, len(valid_rolling), step):
            trade_idx = ROLLING_WINDOW - 1 + i
            val = valid_rolling[i]
            bar_len = max(0, int(val * 100))
            bar = "#" * min(bar_len, 40)
            print(f"    Trade {trade_idx + 1:>4}: {val:>7.3f}  {bar}")

        # Check for trend
        if len(valid_rolling) >= 10:
            first_half = np.mean(arr[: len(arr) // 2])
            second_half = np.mean(arr[len(arr) // 2:])
            if second_half > first_half * 1.3:
                print("\n  TREND: Kelly is INCREASING over time. Verify that "
                      "edge improvement is real.")
            elif second_half < first_half * 0.7:
                print("\n  TREND: Kelly is DECREASING over time. Edge may be "
                      "deteriorating.")
            else:
                print("\n  TREND: Kelly is relatively stable over time.")
    else:
        print("  Insufficient data for rolling analysis "
              f"(need {ROLLING_WINDOW}+ trades).")
        print(f"  Stability score: {stability:.3f}")

    # ── Recommendation ──────────────────────────────────────────
    print_header("RECOMMENDATION")

    rec_frac, rec_reason = recommend_fraction(stats, stability)
    if rec_frac == 0:
        print(f"  {rec_reason}")
    else:
        rec_kelly = stats["kelly_full"] * rec_frac
        print(f"  Recommended fraction:  {rec_frac:.2f}x Kelly")
        print(f"  Effective Kelly:       {rec_kelly:.2%}")
        print(f"  Reasoning:             {rec_reason}")
        print()
        print(f"  For a 100 SOL account: {rec_kelly * 100:.2f} SOL per trade")
        print(f"  Hard cap reminder:     25 SOL (25% of 100 SOL)")

    print()
    print("  NOTE: This is a mathematical analysis, not financial advice.")
    print("  Always verify edge estimates with out-of-sample data.")
    print_separator()
    print()


if __name__ == "__main__":
    main()
