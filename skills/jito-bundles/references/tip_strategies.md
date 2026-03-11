# Jito Tip Strategies

## Overview

The tip is a SOL transfer added as the last instruction of the last transaction in a bundle. Tips incentivize Jito-enabled validators to include your bundle. The tip amount directly affects landing probability — under-tipped bundles are deprioritized relative to higher-tipping competitors.

## Tip Account Selection

Jito maintains 8 tip accounts. Fetch them via `getTipAccounts` and rotate through them:

```python
import random

def select_tip_account(tip_accounts: list[str]) -> str:
    """Select a random tip account to distribute validator load."""
    return random.choice(tip_accounts)
```

**Cache tip accounts** for 60 seconds. They rarely change, and fetching them on every bundle wastes API calls.

## Static Tip Strategies

### Fixed Tip

Set a constant tip amount. Simple but doesn't adapt to network conditions.

```python
TIP_LAMPORTS = 25_000  # 0.000025 SOL — reasonable for standard swaps
```

**When to use:** Low-urgency transactions where you don't mind occasional drops.

### Tiered by Urgency

Pre-define tip levels by transaction urgency:

```python
TIP_TIERS = {
    "low":      5_000,       # 0.000005 SOL — background tasks
    "normal":   25_000,      # 0.000025 SOL — standard swaps
    "high":     100_000,     # 0.0001 SOL   — time-sensitive trades
    "critical": 500_000,     # 0.0005 SOL   — must land this slot
    "extreme":  5_000_000,   # 0.005 SOL    — competitive MEV/liquidation
}

def get_tip(urgency: str = "normal") -> int:
    return TIP_TIERS.get(urgency, TIP_TIERS["normal"])
```

## Dynamic Tip Strategies

### Percentile-Based Tipping

Query recent tip distribution and tip at a target percentile:

```python
def calculate_percentile_tip(
    recent_tips: list[int],
    target_percentile: float = 0.50,
    minimum: int = 5_000,
) -> int:
    """Tip at a given percentile of recent bundle tips.

    Args:
        recent_tips: List of recent tip amounts in lamports.
        target_percentile: 0.0-1.0, where 0.5 = median.
        minimum: Floor tip amount.

    Returns:
        Tip in lamports.
    """
    if not recent_tips:
        return minimum
    sorted_tips = sorted(recent_tips)
    idx = int(len(sorted_tips) * target_percentile)
    idx = min(idx, len(sorted_tips) - 1)
    return max(sorted_tips[idx], minimum)
```

**Guideline percentiles:**
- 25th percentile: Economy — may drop during congestion
- 50th percentile: Standard — lands most of the time
- 75th percentile: Priority — high landing probability
- 90th+ percentile: Competitive — for time-critical operations

### Congestion-Adjusted Tipping

Scale tips based on network congestion signals:

```python
def congestion_adjusted_tip(
    base_tip: int,
    recent_slot_time_ms: float,
    avg_slot_time_ms: float = 400.0,
    max_multiplier: float = 5.0,
) -> int:
    """Increase tip when slots are slower (congested).

    When slots take longer than average, the network is congested
    and competition for block space increases.
    """
    if recent_slot_time_ms <= avg_slot_time_ms:
        return base_tip

    # Congestion ratio: 1.0 = normal, 2.0 = slots taking 2x longer
    congestion_ratio = recent_slot_time_ms / avg_slot_time_ms
    multiplier = min(congestion_ratio, max_multiplier)
    return int(base_tip * multiplier)
```

### Escalating Retry Tips

Increase tip on each retry attempt:

```python
def escalating_tip(
    base_tip: int,
    attempt: int,
    escalation_factor: float = 1.5,
    max_tip: int = 1_000_000,
) -> int:
    """Increase tip with each failed attempt.

    Args:
        base_tip: Starting tip in lamports.
        attempt: Current attempt number (0-indexed).
        escalation_factor: Multiplier per attempt.
        max_tip: Maximum tip cap to prevent accidents.

    Returns:
        Tip in lamports, capped at max_tip.
    """
    tip = int(base_tip * (escalation_factor ** attempt))
    return min(tip, max_tip)

# attempt 0: 25,000
# attempt 1: 37,500
# attempt 2: 56,250
# attempt 3: 84,375 (capped if > max_tip)
```

## Cost Optimization

### Tip Budgeting

Set a per-trade tip budget and track spending:

```python
class TipBudget:
    """Track tip spending against a budget."""

    def __init__(self, daily_budget_lamports: int = 5_000_000):
        self.daily_budget = daily_budget_lamports
        self.spent_today = 0

    def can_afford(self, tip: int) -> bool:
        return (self.spent_today + tip) <= self.daily_budget

    def record_tip(self, tip: int) -> None:
        self.spent_today += tip

    def remaining(self) -> int:
        return max(0, self.daily_budget - self.spent_today)

    def reset_daily(self) -> None:
        self.spent_today = 0
```

### Bundle vs Priority Fee Decision

Not every transaction needs a bundle. Compare costs:

```python
def should_use_bundle(
    trade_size_lamports: int,
    estimated_mev_risk_bps: float,
    bundle_tip: int,
    priority_fee: int,
) -> bool:
    """Decide whether a bundle is worth the extra tip cost.

    Args:
        trade_size_lamports: Size of the trade in lamports.
        estimated_mev_risk_bps: Estimated MEV loss in basis points.
        bundle_tip: Cost of bundle tip in lamports.
        priority_fee: Cost of priority fee in lamports.

    Returns:
        True if bundle protection saves more than it costs.
    """
    mev_cost = int(trade_size_lamports * estimated_mev_risk_bps / 10_000)
    bundle_extra_cost = bundle_tip - priority_fee
    return mev_cost > bundle_extra_cost
```

**Rule of thumb:** If MEV risk (in lamports) exceeds the bundle tip premium over a priority fee, use a bundle.

### Tip Minimization

For non-competitive transactions (no one else is trying to do the same trade):

1. Start with the minimum viable tip (5,000-10,000 lamports)
2. If dropped, retry with 1.5x the tip
3. Track your personal landing rate at each tip level
4. Find the minimum tip that gives you an acceptable landing rate (>80%)

```python
def find_minimum_viable_tip(
    landing_rates: dict[int, float],
    target_rate: float = 0.80,
) -> int:
    """Find the lowest tip that achieves the target landing rate.

    Args:
        landing_rates: {tip_amount: landing_rate} from historical data.
        target_rate: Minimum acceptable landing rate (0.0-1.0).

    Returns:
        Minimum tip amount meeting the target.
    """
    for tip, rate in sorted(landing_rates.items()):
        if rate >= target_rate:
            return tip
    # If no tip meets the target, return the highest tested
    return max(landing_rates.keys()) if landing_rates else 50_000
```

## Safety Guardrails

Always implement tip caps to prevent accidental overpayment:

```python
MAX_TIP_LAMPORTS = 10_000_000  # 0.01 SOL hard cap

def safe_tip(tip: int) -> int:
    """Apply safety cap to tip amount."""
    if tip > MAX_TIP_LAMPORTS:
        print(f"WARNING: Tip {tip} exceeds cap {MAX_TIP_LAMPORTS}, capping")
    return min(tip, MAX_TIP_LAMPORTS)
```

**Common tip mistakes:**
- Using SOL instead of lamports (1 SOL = 1,000,000,000 lamports)
- Not capping dynamic tips (congestion spike = 100x tip)
- Tipping on every retry with the same blockhash (waste; bundle won't land anyway)
- Over-tipping non-competitive transactions (nobody is competing for your swap)
