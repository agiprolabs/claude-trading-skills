# Drawdown Management

Comprehensive framework for detecting, responding to, and recovering from portfolio drawdowns in crypto trading.

## Drawdown Mathematics

### Recovery Table

A drawdown of X% requires a gain greater than X% to recover, and the relationship is nonlinear:

| Drawdown | Required Gain | Ratio |
|---|---|---|
| -1% | +1.01% | 1.01× |
| -2% | +2.04% | 1.02× |
| -3% | +3.09% | 1.03× |
| -5% | +5.26% | 1.05× |
| -7% | +7.53% | 1.08× |
| -10% | +11.11% | 1.11× |
| -15% | +17.65% | 1.18× |
| -20% | +25.00% | 1.25× |
| -25% | +33.33% | 1.33× |
| -30% | +42.86% | 1.43× |
| -35% | +53.85% | 1.54× |
| -40% | +66.67% | 1.67× |
| -45% | +81.82% | 1.82× |
| -50% | +100.00% | 2.00× |
| -60% | +150.00% | 2.50× |
| -70% | +233.33% | 3.33× |
| -80% | +400.00% | 5.00× |
| -90% | +900.00% | 10.00× |

**Formula**: `required_gain = drawdown / (1 - drawdown)`

### Why Small Drawdowns Matter

At -10%, recovery is manageable (+11.1%). At -20%, it becomes difficult (+25%). Past -30%, recovery is unlikely without exceptional conditions. The priority is always to keep drawdowns small.

A trader earning 1% per day on average needs:
- 6 trading days to recover from -5%
- 11 days to recover from -10%
- 25 days to recover from -20%
- 100 days to recover from -50%

## Drawdown Detection

### Calculating Current Drawdown

```python
def current_drawdown(equity_curve: list[float]) -> float:
    """Calculate current drawdown from peak.

    Returns:
        Drawdown as a positive fraction (0.10 = 10% drawdown).
    """
    peak = max(equity_curve)
    current = equity_curve[-1]
    if peak <= 0:
        return 0.0
    return (peak - current) / peak
```

### Rolling Peak Tracking

Track the high-water mark continuously:

```python
def rolling_peak(equity_curve: list[float]) -> list[float]:
    """Calculate rolling peak (high-water mark) at each point."""
    peaks = []
    current_peak = equity_curve[0]
    for value in equity_curve:
        current_peak = max(current_peak, value)
        peaks.append(current_peak)
    return peaks
```

### Drawdown Duration

Track not just depth but how long the portfolio has been underwater:

```python
def time_underwater(equity_curve: list[float]) -> int:
    """Count periods since last equity high."""
    peak = equity_curve[0]
    periods = 0
    for value in equity_curve:
        if value >= peak:
            peak = value
            periods = 0
        else:
            periods += 1
    return periods
```

## Drawdown Response Framework

### Level 0: Normal (0–5% drawdown)
- **Detection**: Equity within 5% of peak
- **Action**: Continue trading at full size
- **Monitoring**: Standard daily P&L review
- **Psychology**: Expected fluctuation, no concern

### Level 1: Caution (5–10% drawdown)
- **Detection**: Alert triggers at 5% threshold
- **Action**: Reduce position sizes by 25–50%
- **Monitoring**: Review each trade more carefully before entry
- **Psychology**: Increased discipline, no revenge trading
- **Additional**: Review recent trades for pattern of errors

### Level 2: Warning (10–15% drawdown)
- **Detection**: Alert triggers at 10% threshold
- **Action**: Trade at minimum position sizes only
- **Monitoring**: Daily strategy review, check for edge decay
- **Psychology**: Accept the drawdown, focus on process not P&L
- **Additional**: Consider whether market regime has changed

### Level 3: Critical (15–20% drawdown)
- **Detection**: Alert triggers at 15% threshold
- **Action**: Halt all new trades, manage existing positions only
- **Monitoring**: Review entire strategy, check assumptions
- **Psychology**: Step back, no trading decisions while emotional
- **Additional**: Consult trading journal for similar past periods

### Level 4: Emergency (>20% drawdown)
- **Detection**: Alert triggers at 20% threshold
- **Action**: Full stop — close positions systematically, not in panic
- **Monitoring**: Complete portfolio review before any resumption
- **Psychology**: Mandatory break (48–72 hours minimum)
- **Additional**: Re-evaluate all strategies, parameters, and risk limits

## Recovery Criteria

Before resuming normal-size trading after a drawdown halt:

1. **Time requirement**: Minimum 48 hours of no trading
2. **Analysis complete**: Root cause identified and documented
3. **Strategy validated**: Backtested the strategy on recent data
4. **Paper trading**: 5–10 simulated trades showing the edge still exists
5. **Gradual ramp**: Start at 25% size → 50% → 75% → 100% over 1–2 weeks

## Drawdown Causes and Remediation

### Strategy Decay
- **Symptoms**: Win rate declining over weeks/months, not days
- **Cause**: The edge was arbitraged away or market structure changed
- **Remediation**: Retire the strategy, develop new ones on out-of-sample data

### Regime Change
- **Symptoms**: Sudden performance drop, previously profitable setups failing
- **Cause**: Market shifted (trending → ranging, low vol → high vol)
- **Remediation**: Add regime detection, adapt parameters per regime
- **Reference**: See `regime-detection` skill

### Overexposure
- **Symptoms**: Multiple positions stopping out simultaneously
- **Cause**: Too many correlated positions
- **Remediation**: Enforce correlation limits, reduce concurrent positions

### Emotional Trading
- **Symptoms**: Deviation from plan, increasing size after losses, FOMO entries
- **Cause**: Psychological response to losses
- **Remediation**: Enforce circuit breakers, journal every trade, take breaks

### Incorrect Position Sizing
- **Symptoms**: Single trades causing outsized impact on portfolio
- **Cause**: Position sizes too large relative to stop distance or account size
- **Remediation**: Review `position-sizing` skill, enforce maximum risk per trade

## Historical Drawdown Tracking

Maintain a drawdown log with these fields for every significant drawdown (>5%):

| Field | Description |
|---|---|
| Start date | When equity first dropped below prior peak |
| Trough date | Date of maximum drawdown depth |
| Recovery date | When equity returned to prior peak (or N/A) |
| Depth | Maximum drawdown percentage |
| Duration | Start to trough (periods) |
| Recovery time | Trough to recovery (periods) |
| Cause | Primary cause category |
| Lessons | Key takeaways documented |

This log is invaluable for identifying patterns: Are drawdowns seasonal? Strategy-specific? Correlated with market events?

## Key Principles

1. **Drawdowns are inevitable** — The goal is management, not avoidance
2. **Small drawdowns are recoverable** — Keep them under 15%
3. **Time heals, size kills** — A small position that goes wrong is a learning opportunity; a large one is a disaster
4. **Process over outcome** — Follow the framework even when it feels overly cautious
5. **Document everything** — Future you will thank present you for the drawdown log
