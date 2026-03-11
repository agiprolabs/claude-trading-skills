#!/usr/bin/env python3
"""Strategy evaluation scorecard.

Takes backtest results and scores a strategy across multiple dimensions,
providing an overall GO / REVIEW / NO-GO recommendation with specific
concerns and suggestions.

Usage:
    python scripts/strategy_scorecard.py --demo     # Run with 3 example strategies
    python scripts/strategy_scorecard.py             # Enter metrics interactively

Dependencies:
    None (standard library only)
"""

import math
import sys
from dataclasses import dataclass
from typing import Optional


# ── Data Structures ─────────────────────────────────────────────────


@dataclass
class BacktestResults:
    """Backtest results for a strategy."""

    strategy_name: str
    style: str  # "trend", "mean_reversion", "scalping", "breakout"
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float  # as decimal (0.45 = 45%)
    profit_factor: float
    trade_count: int
    avg_win_loss_ratio: float
    avg_trade_duration_bars: float
    is_oos: bool = False  # out-of-sample results?
    is_sharpe_degradation: Optional[float] = None  # OOS vs IS Sharpe drop


@dataclass
class ScoreComponent:
    """A single scored dimension."""

    name: str
    score: float  # 0 to 100
    weight: float
    grade: str  # A, B, C, D, F
    notes: list[str]


@dataclass
class Scorecard:
    """Complete strategy scorecard."""

    strategy_name: str
    components: list[ScoreComponent]
    overall_score: float
    recommendation: str  # GO, REVIEW, NO-GO
    concerns: list[str]
    suggestions: list[str]


# ── Scoring Functions ───────────────────────────────────────────────


def score_edge_quality(results: BacktestResults) -> ScoreComponent:
    """Score the strategy's edge quality based on Sharpe ratio.

    Args:
        results: Backtest results to evaluate.

    Returns:
        ScoreComponent with edge quality assessment.
    """
    sharpe = results.sharpe_ratio
    notes: list[str] = []

    if sharpe >= 2.0:
        score = 95.0
        notes.append(f"Sharpe {sharpe:.2f} — excellent risk-adjusted returns")
    elif sharpe >= 1.5:
        score = 80.0
        notes.append(f"Sharpe {sharpe:.2f} — strong risk-adjusted returns")
    elif sharpe >= 1.0:
        score = 65.0
        notes.append(f"Sharpe {sharpe:.2f} — acceptable risk-adjusted returns")
    elif sharpe >= 0.5:
        score = 40.0
        notes.append(f"Sharpe {sharpe:.2f} — marginal edge, may not survive costs")
    elif sharpe >= 0.0:
        score = 20.0
        notes.append(f"Sharpe {sharpe:.2f} — minimal edge detected")
    else:
        score = 0.0
        notes.append(f"Sharpe {sharpe:.2f} — negative risk-adjusted returns")

    # Bonus/penalty for profit factor
    if results.profit_factor >= 2.0:
        score = min(100, score + 10)
        notes.append(f"Profit factor {results.profit_factor:.2f} — strong")
    elif results.profit_factor < 1.2:
        score = max(0, score - 10)
        notes.append(f"Profit factor {results.profit_factor:.2f} — thin edge")

    grade = _score_to_grade(score)
    return ScoreComponent("Edge Quality", score, 0.30, grade, notes)


def score_risk_management(results: BacktestResults) -> ScoreComponent:
    """Score risk management based on drawdown characteristics.

    Args:
        results: Backtest results to evaluate.

    Returns:
        ScoreComponent with risk management assessment.
    """
    mdd = results.max_drawdown_pct
    notes: list[str] = []

    if mdd <= 10:
        score = 95.0
        notes.append(f"Max drawdown {mdd:.1f}% — excellent capital preservation")
    elif mdd <= 15:
        score = 80.0
        notes.append(f"Max drawdown {mdd:.1f}% — good capital preservation")
    elif mdd <= 20:
        score = 65.0
        notes.append(f"Max drawdown {mdd:.1f}% — acceptable but monitor closely")
    elif mdd <= 30:
        score = 40.0
        notes.append(f"Max drawdown {mdd:.1f}% — concerning, tighten risk controls")
    elif mdd <= 50:
        score = 20.0
        notes.append(f"Max drawdown {mdd:.1f}% — severe, strategy needs redesign")
    else:
        score = 0.0
        notes.append(f"Max drawdown {mdd:.1f}% — catastrophic, do not trade")

    # Return-to-drawdown ratio
    ret_dd = results.total_return_pct / mdd if mdd > 0 else 0
    if ret_dd >= 3.0:
        score = min(100, score + 10)
        notes.append(f"Return/MDD ratio {ret_dd:.1f} — excellent compensation for risk")
    elif ret_dd < 1.0:
        score = max(0, score - 10)
        notes.append(f"Return/MDD ratio {ret_dd:.1f} — returns don't justify the drawdown")

    grade = _score_to_grade(score)
    return ScoreComponent("Risk Management", score, 0.25, grade, notes)


def score_consistency(results: BacktestResults) -> ScoreComponent:
    """Score strategy consistency based on win rate and profit factor stability.

    Args:
        results: Backtest results to evaluate.

    Returns:
        ScoreComponent with consistency assessment.
    """
    notes: list[str] = []
    score = 50.0  # Start neutral

    style = results.style.lower()
    wr = results.win_rate
    awl = results.avg_win_loss_ratio

    # Win rate evaluation depends on style
    if style in ("trend", "trend_following", "breakout"):
        if wr >= 0.45:
            score += 20
            notes.append(f"Win rate {wr:.0%} — above average for trend/breakout")
        elif wr >= 0.35:
            score += 10
            notes.append(f"Win rate {wr:.0%} — typical for trend/breakout")
        elif wr >= 0.25:
            notes.append(f"Win rate {wr:.0%} — low but acceptable if avg win/loss high")
        else:
            score -= 20
            notes.append(f"Win rate {wr:.0%} — too low even for trend following")
    else:  # mean reversion, scalping
        if wr >= 0.60:
            score += 20
            notes.append(f"Win rate {wr:.0%} — strong for {style}")
        elif wr >= 0.50:
            score += 10
            notes.append(f"Win rate {wr:.0%} — adequate for {style}")
        elif wr >= 0.40:
            notes.append(f"Win rate {wr:.0%} — below expectations for {style}")
            score -= 10
        else:
            score -= 20
            notes.append(f"Win rate {wr:.0%} — too low for {style}")

    # Avg win/loss ratio
    if awl >= 3.0:
        score += 15
        notes.append(f"Avg win/loss {awl:.2f} — large winners compensate for losses")
    elif awl >= 2.0:
        score += 10
        notes.append(f"Avg win/loss {awl:.2f} — good asymmetry")
    elif awl >= 1.0:
        notes.append(f"Avg win/loss {awl:.2f} — balanced")
    else:
        score -= 15
        notes.append(f"Avg win/loss {awl:.2f} — losses larger than wins on average")

    # Expectancy check: (win_rate * avg_win) - ((1-win_rate) * 1.0) > 0
    expectancy = (wr * awl) - (1 - wr)
    if expectancy > 0.5:
        score += 10
        notes.append(f"Expectancy per trade {expectancy:.2f}R — positive edge confirmed")
    elif expectancy > 0:
        notes.append(f"Expectancy per trade {expectancy:.2f}R — thin but positive")
    else:
        score -= 20
        notes.append(f"Expectancy per trade {expectancy:.2f}R — NEGATIVE expected value")

    score = max(0, min(100, score))
    grade = _score_to_grade(score)
    return ScoreComponent("Consistency", score, 0.20, grade, notes)


def score_sample_size(results: BacktestResults) -> ScoreComponent:
    """Score the statistical adequacy of the trade sample.

    Args:
        results: Backtest results to evaluate.

    Returns:
        ScoreComponent with sample size assessment.
    """
    n = results.trade_count
    notes: list[str] = []

    if n >= 500:
        score = 95.0
        notes.append(f"{n} trades — large sample, high statistical confidence")
    elif n >= 200:
        score = 80.0
        notes.append(f"{n} trades — good sample size")
    elif n >= 100:
        score = 65.0
        notes.append(f"{n} trades — minimum acceptable sample")
    elif n >= 50:
        score = 40.0
        notes.append(f"{n} trades — borderline, results may not be reliable")
    elif n >= 20:
        score = 20.0
        notes.append(f"{n} trades — insufficient for statistical significance")
    else:
        score = 5.0
        notes.append(f"{n} trades — far too few trades, backtest is meaningless")

    # Margin of error estimate (simplified)
    if n > 0:
        wr = results.win_rate
        margin = 1.96 * math.sqrt(wr * (1 - wr) / n)
        notes.append(
            f"Win rate 95% CI: {max(0, wr - margin):.0%} to {min(1, wr + margin):.0%} "
            f"(±{margin:.1%})"
        )
        if margin > 0.10:
            score = max(0, score - 10)
            notes.append("Wide confidence interval — need more trades")

    grade = _score_to_grade(score)
    return ScoreComponent("Sample Size", score, 0.10, grade, notes)


def score_robustness(results: BacktestResults) -> ScoreComponent:
    """Score strategy robustness based on OOS degradation.

    Args:
        results: Backtest results to evaluate.

    Returns:
        ScoreComponent with robustness assessment.
    """
    notes: list[str] = []

    if not results.is_oos:
        score = 50.0
        notes.append("In-sample only — cannot assess robustness without OOS results")
        notes.append("Run walk-forward validation to get out-of-sample metrics")
        grade = _score_to_grade(score)
        return ScoreComponent("Robustness", score, 0.15, grade, notes)

    degradation = results.is_sharpe_degradation
    if degradation is None:
        score = 50.0
        notes.append("OOS results present but no IS comparison provided")
    elif degradation <= 0:
        score = 95.0
        notes.append(f"OOS Sharpe improved by {abs(degradation):.0%} — rare, verify data")
    elif degradation <= 0.15:
        score = 85.0
        notes.append(f"OOS Sharpe degraded {degradation:.0%} — minimal, strategy is robust")
    elif degradation <= 0.30:
        score = 65.0
        notes.append(f"OOS Sharpe degraded {degradation:.0%} — moderate, acceptable")
    elif degradation <= 0.50:
        score = 40.0
        notes.append(f"OOS Sharpe degraded {degradation:.0%} — significant overfitting risk")
    else:
        score = 15.0
        notes.append(f"OOS Sharpe degraded {degradation:.0%} — severe overfitting detected")

    grade = _score_to_grade(score)
    return ScoreComponent("Robustness", score, 0.15, grade, notes)


# ── Scorecard Generation ───────────────────────────────────────────


def generate_scorecard(results: BacktestResults) -> Scorecard:
    """Generate a complete strategy scorecard.

    Args:
        results: Backtest results to evaluate.

    Returns:
        Complete Scorecard with recommendation.
    """
    components = [
        score_edge_quality(results),
        score_risk_management(results),
        score_consistency(results),
        score_sample_size(results),
        score_robustness(results),
    ]

    # Weighted overall score
    overall = sum(c.score * c.weight for c in components)

    # Recommendation
    concerns: list[str] = []
    suggestions: list[str] = []

    if results.sharpe_ratio < 0:
        concerns.append("Negative Sharpe ratio — strategy loses money on risk-adjusted basis")
    if results.max_drawdown_pct > 25:
        concerns.append(f"Max drawdown {results.max_drawdown_pct:.1f}% exceeds 25% threshold")
    if results.trade_count < 50:
        concerns.append(f"Only {results.trade_count} trades — insufficient for statistical significance")
    if results.profit_factor < 1.2:
        concerns.append(f"Profit factor {results.profit_factor:.2f} — thin edge, likely consumed by real-world costs")
    expectancy = (results.win_rate * results.avg_win_loss_ratio) - (1 - results.win_rate)
    if expectancy < 0:
        concerns.append(f"Negative expectancy ({expectancy:.2f}R) — strategy has no edge")

    if results.max_drawdown_pct > 15:
        suggestions.append("Tighten stop losses or reduce position sizes to lower max drawdown")
    if results.trade_count < 100:
        suggestions.append("Extend backtest period or lower timeframe to increase trade count")
    if not results.is_oos:
        suggestions.append("Run walk-forward validation to get out-of-sample metrics")
    if results.sharpe_ratio > 3.0:
        suggestions.append("Sharpe > 3.0 is suspicious — check for lookahead bias or data errors")
    if results.win_rate < 0.35 and results.avg_win_loss_ratio < 2.0:
        suggestions.append("Low win rate with low avg win/loss — improve entries or widen targets")

    # Determine recommendation
    critical_fail = (
        results.sharpe_ratio < 0
        or results.profit_factor < 1.0
        or expectancy < 0
        or results.max_drawdown_pct > 50
    )
    if critical_fail:
        recommendation = "NO-GO"
    elif overall >= 70 and len(concerns) == 0:
        recommendation = "GO"
    elif overall >= 55:
        recommendation = "REVIEW"
    else:
        recommendation = "NO-GO"

    return Scorecard(
        strategy_name=results.strategy_name,
        components=components,
        overall_score=overall,
        recommendation=recommendation,
        concerns=concerns,
        suggestions=suggestions,
    )


# ── Display ─────────────────────────────────────────────────────────


def display_scorecard(sc: Scorecard) -> None:
    """Print a formatted scorecard to stdout.

    Args:
        sc: The scorecard to display.
    """
    rec_display = {
        "GO": "GO — Strategy meets minimum criteria for live trading",
        "REVIEW": "REVIEW — Strategy shows potential but has issues to address",
        "NO-GO": "NO-GO — Strategy does not meet minimum criteria",
    }

    print(f"\n{'=' * 60}")
    print(f" STRATEGY SCORECARD: {sc.strategy_name}")
    print(f"{'=' * 60}\n")

    # Component scores
    print(f" {'Dimension':<20} {'Score':>6} {'Grade':>6} {'Weight':>8}")
    print(f" {'-' * 20} {'-' * 6} {'-' * 6} {'-' * 8}")
    for c in sc.components:
        print(f" {c.name:<20} {c.score:>5.0f}% {c.grade:>5} {c.weight:>7.0%}")
    print(f" {'-' * 20} {'-' * 6}")
    print(f" {'OVERALL':<20} {sc.overall_score:>5.0f}%")
    print()

    # Recommendation
    print(f" RECOMMENDATION: {rec_display.get(sc.recommendation, sc.recommendation)}")
    print()

    # Details per component
    for c in sc.components:
        print(f" [{c.grade}] {c.name}:")
        for note in c.notes:
            print(f"     {note}")
        print()

    # Concerns
    if sc.concerns:
        print(" CONCERNS:")
        for concern in sc.concerns:
            print(f"   - {concern}")
        print()

    # Suggestions
    if sc.suggestions:
        print(" SUGGESTIONS:")
        for suggestion in sc.suggestions:
            print(f"   - {suggestion}")
        print()

    print(f"{'=' * 60}")


# ── Helper ──────────────────────────────────────────────────────────


def _score_to_grade(score: float) -> str:
    """Convert numeric score to letter grade.

    Args:
        score: Score from 0 to 100.

    Returns:
        Letter grade string.
    """
    if score >= 90:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 40:
        return "D"
    else:
        return "F"


# ── Interactive Input ───────────────────────────────────────────────


def prompt_float(label: str, default: float) -> float:
    """Prompt user for a float value.

    Args:
        label: Prompt text.
        default: Default value.

    Returns:
        User-entered float or default.
    """
    try:
        raw = input(f"  {label} [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"    Invalid, using default: {default}")
        return default


def prompt_int(label: str, default: int) -> int:
    """Prompt user for an integer value.

    Args:
        label: Prompt text.
        default: Default value.

    Returns:
        User-entered int or default.
    """
    try:
        raw = input(f"  {label} [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"    Invalid, using default: {default}")
        return default


def prompt_str(label: str, default: str = "") -> str:
    """Prompt user for a string value.

    Args:
        label: Prompt text.
        default: Default value.

    Returns:
        User-entered string or default.
    """
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"  {label}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)
    return raw if raw else default


def interactive_input() -> BacktestResults:
    """Collect backtest results interactively.

    Returns:
        BacktestResults from user input.
    """
    print("\n=== Strategy Scorecard — Enter Backtest Results ===\n")

    name = prompt_str("Strategy name", "My-Strategy")
    style = prompt_str("Style (trend/mean_reversion/breakout/scalping)", "trend")
    total_return = prompt_float("Total return %", 50.0)
    sharpe = prompt_float("Sharpe ratio", 1.0)
    mdd = prompt_float("Max drawdown %", 15.0)
    wr = prompt_float("Win rate (decimal, e.g., 0.45)", 0.45)
    pf = prompt_float("Profit factor", 1.5)
    trades = prompt_int("Trade count", 100)
    awl = prompt_float("Avg win / avg loss ratio", 2.0)
    duration = prompt_float("Avg trade duration (bars)", 10.0)

    is_oos_str = prompt_str("Is this out-of-sample? (y/n)", "n")
    is_oos = is_oos_str.lower().startswith("y")

    degradation: Optional[float] = None
    if is_oos:
        deg = prompt_float("Sharpe degradation from IS (decimal, e.g., 0.2 = 20%)", 0.2)
        degradation = deg

    return BacktestResults(
        strategy_name=name,
        style=style,
        total_return_pct=total_return,
        sharpe_ratio=sharpe,
        max_drawdown_pct=mdd,
        win_rate=wr,
        profit_factor=pf,
        trade_count=trades,
        avg_win_loss_ratio=awl,
        avg_trade_duration_bars=duration,
        is_oos=is_oos,
        is_sharpe_degradation=degradation,
    )


# ── Demo Data ───────────────────────────────────────────────────────


def demo_strategies() -> list[BacktestResults]:
    """Generate three example strategies for demonstration.

    Returns:
        List of BacktestResults: good, mediocre, and bad strategy examples.
    """
    return [
        BacktestResults(
            strategy_name="SOL-Momentum-Pro",
            style="trend",
            total_return_pct=85.0,
            sharpe_ratio=1.8,
            max_drawdown_pct=12.0,
            win_rate=0.42,
            profit_factor=2.1,
            trade_count=230,
            avg_win_loss_ratio=2.8,
            avg_trade_duration_bars=15.0,
            is_oos=True,
            is_sharpe_degradation=0.15,
        ),
        BacktestResults(
            strategy_name="Meme-Mean-Revert",
            style="mean_reversion",
            total_return_pct=22.0,
            sharpe_ratio=0.8,
            max_drawdown_pct=18.0,
            win_rate=0.52,
            profit_factor=1.3,
            trade_count=85,
            avg_win_loss_ratio=1.2,
            avg_trade_duration_bars=8.0,
            is_oos=True,
            is_sharpe_degradation=0.35,
        ),
        BacktestResults(
            strategy_name="YOLO-Breakout",
            style="breakout",
            total_return_pct=-5.0,
            sharpe_ratio=-0.3,
            max_drawdown_pct=42.0,
            win_rate=0.28,
            profit_factor=0.85,
            trade_count=35,
            avg_win_loss_ratio=1.5,
            avg_trade_duration_bars=5.0,
            is_oos=False,
            is_sharpe_degradation=None,
        ),
    ]


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run the strategy scorecard tool."""
    demo_mode = "--demo" in sys.argv

    if demo_mode:
        print("=== Demo Mode: Evaluating 3 Example Strategies ===")
        strategies = demo_strategies()
        for results in strategies:
            scorecard = generate_scorecard(results)
            display_scorecard(scorecard)
    else:
        results = interactive_input()
        scorecard = generate_scorecard(results)
        display_scorecard(scorecard)


if __name__ == "__main__":
    main()
