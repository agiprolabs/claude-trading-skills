#!/usr/bin/env python3
"""Position size calculator using multiple sizing methods.

Calculates position size using fixed fractional, volatility-adjusted,
Kelly criterion, and liquidity-constrained methods. Shows the binding
constraint and provides a formatted report.

Usage:
    python scripts/size_calculator.py

    Or with environment variables:
    ACCOUNT_SIZE=10000 ENTRY_PRICE=1.50 STOP_LOSS=1.30 python scripts/size_calculator.py

Dependencies:
    None (pure math, no external packages required)

Environment Variables:
    ACCOUNT_SIZE:    Account value in USD (default: 10000)
    ENTRY_PRICE:     Entry price per unit (default: 1.50)
    STOP_LOSS:       Stop loss price per unit (default: 1.30)
    WIN_RATE:        Historical win rate 0-1 (default: 0.55)
    AVG_WIN_RATIO:   Average win / average loss ratio (default: 1.8)
    POOL_LIQUIDITY:  Total pool liquidity in USD (default: 50000)
    ATR_VALUE:       14-period ATR in price units (default: 0.12)
    TARGET_VOL_PCT:  Target daily portfolio vol as decimal (default: 0.02)
    FEE_RATE:        One-way trading fee as decimal (default: 0.003)
    SLIPPAGE_EST:    Estimated slippage as decimal (default: 0.005)
"""

import os
import sys
from typing import Optional


# ── Configuration ───────────────────────────────────────────────────

def get_float_env(name: str, default: float) -> float:
    """Read a float from an environment variable with a default."""
    val = os.getenv(name, "")
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        print(f"Warning: {name}='{val}' is not a valid number, using default {default}")
        return default


ACCOUNT_SIZE = get_float_env("ACCOUNT_SIZE", 10_000.0)
ENTRY_PRICE = get_float_env("ENTRY_PRICE", 1.50)
STOP_LOSS = get_float_env("STOP_LOSS", 1.30)
WIN_RATE = get_float_env("WIN_RATE", 0.55)
AVG_WIN_RATIO = get_float_env("AVG_WIN_RATIO", 1.8)
POOL_LIQUIDITY = get_float_env("POOL_LIQUIDITY", 50_000.0)
ATR_VALUE = get_float_env("ATR_VALUE", 0.12)
TARGET_VOL_PCT = get_float_env("TARGET_VOL_PCT", 0.02)
FEE_RATE = get_float_env("FEE_RATE", 0.003)
SLIPPAGE_EST = get_float_env("SLIPPAGE_EST", 0.005)


# ── Fixed Fractional Sizing ────────────────────────────────────────

def fixed_fractional(
    account: float,
    risk_pct: float,
    entry: float,
    stop: float,
    fee_rate: float = 0.0,
    slippage: float = 0.0,
) -> dict:
    """Calculate position size using fixed fractional method.

    Args:
        account: Total account value.
        risk_pct: Fraction of account to risk (e.g., 0.02 for 2%).
        entry: Entry price per unit.
        stop: Stop loss price per unit.
        fee_rate: One-way fee rate (applied to entry and exit).
        slippage: Estimated slippage as fraction of entry price.

    Returns:
        Dictionary with units, value, risk_amount, and effective_risk.
    """
    risk_amount = account * risk_pct
    price_risk = abs(entry - stop)
    fee_cost = entry * fee_rate * 2  # round-trip fees
    slippage_cost = entry * slippage
    effective_risk = price_risk + fee_cost + slippage_cost

    if effective_risk <= 0:
        return {"units": 0.0, "value": 0.0, "risk_amount": risk_amount, "effective_risk": 0.0}

    units = risk_amount / effective_risk
    value = units * entry

    return {
        "units": units,
        "value": value,
        "risk_amount": risk_amount,
        "effective_risk": effective_risk,
        "price_risk": price_risk,
        "fee_cost": fee_cost,
        "slippage_cost": slippage_cost,
    }


# ── Volatility-Adjusted Sizing ─────────────────────────────────────

def volatility_adjusted(
    account: float,
    target_vol_pct: float,
    atr: float,
    entry: float,
) -> dict:
    """Calculate position size scaled by volatility.

    Args:
        account: Total account value.
        target_vol_pct: Target daily portfolio volatility as decimal.
        atr: Average True Range (14-period) in price units.
        entry: Current price per unit.

    Returns:
        Dictionary with units, value, and volatility metrics.
    """
    if atr <= 0:
        return {"units": 0.0, "value": 0.0, "daily_vol_pct": 0.0, "expected_daily_pnl": 0.0}

    target_daily_pnl = account * target_vol_pct
    daily_vol_pct = atr / entry
    units = target_daily_pnl / atr
    value = units * entry
    expected_daily_pnl = units * atr

    return {
        "units": units,
        "value": value,
        "daily_vol_pct": daily_vol_pct,
        "expected_daily_pnl": expected_daily_pnl,
        "target_daily_pnl": target_daily_pnl,
    }


# ── Kelly Criterion Sizing ─────────────────────────────────────────

def kelly_criterion(
    account: float,
    win_rate: float,
    payoff_ratio: float,
    entry: float,
    stop: float,
    fraction: float = 0.25,
) -> dict:
    """Calculate position size using Kelly criterion.

    Args:
        account: Total account value.
        win_rate: Probability of winning trade (0-1).
        payoff_ratio: Average win / average loss.
        entry: Entry price per unit.
        stop: Stop loss price per unit.
        fraction: Kelly fraction to use (0.25 recommended).

    Returns:
        Dictionary with full Kelly, fractional Kelly, units, and value.
    """
    q = 1.0 - win_rate
    if payoff_ratio <= 0:
        return {
            "full_kelly": 0.0, "fractional_kelly": 0.0, "fraction_used": fraction,
            "units": 0.0, "value": 0.0, "has_edge": False,
        }

    full_kelly = (win_rate * payoff_ratio - q) / payoff_ratio
    has_edge = full_kelly > 0
    fractional_kelly = max(0.0, full_kelly * fraction)

    price_risk = abs(entry - stop)
    if price_risk <= 0 or not has_edge:
        units = 0.0
    else:
        risk_amount = account * fractional_kelly
        units = risk_amount / price_risk

    value = units * entry

    return {
        "full_kelly": full_kelly,
        "fractional_kelly": fractional_kelly,
        "fraction_used": fraction,
        "units": units,
        "value": value,
        "has_edge": has_edge,
        "expected_growth_fraction": fractional_kelly * (2 - fractional_kelly / max(full_kelly, 1e-9)),
    }


# ── Liquidity-Constrained Sizing ───────────────────────────────────

def liquidity_constrained(
    pool_liquidity: float,
    max_slippage_pct: float,
    entry: float,
) -> dict:
    """Calculate maximum position size based on pool liquidity.

    Args:
        pool_liquidity: Total pool liquidity in USD.
        max_slippage_pct: Maximum acceptable slippage as decimal.
        entry: Token price per unit.

    Returns:
        Dictionary with max_value, max_units, and expected slippage.
    """
    if pool_liquidity <= 0 or entry <= 0:
        return {"max_value": 0.0, "max_units": 0.0, "expected_slippage_pct": 0.0}

    max_value = pool_liquidity * max_slippage_pct
    max_units = max_value / entry
    expected_slippage_pct = max_slippage_pct

    return {
        "max_value": max_value,
        "max_units": max_units,
        "expected_slippage_pct": expected_slippage_pct,
        "pool_liquidity": pool_liquidity,
        "position_as_pct_of_pool": (max_value / pool_liquidity) * 100,
    }


# ── R:R Targets ────────────────────────────────────────────────────

def calculate_rr_targets(
    entry: float,
    stop: float,
    units: float,
) -> list:
    """Calculate reward-to-risk targets for a given position.

    Args:
        entry: Entry price.
        stop: Stop loss price.
        units: Number of units in position.

    Returns:
        List of dicts with R multiple, target price, and P&L.
    """
    risk_per_unit = abs(entry - stop)
    direction = 1 if entry > stop else -1  # long if stop below entry
    targets = []

    for r_multiple in [1.0, 1.5, 2.0, 3.0, 5.0]:
        target_price = entry + direction * risk_per_unit * r_multiple
        pnl = units * direction * (target_price - entry)
        targets.append({
            "r_multiple": r_multiple,
            "target_price": round(target_price, 6),
            "pnl": round(pnl, 2),
        })

    return targets


# ── Report Formatting ──────────────────────────────────────────────

def format_number(val: float, decimals: int = 2) -> str:
    """Format a number with commas and specified decimals."""
    return f"{val:,.{decimals}f}"


def print_header(title: str) -> None:
    """Print a section header."""
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def print_row(label: str, value: str, width: int = 40) -> None:
    """Print a label-value row."""
    print(f"  {label:<{width}} {value}")


def print_report(
    account: float,
    entry: float,
    stop: float,
    win_rate: float,
    payoff_ratio: float,
    pool_liquidity: float,
    atr: float,
    target_vol_pct: float,
    fee_rate: float,
    slippage_est: float,
) -> None:
    """Print the complete position sizing report.

    Args:
        account: Account value in USD.
        entry: Entry price per unit.
        stop: Stop loss price per unit.
        win_rate: Historical win rate (0-1).
        payoff_ratio: Avg win / avg loss.
        pool_liquidity: Pool liquidity in USD.
        atr: 14-period ATR in price units.
        target_vol_pct: Target daily vol as decimal.
        fee_rate: One-way fee rate.
        slippage_est: Estimated slippage fraction.
    """
    # ── Input Summary ───────────────────────────────────────────
    print_header("POSITION SIZE CALCULATOR")
    print_row("Account Size", f"${format_number(account)}")
    print_row("Entry Price", f"${format_number(entry, 6)}")
    print_row("Stop Loss", f"${format_number(stop, 6)}")
    print_row("Price Risk", f"${format_number(abs(entry - stop), 6)} ({abs(entry - stop) / entry * 100:.1f}%)")
    print_row("Win Rate", f"{win_rate * 100:.1f}%")
    print_row("Payoff Ratio", f"{payoff_ratio:.2f}x")
    print_row("Pool Liquidity", f"${format_number(pool_liquidity)}")
    print_row("ATR(14)", f"${format_number(atr, 6)}")
    print_row("Fee Rate (one-way)", f"{fee_rate * 100:.2f}%")
    print_row("Slippage Estimate", f"{slippage_est * 100:.2f}%")

    # ── Fixed Fractional ────────────────────────────────────────
    print_header("METHOD 1: FIXED FRACTIONAL")
    results_ff = {}
    for risk_pct in [0.01, 0.02, 0.03]:
        ff = fixed_fractional(account, risk_pct, entry, stop, fee_rate, slippage_est)
        results_ff[risk_pct] = ff
        label = f"{risk_pct * 100:.0f}% risk"
        print_row(
            label,
            f"{format_number(ff['units'])} units | ${format_number(ff['value'])} value | ${format_number(ff['risk_amount'])} at risk",
        )
    ff_default = results_ff[0.02]
    print(f"\n  Fee-adjusted risk per unit: ${format_number(ff_default['effective_risk'], 4)}")
    print(f"  (Price risk ${format_number(ff_default['price_risk'], 4)} + fees ${format_number(ff_default['fee_cost'], 4)} + slippage ${format_number(ff_default['slippage_cost'], 4)})")

    # ── Volatility-Adjusted ─────────────────────────────────────
    print_header("METHOD 2: VOLATILITY-ADJUSTED")
    va = volatility_adjusted(account, target_vol_pct, atr, entry)
    print_row("Daily Vol (ATR/Price)", f"{va['daily_vol_pct'] * 100:.1f}%")
    print_row("Target Daily PnL", f"${format_number(va['target_daily_pnl'])}")
    print_row("Position Size", f"{format_number(va['units'])} units")
    print_row("Position Value", f"${format_number(va['value'])}")
    print_row("Expected Daily PnL Range", f"+/- ${format_number(va['expected_daily_pnl'])}")

    # ── Kelly Criterion ─────────────────────────────────────────
    print_header("METHOD 3: KELLY CRITERION")
    kelly_results = {}
    for frac, label in [(1.0, "Full Kelly"), (0.5, "Half Kelly"), (0.25, "Quarter Kelly")]:
        kc = kelly_criterion(account, win_rate, payoff_ratio, entry, stop, frac)
        kelly_results[frac] = kc
        edge_str = "" if kc["has_edge"] else " [NO EDGE]"
        print_row(
            f"{label} ({frac:.0%})",
            f"{kc['fractional_kelly'] * 100:.1f}% risk | {format_number(kc['units'])} units | ${format_number(kc['value'])}{edge_str}",
        )
    full_kc = kelly_results[1.0]
    print(f"\n  Full Kelly fraction: {full_kc['full_kelly'] * 100:.2f}%")
    if not full_kc["has_edge"]:
        print("  *** NEGATIVE KELLY: No statistical edge detected. Do not trade. ***")
    else:
        print("  Recommendation: Use Quarter Kelly (0.25x) as default")

    # ── Liquidity-Constrained ───────────────────────────────────
    print_header("METHOD 4: LIQUIDITY-CONSTRAINED")
    liq_results = {}
    for slip_pct in [0.01, 0.02, 0.05]:
        lc = liquidity_constrained(pool_liquidity, slip_pct, entry)
        liq_results[slip_pct] = lc
        print_row(
            f"{slip_pct * 100:.0f}% max slippage",
            f"{format_number(lc['max_units'])} units | ${format_number(lc['max_value'])} max value | {lc['position_as_pct_of_pool']:.1f}% of pool",
        )

    # ── Combined Recommendation ─────────────────────────────────
    print_header("RECOMMENDATION (BINDING CONSTRAINT)")

    candidates = {
        "Fixed Fractional (2%)": ff_default["units"],
        "Volatility-Adjusted": va["units"],
        "Quarter Kelly": kelly_results[0.25]["units"],
        "Liquidity (2% slip)": liq_results[0.02]["max_units"],
    }

    # Filter out zero/negative
    valid = {k: v for k, v in candidates.items() if v > 0}
    if not valid:
        print("  No valid position size found. Check inputs.")
        return

    binding_method = min(valid, key=valid.get)
    recommended_units = valid[binding_method]
    recommended_value = recommended_units * entry
    pct_of_account = (recommended_value / account) * 100

    print_row("Binding Constraint", binding_method)
    print_row("Recommended Size", f"{format_number(recommended_units)} units")
    print_row("Position Value", f"${format_number(recommended_value)}")
    print_row("% of Account", f"{pct_of_account:.1f}%")

    # Check portfolio limits
    print("\n  Portfolio limit checks:")
    single_ok = pct_of_account <= 10
    print(f"    Single position < 10%: {'PASS' if single_ok else 'FAIL'} ({pct_of_account:.1f}%)")

    print("\n  All methods compared:")
    for method, units in sorted(candidates.items(), key=lambda x: x[1]):
        marker = " <-- BINDING" if method == binding_method else ""
        val = units * entry
        print(f"    {method:<30} {format_number(units):>12} units  ${format_number(val):>12}{marker}")

    # ── R:R Targets ─────────────────────────────────────────────
    print_header("R:R TARGETS (at recommended size)")
    risk_per_unit = abs(entry - stop)
    risk_total = recommended_units * risk_per_unit
    targets = calculate_rr_targets(entry, stop, recommended_units)

    print_row("Risk per trade", f"${format_number(risk_total)}")
    print()
    print(f"  {'R:R':<8} {'Target Price':<16} {'P&L':<16} {'% of Account'}")
    print(f"  {'-' * 56}")
    for t in targets:
        pct = (t["pnl"] / account) * 100
        print(f"  {t['r_multiple']:<8.1f} ${format_number(t['target_price'], 6):<14} ${format_number(t['pnl']):<14} {pct:+.2f}%")


# ── Validation ──────────────────────────────────────────────────────

def validate_inputs(
    account: float,
    entry: float,
    stop: float,
    win_rate: float,
    payoff_ratio: float,
    pool_liquidity: float,
) -> list:
    """Validate inputs and return list of warning messages.

    Args:
        account: Account size.
        entry: Entry price.
        stop: Stop loss price.
        win_rate: Win rate (0-1).
        payoff_ratio: Avg win / avg loss.
        pool_liquidity: Pool liquidity.

    Returns:
        List of warning/error strings. Empty list means all OK.
    """
    errors: list = []
    if account <= 0:
        errors.append("Account size must be positive")
    if entry <= 0:
        errors.append("Entry price must be positive")
    if stop <= 0:
        errors.append("Stop loss must be positive")
    if entry == stop:
        errors.append("Entry and stop loss cannot be the same price")
    if not 0 < win_rate < 1:
        errors.append(f"Win rate must be between 0 and 1, got {win_rate}")
    if payoff_ratio <= 0:
        errors.append("Payoff ratio must be positive")
    if pool_liquidity <= 0:
        errors.append("Pool liquidity must be positive")

    # Warnings (non-fatal)
    risk_pct = abs(entry - stop) / entry * 100
    if risk_pct > 30:
        errors.append(f"Warning: Stop distance is {risk_pct:.1f}% from entry (very wide)")
    if pool_liquidity < account * 0.1:
        errors.append("Warning: Pool liquidity is less than 10% of account size")

    return errors


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Run the position size calculator with configured parameters."""
    issues = validate_inputs(
        ACCOUNT_SIZE, ENTRY_PRICE, STOP_LOSS,
        WIN_RATE, AVG_WIN_RATIO, POOL_LIQUIDITY,
    )

    fatal = [i for i in issues if not i.startswith("Warning")]
    warnings = [i for i in issues if i.startswith("Warning")]

    if fatal:
        print("Input errors:")
        for e in fatal:
            print(f"  - {e}")
        sys.exit(1)

    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"  - {w}")

    print_report(
        account=ACCOUNT_SIZE,
        entry=ENTRY_PRICE,
        stop=STOP_LOSS,
        win_rate=WIN_RATE,
        payoff_ratio=AVG_WIN_RATIO,
        pool_liquidity=POOL_LIQUIDITY,
        atr=ATR_VALUE,
        target_vol_pct=TARGET_VOL_PCT,
        fee_rate=FEE_RATE,
        slippage_est=SLIPPAGE_EST,
    )


if __name__ == "__main__":
    main()
