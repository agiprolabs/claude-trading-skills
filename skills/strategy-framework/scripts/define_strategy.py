#!/usr/bin/env python3
"""Interactive strategy definition tool.

Prompts the user through each section of the strategy template and
generates a formatted strategy document. Use --demo mode to see an
example EMA crossover strategy definition without interactive input.

Usage:
    python scripts/define_strategy.py           # Interactive mode
    python scripts/define_strategy.py --demo    # Generate example strategy

Dependencies:
    None (standard library only)
"""

import sys
import textwrap
from dataclasses import dataclass, field
from typing import Optional


# ── Data Structures ─────────────────────────────────────────────────


@dataclass
class ExitRule:
    """A single exit rule with method and parameters."""

    exit_type: str
    method: str
    parameters: str


@dataclass
class PerformanceCriteria:
    """Thresholds for continue / review / retire decisions."""

    continue_sharpe: float = 1.0
    continue_pf: float = 1.5
    continue_win_rate: float = 0.40
    continue_max_dd: float = 0.20
    review_degradation: float = 0.25
    retire_sharpe: float = 0.0


@dataclass
class StrategyDefinition:
    """Complete strategy definition."""

    name: str = ""
    version: str = "1.0"
    asset_class: str = ""
    timeframe_primary: str = ""
    timeframe_confirmation: str = ""
    style: str = ""
    edge_hypothesis: str = ""
    entry_conditions: list[str] = field(default_factory=list)
    entry_logic: str = "AND"
    exit_rules: list[ExitRule] = field(default_factory=list)
    sizing_method: str = ""
    risk_per_trade: float = 0.02
    max_position_pct: float = 0.10
    max_concurrent: int = 5
    daily_loss_limit: float = 0.05
    max_drawdown_halt: float = 0.15
    correlated_limit: float = 0.10
    regime_filter: str = ""
    volume_filter: str = ""
    time_filter: str = ""
    token_filter: str = ""
    performance: PerformanceCriteria = field(default_factory=PerformanceCriteria)
    notes: str = ""


# ── Validation ──────────────────────────────────────────────────────


def validate_strategy(strategy: StrategyDefinition) -> list[str]:
    """Validate strategy definition completeness.

    Args:
        strategy: The strategy definition to validate.

    Returns:
        List of warning messages for missing or incomplete sections.
    """
    warnings: list[str] = []

    if not strategy.name:
        warnings.append("MISSING: Strategy name")
    if not strategy.asset_class:
        warnings.append("MISSING: Asset class")
    if not strategy.timeframe_primary:
        warnings.append("MISSING: Primary timeframe")
    if not strategy.style:
        warnings.append("MISSING: Strategy style")
    if not strategy.edge_hypothesis:
        warnings.append("MISSING: Edge hypothesis — you must articulate your edge")
    if len(strategy.entry_conditions) == 0:
        warnings.append("MISSING: Entry conditions — need at least one")
    if len(strategy.entry_conditions) < 2:
        warnings.append("WARNING: Only one entry condition — consider adding confirmation")
    if len(strategy.exit_rules) == 0:
        warnings.append("MISSING: Exit rules — need at least a stop loss")
    else:
        has_stop = any(r.exit_type.lower() == "stop loss" for r in strategy.exit_rules)
        if not has_stop:
            warnings.append("CRITICAL: No stop loss defined — every strategy needs a stop loss")
    if not strategy.sizing_method:
        warnings.append("MISSING: Position sizing method")
    if strategy.risk_per_trade > 0.05:
        warnings.append(
            f"WARNING: Risk per trade is {strategy.risk_per_trade:.1%} — "
            "consider keeping under 5%"
        )
    if strategy.max_drawdown_halt > 0.25:
        warnings.append(
            f"WARNING: Max drawdown halt is {strategy.max_drawdown_halt:.0%} — "
            "consider a tighter limit"
        )
    if not strategy.regime_filter:
        warnings.append("WARNING: No regime filter — strategy may underperform in wrong regime")

    return warnings


# ── Formatting ──────────────────────────────────────────────────────


def format_strategy(strategy: StrategyDefinition) -> str:
    """Format a strategy definition as a markdown document.

    Args:
        strategy: The strategy definition to format.

    Returns:
        Formatted markdown string.
    """
    lines: list[str] = []

    lines.append(f"# Strategy: {strategy.name} v{strategy.version}")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append(f"- **Asset class**: {strategy.asset_class}")
    lines.append(
        f"- **Timeframe**: Primary {strategy.timeframe_primary}"
        + (f", Confirmation {strategy.timeframe_confirmation}"
           if strategy.timeframe_confirmation else "")
    )
    lines.append(f"- **Style**: {strategy.style}")
    lines.append(f"- **Edge hypothesis**: {strategy.edge_hypothesis}")
    lines.append("")

    # Entry Rules
    lines.append("## Entry Rules")
    lines.append("")
    for i, condition in enumerate(strategy.entry_conditions, 1):
        lines.append(f"- Condition {i}: {condition}")
    lines.append("")
    lines.append(f"**Entry logic**: {strategy.entry_logic} — "
                 f"{'all' if strategy.entry_logic == 'AND' else 'any'} "
                 f"conditions must be true")
    lines.append("")

    # Exit Rules
    lines.append("## Exit Rules")
    lines.append("")
    if strategy.exit_rules:
        for rule in strategy.exit_rules:
            lines.append(f"### {rule.exit_type}")
            lines.append(f"- **Method**: {rule.method}")
            lines.append(f"- **Parameters**: {rule.parameters}")
            lines.append("")
    else:
        lines.append("*No exit rules defined — INCOMPLETE*")
        lines.append("")

    # Position Sizing
    lines.append("## Position Sizing")
    lines.append(f"- **Method**: {strategy.sizing_method}")
    lines.append(f"- **Risk per trade**: {strategy.risk_per_trade:.1%}")
    lines.append(f"- **Max position**: {strategy.max_position_pct:.0%} of portfolio")
    lines.append("")

    # Risk Parameters
    lines.append("## Risk Parameters")
    lines.append(f"- **Max concurrent positions**: {strategy.max_concurrent}")
    lines.append(f"- **Daily loss limit**: {strategy.daily_loss_limit:.1%}")
    lines.append(f"- **Max drawdown halt**: {strategy.max_drawdown_halt:.0%}")
    lines.append(f"- **Correlated exposure limit**: {strategy.correlated_limit:.0%}")
    lines.append("")

    # Filters
    lines.append("## Filters")
    lines.append(f"- **Regime filter**: {strategy.regime_filter or 'None specified'}")
    lines.append(f"- **Volume filter**: {strategy.volume_filter or 'None specified'}")
    lines.append(f"- **Time filter**: {strategy.time_filter or 'None specified'}")
    lines.append(f"- **Token filter**: {strategy.token_filter or 'None specified'}")
    lines.append("")

    # Performance Criteria
    perf = strategy.performance
    lines.append("## Performance Criteria")
    lines.append(
        f"- **Continue if**: Sharpe > {perf.continue_sharpe}, "
        f"PF > {perf.continue_pf}, "
        f"Win Rate > {perf.continue_win_rate:.0%}, "
        f"MDD < {perf.continue_max_dd:.0%}"
    )
    lines.append(
        f"- **Review if**: Any metric degrades {perf.review_degradation:.0%} from baseline"
    )
    lines.append(
        f"- **Retire if**: Rolling 30d Sharpe < {perf.retire_sharpe}"
    )
    lines.append("")

    # Backtest Results (placeholder)
    lines.append("## Backtest Results")
    lines.append("")
    lines.append("*Fill in after backtesting*")
    lines.append("")
    lines.append("### In-Sample")
    lines.append("- Period: ")
    lines.append("- Sharpe: ")
    lines.append("- Max Drawdown: ")
    lines.append("- Win Rate: ")
    lines.append("- Profit Factor: ")
    lines.append("- Trade Count: ")
    lines.append("")
    lines.append("### Out-of-Sample")
    lines.append("- Period: ")
    lines.append("- Sharpe: ")
    lines.append("- Max Drawdown: ")
    lines.append("- Win Rate: ")
    lines.append("- Profit Factor: ")
    lines.append("- Trade Count: ")
    lines.append("")

    # Notes
    if strategy.notes:
        lines.append("## Notes")
        lines.append(strategy.notes)
        lines.append("")

    # Change Log
    lines.append("## Change Log")
    lines.append(f"- **v{strategy.version}**: Initial strategy definition")
    lines.append("")

    return "\n".join(lines)


# ── Interactive Mode ────────────────────────────────────────────────


def prompt(label: str, default: str = "") -> str:
    """Prompt the user for input with an optional default.

    Args:
        label: The prompt label to display.
        default: Default value if user presses Enter.

    Returns:
        User input or default value.
    """
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"  {label}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)
    return value if value else default


def prompt_float(label: str, default: float) -> float:
    """Prompt for a float value with a default.

    Args:
        label: The prompt label.
        default: Default float value.

    Returns:
        Parsed float from user input.
    """
    raw = prompt(label, str(default))
    try:
        return float(raw)
    except ValueError:
        print(f"    Invalid number, using default: {default}")
        return default


def prompt_int(label: str, default: int) -> int:
    """Prompt for an integer value with a default.

    Args:
        label: The prompt label.
        default: Default integer value.

    Returns:
        Parsed integer from user input.
    """
    raw = prompt(label, str(default))
    try:
        return int(raw)
    except ValueError:
        print(f"    Invalid number, using default: {default}")
        return default


def interactive_define() -> StrategyDefinition:
    """Walk the user through defining a strategy interactively.

    Returns:
        Completed StrategyDefinition.
    """
    s = StrategyDefinition()

    print("\n=== Strategy Definition Tool ===\n")
    print("Fill in each section. Press Enter to skip optional fields.\n")

    # Identity
    print("── Identity ──")
    s.name = prompt("Strategy name", "My-Strategy")
    s.version = prompt("Version", "1.0")
    s.asset_class = prompt("Asset class (e.g., Solana tokens top 50 by volume)")
    s.timeframe_primary = prompt("Primary timeframe (e.g., 1H)")
    s.timeframe_confirmation = prompt("Confirmation timeframe (e.g., 4H, optional)")
    s.style = prompt("Style (Trend/MeanReversion/Breakout/Scalping/Other)")
    print()

    # Edge
    print("── Edge Hypothesis ──")
    s.edge_hypothesis = prompt("What market inefficiency are you exploiting?")
    print()

    # Entry
    print("── Entry Rules ──")
    print("  Enter conditions one per line. Empty line to finish.")
    while True:
        condition = prompt(f"Condition {len(s.entry_conditions) + 1} (empty to finish)")
        if not condition:
            break
        s.entry_conditions.append(condition)
    s.entry_logic = prompt("Logic (AND/OR)", "AND").upper()
    print()

    # Exit
    print("── Exit Rules ──")
    for exit_type in ["Stop Loss", "Take Profit", "Trailing Stop", "Time Stop", "Signal Exit"]:
        method = prompt(f"{exit_type} method (empty to skip)")
        if method:
            params = prompt(f"{exit_type} parameters")
            s.exit_rules.append(ExitRule(exit_type=exit_type, method=method, parameters=params))
    print()

    # Position Sizing
    print("── Position Sizing ──")
    s.sizing_method = prompt("Method (FixedFractional/VolatilityAdjusted/Kelly)", "FixedFractional")
    s.risk_per_trade = prompt_float("Risk per trade (decimal, e.g., 0.02 = 2%)", 0.02)
    s.max_position_pct = prompt_float("Max position % of portfolio (decimal)", 0.10)
    print()

    # Risk
    print("── Risk Parameters ──")
    s.max_concurrent = prompt_int("Max concurrent positions", 5)
    s.daily_loss_limit = prompt_float("Daily loss limit (decimal)", 0.05)
    s.max_drawdown_halt = prompt_float("Max drawdown halt (decimal)", 0.15)
    s.correlated_limit = prompt_float("Correlated exposure limit (decimal)", 0.10)
    print()

    # Filters
    print("── Filters ──")
    s.regime_filter = prompt("Regime filter (e.g., only trade when ADX > 20)")
    s.volume_filter = prompt("Volume filter (e.g., 24h volume > $500K)")
    s.time_filter = prompt("Time filter (e.g., 08:00-22:00 UTC)")
    s.token_filter = prompt("Token filter (e.g., age > 7d, holders > 500)")
    print()

    # Performance
    print("── Performance Criteria ──")
    s.performance.continue_sharpe = prompt_float("Min Sharpe to continue", 1.0)
    s.performance.continue_pf = prompt_float("Min Profit Factor to continue", 1.5)
    s.performance.continue_win_rate = prompt_float("Min Win Rate to continue (decimal)", 0.40)
    s.performance.continue_max_dd = prompt_float("Max drawdown to continue (decimal)", 0.20)
    print()

    # Notes
    s.notes = prompt("Additional notes (optional)")

    return s


# ── Demo Mode ───────────────────────────────────────────────────────


def demo_strategy() -> StrategyDefinition:
    """Generate an example EMA crossover strategy definition.

    Returns:
        A fully populated StrategyDefinition for demonstration.
    """
    return StrategyDefinition(
        name="SOL-EMA-Cross",
        version="1.0",
        asset_class="Solana tokens, top 50 by 24h volume on Birdeye",
        timeframe_primary="1H",
        timeframe_confirmation="4H",
        style="Trend Following",
        edge_hypothesis=(
            "Solana mid-cap tokens exhibit momentum persistence on the 1H timeframe "
            "due to retail herding behavior and low institutional participation. "
            "EMA crossovers capture trend initiation with volume confirmation "
            "filtering out false signals."
        ),
        entry_conditions=[
            "EMA(12) crosses above EMA(26) on 1H chart",
            "EMA(26) slope is positive over last 3 bars (trend confirmation)",
            "Volume > 1.5x 20-period volume SMA (volume confirmation)",
            "ADX(14) > 20 (trending regime filter)",
            "4H EMA(12) > 4H EMA(26) (higher timeframe alignment)",
        ],
        entry_logic="AND",
        exit_rules=[
            ExitRule("Stop Loss", "ATR-based", "2.0 x ATR(14) below entry price"),
            ExitRule("Take Profit", "Risk multiple", "3.0 x risk distance (3:1 R:R)"),
            ExitRule(
                "Trailing Stop", "Chandelier Exit",
                "3.0 x ATR(14) from highest high since entry, "
                "activated after 1.5R profit"
            ),
            ExitRule("Time Stop", "Bar count", "Close if < 0.5R move after 20 bars"),
            ExitRule("Signal Exit", "EMA reversal", "EMA(12) crosses below EMA(26) on 1H"),
        ],
        sizing_method="Fixed Fractional",
        risk_per_trade=0.02,
        max_position_pct=0.10,
        max_concurrent=5,
        daily_loss_limit=0.05,
        max_drawdown_halt=0.15,
        correlated_limit=0.10,
        regime_filter="Only trade when ADX(14) > 20 (trending regime)",
        volume_filter="24h volume > $500K, pool liquidity > $100K",
        time_filter="08:00-22:00 UTC (peak Solana activity)",
        token_filter="Token age > 7 days, holder count > 500, top 10 holders < 50% supply",
        performance=PerformanceCriteria(
            continue_sharpe=1.0,
            continue_pf=1.5,
            continue_win_rate=0.40,
            continue_max_dd=0.20,
            review_degradation=0.25,
            retire_sharpe=0.0,
        ),
        notes=(
            "This strategy works best during moderate trending conditions. "
            "Avoid during high-volatility regime changes (e.g., major protocol updates, "
            "regulatory announcements). Consider pausing during BTC dominance spikes "
            "as altcoin trends become unreliable."
        ),
    )


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run the strategy definition tool."""
    demo_mode = "--demo" in sys.argv

    if demo_mode:
        print("=== Demo Mode: EMA Crossover Strategy ===\n")
        strategy = demo_strategy()
    else:
        strategy = interactive_define()

    # Validate
    warnings = validate_strategy(strategy)

    # Output
    document = format_strategy(strategy)
    print("\n" + "=" * 60)
    print(document)
    print("=" * 60)

    # Validation report
    if warnings:
        print(f"\n⚠ Validation ({len(warnings)} issues):\n")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\nValidation: All sections complete.")

    print("\nTo save this strategy definition:")
    print(f"  python scripts/define_strategy.py {'--demo ' if demo_mode else ''}"
          f"> strategies/{strategy.name.lower().replace(' ', '-')}-v{strategy.version}.md")


if __name__ == "__main__":
    main()
