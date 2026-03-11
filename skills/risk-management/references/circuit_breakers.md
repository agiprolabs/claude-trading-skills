# Circuit Breakers

Automated controls that restrict or halt trading activity when predefined conditions are met. Circuit breakers protect against compounding losses, emotional decisions, and system failures.

## Daily Loss Limit

### Implementation

```python
from datetime import datetime, timezone

class DailyLossBreaker:
    """Track daily P&L and halt trading when limit is hit."""

    def __init__(self, account_size: float, limit_pct: float = 0.03):
        self.account_size = account_size
        self.limit_pct = limit_pct
        self.limit_amount = account_size * limit_pct
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.reset_date = datetime.now(timezone.utc).date()
        self.consecutive_limit_days = 0

    def update(self, realized: float, unrealized: float) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self.reset_date:
            if self.is_triggered():
                self.consecutive_limit_days += 1
            else:
                self.consecutive_limit_days = 0
            self.realized_pnl = 0.0
            self.unrealized_pnl = 0.0
            self.reset_date = today
        self.realized_pnl = realized
        self.unrealized_pnl = unrealized

    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    def is_triggered(self) -> bool:
        return self.total_pnl() <= -self.limit_amount

    def needs_weekly_halt(self) -> bool:
        return self.consecutive_limit_days >= 3
```

### Rules

| Rule | Detail |
|---|---|
| Tracking | Realized P&L + unrealized P&L combined |
| Trigger | Stop opening new positions when limit hit |
| Existing positions | May be managed (tighten stops) but not added to |
| Reset | Midnight UTC |
| Escalation | 3 consecutive days hitting limit → halt for remainder of week |

### Recommended Limits

| Profile | Daily Limit | Weekly Escalation |
|---|---|---|
| Conservative | -3% | 2 consecutive days |
| Moderate | -4% | 3 consecutive days |
| Aggressive | -5% | 3 consecutive days |

## Consecutive Loss Breaker

### Implementation

```python
class ConsecutiveLossBreaker:
    """Track consecutive losses and enforce size/halt rules."""

    def __init__(self):
        self.consecutive_losses = 0
        self.consecutive_wins = 0

    def record_trade(self, pnl: float) -> None:
        if pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        elif pnl > 0:
            self.consecutive_wins += 1
            if self.consecutive_wins >= 2:
                self.consecutive_losses = 0

    def size_multiplier(self) -> float:
        if self.consecutive_losses >= 7:
            return 0.0  # Halt
        elif self.consecutive_losses >= 5:
            return 0.25  # Minimum size
        elif self.consecutive_losses >= 3:
            return 0.50  # Half size
        return 1.0  # Full size

    def status(self) -> str:
        if self.consecutive_losses >= 7:
            return "HALT — 7+ consecutive losses, 24h mandatory break"
        elif self.consecutive_losses >= 5:
            return "MINIMUM SIZE — 5+ consecutive losses"
        elif self.consecutive_losses >= 3:
            return "HALF SIZE — 3+ consecutive losses"
        return "NORMAL"
```

### Rules

| Consecutive Losses | Action | Reset Condition |
|---|---|---|
| 3 | Reduce position size by 50% | 2 consecutive wins |
| 5 | Minimum position size only | 2 consecutive wins |
| 7 | Halt trading for 24 hours | 24h elapsed + review complete |
| 10+ | Full stop, strategy review | Complete strategy audit |

### Reset Logic

- Consecutive loss counter resets after 2 consecutive wins (not 1, to avoid whipsaw)
- After a 7+ loss halt, counter resets only after the mandatory break AND 2 consecutive wins in paper trading
- The counter persists across days — it tracks consecutive trade outcomes, not daily

## Volatility Circuit Breaker

### Implementation

```python
import numpy as np

class VolatilityBreaker:
    """Monitor portfolio volatility and restrict trading in extreme conditions."""

    def __init__(self, lookback: int = 20, trigger_multiple: float = 2.0,
                 reset_multiple: float = 1.5):
        self.lookback = lookback
        self.trigger_multiple = trigger_multiple
        self.reset_multiple = reset_multiple
        self.returns: list[float] = []
        self.baseline_vol: float | None = None

    def update(self, daily_return: float) -> None:
        self.returns.append(daily_return)
        if len(self.returns) > self.lookback * 3:
            self.returns = self.returns[-self.lookback * 3:]
        if len(self.returns) >= self.lookback:
            self.baseline_vol = float(np.std(self.returns[-self.lookback:]))

    def current_vol(self, window: int = 5) -> float | None:
        if len(self.returns) < window:
            return None
        return float(np.std(self.returns[-window:]))

    def is_triggered(self) -> bool:
        if self.baseline_vol is None:
            return False
        current = self.current_vol()
        if current is None:
            return False
        return current > self.baseline_vol * self.trigger_multiple

    def is_reset(self) -> bool:
        if self.baseline_vol is None:
            return True
        current = self.current_vol()
        if current is None:
            return True
        return current <= self.baseline_vol * self.reset_multiple
```

### Rules

| Condition | Trigger | Action | Reset |
|---|---|---|---|
| Short-term vol > 2× baseline | Triggered | Reduce exposure to 50%, widen stops | Vol drops below 1.5× baseline |
| Short-term vol > 3× baseline | Extreme | Reduce exposure to 25%, exit weak setups | Vol drops below 2× baseline |
| Market-wide liquidation event | Manual | Halt all entries | Manual assessment complete |

### Crypto Volatility Indicators

- SOL 1-hour realized volatility vs 7-day average
- BTC dominance change rate (rapid shifts signal risk-off)
- DEX volume spikes (>3× average may indicate panic)
- Funding rates extreme readings (>0.1% or <-0.1%)

## System Failure Breaker

### Triggers

| Failure Type | Trigger | Action |
|---|---|---|
| API errors | 3+ consecutive failed API calls | Halt new trades |
| RPC failures | Primary + backup RPC unreachable | Halt all activity |
| Price feed stale | No price update for >60 seconds | Halt new trades |
| Unexpected P&L | Single trade P&L > 5× expected | Halt, investigate |
| Execution anomaly | Fill price >5% from expected | Halt, investigate |

### Recovery

1. Identify the failure and confirm it is resolved
2. Verify all position data is accurate (reconcile on-chain state)
3. Resume with reduced size for first 3 trades
4. Return to normal only after 3 successful trades at reduced size

## Combining Circuit Breakers

Multiple breakers can be active simultaneously. Use the most restrictive rule:

```python
def effective_size_multiplier(
    daily_loss_breaker: DailyLossBreaker,
    consecutive_loss_breaker: ConsecutiveLossBreaker,
    volatility_breaker: VolatilityBreaker,
) -> float:
    """Return the most restrictive size multiplier across all breakers."""
    multipliers = []

    if daily_loss_breaker.is_triggered():
        multipliers.append(0.0)
    if consecutive_loss_breaker.size_multiplier() < 1.0:
        multipliers.append(consecutive_loss_breaker.size_multiplier())
    if volatility_breaker.is_triggered():
        multipliers.append(0.5)

    return min(multipliers) if multipliers else 1.0
```

## Implementation Checklist

- [ ] Implement daily loss tracking (realized + unrealized)
- [ ] Set up daily loss limit with UTC reset
- [ ] Track consecutive losses across all strategies
- [ ] Calculate rolling portfolio volatility
- [ ] Define volatility baseline (20-period rolling std)
- [ ] Set up system health monitoring (API, RPC, price feeds)
- [ ] Log all circuit breaker activations with timestamp and cause
- [ ] Review circuit breaker thresholds monthly
- [ ] Test breaker logic with simulated extreme scenarios
- [ ] Ensure breakers cannot be overridden without explicit acknowledgment
