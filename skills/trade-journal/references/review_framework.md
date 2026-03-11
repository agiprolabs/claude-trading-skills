# Review Framework — Daily, Weekly, Monthly

## Overview

Consistent review cadence is what transforms raw trade data into actionable improvement. Each level of review serves a different purpose: daily catches immediate behavioral issues, weekly reveals strategy-level patterns, and monthly drives structural changes.

## Daily Review (5 Minutes)

Perform at end of trading day or after last trade closes.

### Checklist

- [ ] How many trades today? What was net P&L?
- [ ] Did every trade have a written rationale before entry?
- [ ] Did I follow my position sizing rules on every trade?
- [ ] Did I honor my stop-losses without moving them?
- [ ] Were any trades emotional (FOMO, revenge, boredom)?
- [ ] One thing I did well today
- [ ] One thing to improve tomorrow

### Quick Stats to Compute

```python
daily_stats = {
    "trade_count": len(today_trades),
    "wins": sum(1 for t in today_trades if t["outcome"] == "win"),
    "losses": sum(1 for t in today_trades if t["outcome"] == "loss"),
    "net_pnl_sol": sum(t.get("pnl_sol", 0) for t in today_trades),
    "largest_win": max((t.get("pnl_sol", 0) for t in today_trades), default=0),
    "largest_loss": min((t.get("pnl_sol", 0) for t in today_trades), default=0),
}
```

### Red Flags — Immediate Action Required

| Flag | Signal | Action |
|------|--------|--------|
| 3+ losses in a row | Possible tilt | Stop trading for the day |
| Trade without rationale | Discipline breakdown | Write rationale retroactively, add to improvement list |
| Size > max allowed | Risk violation | Review position sizing rules |
| Trade entered < 10 min after loss | Revenge trading | Mark trade, review in weekly |

## Weekly Review (30 Minutes)

Perform every Sunday or on your designated review day.

### Checklist

- [ ] Total trades this week, win rate, net P&L
- [ ] Win rate and P&L by strategy — which strategies performed?
- [ ] Any revenge trades detected? (re-entry within 15 min of loss)
- [ ] Any tilt trades? (size increase > 1.5x after loss)
- [ ] Best trade of the week — what made it good?
- [ ] Worst trade of the week — what went wrong?
- [ ] Compare planned R:R vs actual R:R
- [ ] Are my self-rated setup quality scores predictive? (Do high-quality setups actually win more?)
- [ ] Any new patterns noticed?

### Questions to Ask

1. **Strategy performance**: Which strategies have positive expectancy over the last 20+ trades? Any strategies I should pause?
2. **Behavioral check**: Am I trading more after losses? Am I cutting winners short?
3. **Risk adherence**: Did I exceed my max daily loss on any day? Did I stick to position limits?
4. **Edge validation**: Is my overall profit factor above 1.5? If not, what is dragging it down?
5. **Improvement tracking**: Did the thing I said I would improve last week actually improve?

### Key Metrics to Compute

```python
weekly_metrics = {
    "total_trades": len(week_trades),
    "win_rate": wins / total if total > 0 else 0,
    "profit_factor": gross_wins / gross_losses if gross_losses > 0 else float("inf"),
    "avg_win_sol": avg(t["pnl_sol"] for t in wins),
    "avg_loss_sol": avg(abs(t["pnl_sol"]) for t in losses),
    "expectancy_sol": (win_rate * avg_win) - ((1 - win_rate) * avg_loss),
    "max_consecutive_losses": max_streak(week_trades, "loss"),
    "revenge_trade_count": len(detect_revenge_trades(week_trades)),
    "avg_setup_quality_winners": avg(t["setup_quality"] for t in wins),
    "avg_setup_quality_losers": avg(t["setup_quality"] for t in losses),
}
```

## Monthly Review (2 Hours)

Comprehensive analysis on the first weekend of each month.

### Checklist

- [ ] Full P&L breakdown by strategy, token, and time period
- [ ] Equity curve — any significant drawdowns?
- [ ] Strategy attribution — which strategies earned their keep?
- [ ] Behavioral pattern summary — trends in emotional trading?
- [ ] Compare this month to previous months — improving or declining?
- [ ] Review and update strategy parameters if needed
- [ ] Set specific improvement goals for next month

### Deep Analysis Questions

1. **Strategy lifecycle**: Are any strategies decaying? Compare last 30 trades vs prior 30 trades per strategy.
2. **Time analysis**: What hours/days are most profitable? Should I restrict trading to certain windows?
3. **Token analysis**: Am I better at trading certain token types? Large caps vs small caps?
4. **Hold time analysis**: Am I holding winners long enough? Am I cutting losses quickly enough?
5. **Sizing analysis**: Am I sizing correctly? Larger on high-conviction, smaller on speculative?
6. **Fee analysis**: What percentage of gross P&L goes to fees and slippage?

### Performance Decay Detection

Track rolling metrics to detect when a strategy or your overall trading is deteriorating.

```python
def detect_decay(trades: list[dict], window: int = 20) -> dict:
    """Compare recent window to prior window."""
    if len(trades) < window * 2:
        return {"status": "insufficient_data"}

    recent = trades[-window:]
    prior = trades[-window * 2:-window]

    recent_wr = sum(1 for t in recent if t["outcome"] == "win") / window
    prior_wr = sum(1 for t in prior if t["outcome"] == "win") / window

    recent_pf = compute_profit_factor(recent)
    prior_pf = compute_profit_factor(prior)

    return {
        "win_rate_change": recent_wr - prior_wr,
        "profit_factor_change": recent_pf - prior_pf,
        "decaying": recent_wr < prior_wr * 0.8 or recent_pf < prior_pf * 0.7,
        "recent_win_rate": recent_wr,
        "prior_win_rate": prior_wr,
    }
```

**Decay thresholds**:
- Win rate drops > 20% relative: investigate
- Profit factor drops > 30% relative: pause the strategy
- 3 consecutive losing weeks: full strategy review required

## Behavioral Red Flags

### Revenge Trading

**Definition**: Entering a new trade within 15 minutes of a losing exit, often with equal or larger size.

**Detection**: Compare `entry_date` of trade N to `exit_date` of trade N-1 when N-1 was a loss.

**Severity levels**:
- Mild: 1-2 revenge trades per week — note and monitor
- Moderate: 3-5 per week — implement mandatory 30-minute cooldown after losses
- Severe: Daily occurrence — stop live trading, review process

### FOMO (Fear of Missing Out)

**Indicators**:
- Setup quality self-rated < 5
- Rationale mentions "already moved" or "catching up"
- Entry after token already moved > 1 ATR from prior level
- No clear stop-loss defined

**Detection**: Correlate low setup quality scores with outcomes.

### Cutting Winners

**Definition**: Average hold time for winning trades is significantly shorter than for losing trades.

**Threshold**: If `avg_win_hold / avg_loss_hold < 0.7`, you are likely cutting winners.

**Fix**: Use trailing stops instead of fixed targets. Review exits on winners that continued moving favorably.

### Riding Losers

**Definition**: Holding losing trades far beyond the planned stop.

**Detection**: Compare actual exit price on losses to the recorded `stop_price`.

**Threshold**: If > 30% of losses exceed the planned stop by > 50%, there is a stop-honoring problem.

### Tilt / Emotional Sizing

**Definition**: Increasing position size after losses, driven by desire to "make it back."

**Detection**: Size of trade N vs trade N-1 when N-1 was a loss. Increase > 1.5x is a red flag.

**Impact analysis**: Compute P&L of tilt trades separately — they almost always have negative expectancy.

### Overtrading

**Definition**: Taking trades that do not meet setup criteria, often from boredom.

**Detection**:
- Trade count per day significantly above your baseline
- Setup quality scores trending downward through the day
- Trades without complete rationale

**Threshold**: More than 2x your average daily trade count without proportional increase in opportunities.

## Improvement Goal Setting

After monthly review, set 1-3 specific, measurable goals:

**Good goals**:
- "Reduce revenge trades from 4/week to 1/week"
- "Increase average setup quality of entries from 6.2 to 7.0"
- "Hold winning momentum trades for at least 2x the current average hold time"
- "Stop trading the `gut-feel` strategy until I can define entry criteria"

**Bad goals**:
- "Make more money" (not specific)
- "Be more disciplined" (not measurable)
- "Never have a losing trade" (not realistic)

Track goals in the journal metadata and review progress weekly.
