#!/usr/bin/env python3
"""Equity curve drawdown analysis with response recommendations.

Analyzes an equity curve to identify all drawdown periods, calculate
maximum drawdown statistics, and provide actionable recommendations
based on the current drawdown state.

Usage:
    python scripts/drawdown_analyzer.py --demo
    python scripts/drawdown_analyzer.py --equity equity_data.json

Dependencies:
    uv pip install numpy

Environment Variables:
    None required.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Optional

import numpy as np


# ── Data Models ─────────────────────────────────────────────────────
@dataclass
class DrawdownPeriod:
    """A single drawdown period from peak to recovery."""
    start_index: int
    trough_index: int
    recovery_index: Optional[int]  # None if not yet recovered
    peak_value: float
    trough_value: float
    depth: float  # As positive fraction (0.10 = 10%)
    duration_to_trough: int  # Periods from start to trough
    recovery_duration: Optional[int]  # Periods from trough to recovery
    total_duration: Optional[int]  # Periods from start to recovery


@dataclass
class DrawdownSummary:
    """Summary statistics for all drawdowns in an equity curve."""
    max_drawdown: float
    max_drawdown_period: Optional[DrawdownPeriod]
    current_drawdown: float
    current_drawdown_start: Optional[int]
    total_time_underwater: int
    longest_underwater: int
    num_drawdowns: int
    avg_drawdown_depth: float
    avg_recovery_time: float
    all_periods: list[DrawdownPeriod]


# ── Core Analysis ───────────────────────────────────────────────────
def find_drawdown_periods(
    equity: np.ndarray, min_depth: float = 0.01
) -> list[DrawdownPeriod]:
    """Identify all drawdown periods in an equity curve.

    Args:
        equity: Array of equity values over time.
        min_depth: Minimum drawdown depth to record (default 1%).

    Returns:
        List of DrawdownPeriod objects sorted by start index.
    """
    if len(equity) < 2:
        return []

    periods: list[DrawdownPeriod] = []
    peak = equity[0]
    peak_index = 0
    in_drawdown = False
    dd_start = 0
    trough = equity[0]
    trough_index = 0

    for i in range(len(equity)):
        if equity[i] >= peak:
            # New high or recovery
            if in_drawdown:
                depth = (peak - trough) / peak if peak > 0 else 0.0
                if depth >= min_depth:
                    periods.append(DrawdownPeriod(
                        start_index=dd_start,
                        trough_index=trough_index,
                        recovery_index=i,
                        peak_value=peak,
                        trough_value=trough,
                        depth=depth,
                        duration_to_trough=trough_index - dd_start,
                        recovery_duration=i - trough_index,
                        total_duration=i - dd_start,
                    ))
                in_drawdown = False
            peak = equity[i]
            peak_index = i
            trough = equity[i]
            trough_index = i
        else:
            if not in_drawdown:
                in_drawdown = True
                dd_start = peak_index
                trough = equity[i]
                trough_index = i
            if equity[i] < trough:
                trough = equity[i]
                trough_index = i

    # Handle open drawdown (not yet recovered)
    if in_drawdown:
        depth = (peak - trough) / peak if peak > 0 else 0.0
        if depth >= min_depth:
            periods.append(DrawdownPeriod(
                start_index=dd_start,
                trough_index=trough_index,
                recovery_index=None,
                peak_value=peak,
                trough_value=trough,
                depth=depth,
                duration_to_trough=trough_index - dd_start,
                recovery_duration=None,
                total_duration=None,
            ))

    return periods


def analyze_drawdowns(equity: np.ndarray) -> DrawdownSummary:
    """Comprehensive drawdown analysis of an equity curve.

    Args:
        equity: Array of equity values over time.

    Returns:
        DrawdownSummary with all statistics.
    """
    periods = find_drawdown_periods(equity)

    # Maximum drawdown
    max_dd = 0.0
    max_dd_period: Optional[DrawdownPeriod] = None
    for p in periods:
        if p.depth > max_dd:
            max_dd = p.depth
            max_dd_period = p

    # Current drawdown
    peak = np.max(equity)
    current = equity[-1]
    current_dd = (peak - current) / peak if peak > 0 else 0.0

    current_dd_start: Optional[int] = None
    if current_dd > 0.001:
        # Find when the current drawdown started
        peak_idx = int(np.argmax(equity))
        current_dd_start = peak_idx

    # Time underwater
    peaks = np.maximum.accumulate(equity)
    underwater = peaks > equity
    total_underwater = int(np.sum(underwater))

    # Longest consecutive underwater period
    longest_uw = 0
    current_uw = 0
    for uw in underwater:
        if uw:
            current_uw += 1
            longest_uw = max(longest_uw, current_uw)
        else:
            current_uw = 0

    # Average drawdown depth
    avg_depth = np.mean([p.depth for p in periods]) if periods else 0.0

    # Average recovery time (only for recovered drawdowns)
    recovered = [p for p in periods if p.recovery_duration is not None]
    avg_recovery = (
        np.mean([p.recovery_duration for p in recovered]) if recovered else 0.0
    )

    return DrawdownSummary(
        max_drawdown=max_dd,
        max_drawdown_period=max_dd_period,
        current_drawdown=current_dd,
        current_drawdown_start=current_dd_start,
        total_time_underwater=total_underwater,
        longest_underwater=longest_uw,
        num_drawdowns=len(periods),
        avg_drawdown_depth=float(avg_depth),
        avg_recovery_time=float(avg_recovery),
        all_periods=periods,
    )


def recovery_required(drawdown: float) -> float:
    """Calculate gain needed to recover from a drawdown.

    Args:
        drawdown: Drawdown as positive fraction (0.20 = 20%).

    Returns:
        Required gain as positive fraction.
    """
    if drawdown >= 1.0:
        return float("inf")
    if drawdown <= 0.0:
        return 0.0
    return drawdown / (1.0 - drawdown)


def drawdown_response(drawdown: float) -> tuple[str, str, str]:
    """Determine the appropriate response for a given drawdown level.

    Returns:
        Tuple of (level, status_color, recommendation).
    """
    if drawdown < 0.05:
        return ("Normal", "\033[92m", "Continue trading at full size.")
    elif drawdown < 0.10:
        return ("Caution", "\033[93m", "Reduce position sizes by 25-50%. Review recent trades for errors.")
    elif drawdown < 0.15:
        return ("Warning", "\033[91m", "Minimum position sizes only. Review strategy edge and market regime.")
    elif drawdown < 0.20:
        return ("Critical", "\033[91m", "Halt new trades. Manage existing positions only. Mandatory review.")
    else:
        return (
            "Emergency",
            "\033[91m",
            "Full stop. Close positions systematically. 48-72 hour break. "
            "Complete strategy review before resuming.",
        )


# ── Output Formatting ──────────────────────────────────────────────
def print_separator(char: str = "=", width: int = 70) -> None:
    """Print a separator line."""
    print(char * width)


def print_summary(summary: DrawdownSummary, equity: np.ndarray) -> None:
    """Print formatted drawdown analysis results."""
    reset = "\033[0m"

    print()
    print_separator()
    print("  DRAWDOWN ANALYSIS")
    print_separator()

    print(f"\n  Equity Curve: {len(equity)} periods")
    print(f"  Start Value:  {equity[0]:.2f}")
    print(f"  End Value:    {equity[-1]:.2f}")
    print(f"  Peak Value:   {np.max(equity):.2f}")
    print(f"  Total Return: {(equity[-1] / equity[0] - 1) * 100:+.1f}%")

    # ── Maximum Drawdown ────────────────────────────────────────
    print()
    print_separator("-")
    print("  MAXIMUM DRAWDOWN")
    print_separator("-")

    print(f"  Max Drawdown: {summary.max_drawdown:.1%}")
    print(f"  Recovery Required: +{recovery_required(summary.max_drawdown):.1%}")

    if summary.max_drawdown_period:
        p = summary.max_drawdown_period
        print(f"  Peak Index: {p.start_index}")
        print(f"  Trough Index: {p.trough_index}")
        print(f"  Peak Value: {p.peak_value:.2f}")
        print(f"  Trough Value: {p.trough_value:.2f}")
        print(f"  Duration to Trough: {p.duration_to_trough} periods")
        if p.recovery_index is not None:
            print(f"  Recovery Index: {p.recovery_index}")
            print(f"  Recovery Duration: {p.recovery_duration} periods")
            print(f"  Total Duration: {p.total_duration} periods")
        else:
            print("  Recovery: NOT YET RECOVERED")

    # ── Current Status ──────────────────────────────────────────
    print()
    print_separator("-")
    print("  CURRENT STATUS")
    print_separator("-")

    level, color, recommendation = drawdown_response(summary.current_drawdown)
    print(f"  Current Drawdown: {color}{summary.current_drawdown:.1%}{reset}")
    print(f"  Status Level: {color}{level}{reset}")
    print(f"  Recovery Needed: +{recovery_required(summary.current_drawdown):.1%}")
    print(f"  Recommendation: {recommendation}")

    if summary.current_drawdown_start is not None and summary.current_drawdown > 0.001:
        periods_in_dd = len(equity) - 1 - summary.current_drawdown_start
        print(f"  Periods in Current Drawdown: {periods_in_dd}")

    # ── Underwater Analysis ─────────────────────────────────────
    print()
    print_separator("-")
    print("  UNDERWATER ANALYSIS")
    print_separator("-")

    total_periods = len(equity)
    uw_pct = summary.total_time_underwater / total_periods * 100 if total_periods > 0 else 0
    print(f"  Total Time Underwater: {summary.total_time_underwater} periods ({uw_pct:.1f}%)")
    print(f"  Longest Underwater: {summary.longest_underwater} periods")
    print(f"  Number of Drawdowns (>1%): {summary.num_drawdowns}")
    print(f"  Average Drawdown Depth: {summary.avg_drawdown_depth:.1%}")
    if summary.avg_recovery_time > 0:
        print(f"  Average Recovery Time: {summary.avg_recovery_time:.1f} periods")

    # ── All Drawdown Periods ────────────────────────────────────
    if summary.all_periods:
        print()
        print_separator("-")
        print("  ALL DRAWDOWN PERIODS")
        print_separator("-")

        print(f"  {'#':>3s}  {'Depth':>7s}  {'Peak':>8s}  {'Trough':>8s}  {'To Trough':>10s}  {'Recovery':>10s}  {'Status':<12s}")
        print("  " + "-" * 65)

        for i, p in enumerate(sorted(summary.all_periods, key=lambda x: -x.depth), 1):
            recovery_str = (
                f"{p.recovery_duration}" if p.recovery_duration is not None else "OPEN"
            )
            status_str = "Recovered" if p.recovery_index is not None else "ACTIVE"
            print(
                f"  {i:>3d}  {p.depth:>6.1%}  {p.peak_value:>8.2f}  {p.trough_value:>8.2f}  "
                f"{p.duration_to_trough:>10d}  {recovery_str:>10s}  {status_str:<12s}"
            )

    # ── Recovery Table ──────────────────────────────────────────
    print()
    print_separator("-")
    print("  RECOVERY REFERENCE TABLE")
    print_separator("-")

    print(f"  {'Drawdown':>10s}  {'Gain Needed':>12s}  {'At 1%/day':>10s}")
    print("  " + "-" * 36)
    for dd_pct in [5, 10, 15, 20, 25, 30, 40, 50]:
        dd = dd_pct / 100
        gain = recovery_required(dd)
        days = 0
        cumulative = 1.0
        target = 1.0 / (1.0 - dd)
        while cumulative < target and days < 1000:
            cumulative *= 1.01
            days += 1
        print(f"  {dd:>9.0%}  {gain:>11.1%}  {days:>8d} days")

    print()
    print_separator()


# ── Demo Data ───────────────────────────────────────────────────────
def generate_demo_equity(
    start: float = 100.0,
    periods: int = 200,
    seed: int = 42,
) -> np.ndarray:
    """Generate a realistic equity curve with multiple drawdowns.

    Creates an equity curve that trends upward with realistic drawdown
    characteristics including:
    - A moderate drawdown early on (~8%)
    - A significant drawdown in the middle (~18%)
    - A recovery followed by a mild current drawdown (~6%)

    Args:
        start: Starting equity value.
        periods: Number of periods to generate.
        seed: Random seed for reproducibility.

    Returns:
        NumPy array of equity values.
    """
    rng = np.random.default_rng(seed)

    equity = [start]
    current = start

    # Phase 1: Mild uptrend (periods 0-40)
    for _ in range(40):
        ret = rng.normal(0.003, 0.015)
        current *= (1 + ret)
        equity.append(current)

    # Phase 2: Moderate drawdown (periods 41-60)
    for _ in range(20):
        ret = rng.normal(-0.004, 0.012)
        current *= (1 + ret)
        equity.append(current)

    # Phase 3: Recovery and new highs (periods 61-100)
    for _ in range(40):
        ret = rng.normal(0.004, 0.014)
        current *= (1 + ret)
        equity.append(current)

    # Phase 4: Significant drawdown (periods 101-130)
    for _ in range(30):
        ret = rng.normal(-0.006, 0.015)
        current *= (1 + ret)
        equity.append(current)

    # Phase 5: Slow recovery (periods 131-170)
    for _ in range(40):
        ret = rng.normal(0.005, 0.013)
        current *= (1 + ret)
        equity.append(current)

    # Phase 6: Current mild drawdown (periods 171-200)
    for _ in range(periods - 171):
        ret = rng.normal(-0.001, 0.012)
        current *= (1 + ret)
        equity.append(current)

    return np.array(equity[:periods])


def load_equity_from_file(filepath: str) -> np.ndarray:
    """Load equity curve from a JSON file.

    Expected format: {"equity": [100.0, 101.5, 99.8, ...]}
    Or a plain JSON array: [100.0, 101.5, 99.8, ...]
    """
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading equity file: {e}")
        sys.exit(1)

    if isinstance(data, list):
        return np.array(data, dtype=float)
    elif isinstance(data, dict) and "equity" in data:
        return np.array(data["equity"], dtype=float)
    else:
        print("Expected JSON array or object with 'equity' key")
        sys.exit(1)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point for the drawdown analyzer."""
    parser = argparse.ArgumentParser(
        description="Equity curve drawdown analysis — identify and analyze drawdown periods"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with generated demo equity curve",
    )
    parser.add_argument(
        "--equity",
        type=str,
        help="Path to JSON file with equity curve data",
    )
    parser.add_argument(
        "--min-depth",
        type=float,
        default=0.02,
        help="Minimum drawdown depth to report (default: 0.02 = 2%%)",
    )
    args = parser.parse_args()

    if args.demo:
        equity = generate_demo_equity()
        print("\n  [Running with generated demo equity curve]")
    elif args.equity:
        equity = load_equity_from_file(args.equity)
    else:
        parser.print_help()
        print("\nProvide --demo or --equity <file.json>")
        sys.exit(1)

    summary = analyze_drawdowns(equity)
    # Re-run with custom min_depth if specified
    if args.min_depth != 0.01:
        summary.all_periods = find_drawdown_periods(equity, min_depth=args.min_depth)
        summary.num_drawdowns = len(summary.all_periods)
        if summary.all_periods:
            summary.avg_drawdown_depth = float(
                np.mean([p.depth for p in summary.all_periods])
            )

    print_summary(summary, equity)


if __name__ == "__main__":
    main()
