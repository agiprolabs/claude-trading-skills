---
name: trade-journal
description: Structured trade logging, performance review, behavioral pattern detection, and strategy attribution for systematic improvement
---

# Trade Journal

Structured trade journaling for systematic improvement. Log every trade with context, review performance at multiple cadences, detect behavioral patterns that destroy edge, and attribute returns to specific strategies.

## Why Journaling Matters

Most traders fail not from bad strategies but from bad behavior. A trade journal transforms subjective "feel" into objective data:

- **Strategy Attribution**: Know which setups actually make money vs. which feel profitable
- **Behavioral Detection**: Catch revenge trading, FOMO entries, and premature exits before they compound
- **Pattern Recognition**: Discover that your Monday morning trades lose money, or that you cut SOL winners too early
- **Accountability**: Written rationale before entry forces deliberate decision-making
- **Improvement Tracking**: Measure whether changes to your process actually improve results

Without a journal, you optimize on noise. With one, you optimize on signal.

## Trade Record Structure

Every trade record captures context at entry and outcome at exit. See `references/record_format.md` for the complete 18-field schema.

### Minimum Required Fields

```python
trade = {
    "id": "T-20250310-001",
    "token": "SOL",
    "direction": "long",
    "entry_date": "2025-03-10T14:30:00Z",
    "entry_price": 142.50,
    "size_sol": 5.0,
    "strategy": "momentum-breakout",
    "rationale": "Breaking above 4h resistance at 141.80 with volume confirmation",
    "exit_date": "2025-03-10T16:45:00Z",
    "exit_price": 146.20,
    "pnl_sol": 0.648,
    "outcome": "win",
    "lessons": "Held through initial pullback to 143.0, rewarded for patience"
}
```

### Strategy Tagging

Use consistent tags to enable performance attribution:

| Category | Tags |
|----------|------|
| Momentum | `momentum-breakout`, `trend-continuation`, `pullback-entry` |
| Mean Reversion | `range-fade`, `oversold-bounce`, `deviation-snap` |
| Event-Driven | `listing-play`, `catalyst-trade`, `news-reaction` |
| On-Chain | `whale-follow`, `wallet-copy`, `flow-signal` |
| DeFi | `lp-entry`, `yield-farm`, `arb-capture` |

### Rationale Templates

Write rationale **before** entering. Templates by setup type:

```
Momentum: "[Token] breaking [level] on [timeframe] with [confirmation]. Target [price], stop [price]."
Mean Reversion: "[Token] at [X] std devs from [mean] on [timeframe]. Expecting reversion to [target]."
On-Chain: "[Signal type] detected — [wallet/flow description]. Historical hit rate [X]%."
```

## Storage Format

The journal uses JSON for structured querying and CSV for spreadsheet compatibility.

### JSON Format (Primary)

```json
{
  "journal_version": "1.0",
  "trader_id": "anon",
  "trades": [
    {
      "id": "T-20250310-001",
      "token": "SOL",
      "direction": "long",
      "entry_date": "2025-03-10T14:30:00Z",
      "entry_price": 142.50,
      "size_sol": 5.0,
      "size_usd": 712.50,
      "strategy": "momentum-breakout",
      "setup_quality": 8,
      "rationale": "Breaking above 4h resistance with volume",
      "exit_date": "2025-03-10T16:45:00Z",
      "exit_price": 146.20,
      "pnl_sol": 0.648,
      "pnl_pct": 2.60,
      "outcome": "win",
      "hold_time_minutes": 135,
      "emotional_state": "calm",
      "lessons": "Patience through pullback paid off",
      "tags": ["high-conviction", "clean-setup"]
    }
  ]
}
```

### CSV Format (Export)

```
id,token,direction,entry_date,entry_price,size_sol,strategy,exit_date,exit_price,pnl_sol,pnl_pct,outcome,lessons
T-20250310-001,SOL,long,2025-03-10T14:30:00Z,142.50,5.0,momentum-breakout,2025-03-10T16:45:00Z,146.20,0.648,2.60,win,"Patience paid off"
```

## Analytics from Journal Data

### Win Rate by Strategy

```python
from collections import Counter

def win_rate_by_strategy(trades: list[dict]) -> dict[str, float]:
    """Compute win rate grouped by strategy tag."""
    strategy_outcomes: dict[str, list[str]] = {}
    for t in trades:
        strat = t["strategy"]
        strategy_outcomes.setdefault(strat, []).append(t["outcome"])

    return {
        strat: outcomes.count("win") / len(outcomes)
        for strat, outcomes in strategy_outcomes.items()
        if len(outcomes) >= 5  # minimum sample size
    }
```

### Performance by Time of Day

```python
from datetime import datetime

def pnl_by_hour(trades: list[dict]) -> dict[int, float]:
    """Aggregate P&L by entry hour (UTC)."""
    hourly: dict[int, float] = {}
    for t in trades:
        hour = datetime.fromisoformat(t["entry_date"].rstrip("Z")).hour
        hourly[hour] = hourly.get(hour, 0.0) + t.get("pnl_sol", 0.0)
    return dict(sorted(hourly.items()))
```

### Profit Factor by Token Type

```python
def profit_factor(trades: list[dict], group_key: str = "token") -> dict[str, float]:
    """Compute profit factor (gross wins / gross losses) by grouping key."""
    groups: dict[str, dict[str, float]] = {}
    for t in trades:
        key = t.get(group_key, "unknown")
        groups.setdefault(key, {"wins": 0.0, "losses": 0.0})
        pnl = t.get("pnl_sol", 0.0)
        if pnl > 0:
            groups[key]["wins"] += pnl
        else:
            groups[key]["losses"] += abs(pnl)

    return {
        k: v["wins"] / v["losses"] if v["losses"] > 0 else float("inf")
        for k, v in groups.items()
    }
```

## Behavioral Pattern Detection

The journal enables detection of destructive trading patterns. See `references/review_framework.md` for the full framework.

### Revenge Trading

Rapid re-entry after a loss, often with larger size:

```python
def detect_revenge_trades(trades: list[dict], max_gap_minutes: int = 15) -> list[dict]:
    """Find trades entered within max_gap_minutes of a losing exit."""
    sorted_trades = sorted(trades, key=lambda t: t["entry_date"])
    revenge = []
    for i in range(1, len(sorted_trades)):
        prev, curr = sorted_trades[i - 1], sorted_trades[i]
        if prev["outcome"] == "loss":
            prev_exit = datetime.fromisoformat(prev["exit_date"].rstrip("Z"))
            curr_entry = datetime.fromisoformat(curr["entry_date"].rstrip("Z"))
            gap = (curr_entry - prev_exit).total_seconds() / 60
            if gap <= max_gap_minutes:
                revenge.append(curr)
    return revenge
```

### FOMO Detection

Entering after large moves without proper setup:

- Entry rationale is vague or missing
- Setup quality self-rated below 5/10
- Entry during a move that already exceeded 1 ATR

### Cutting Winners / Riding Losers

```python
def winner_loser_hold_times(trades: list[dict]) -> dict[str, float]:
    """Compare average hold time for wins vs losses."""
    win_times = [t["hold_time_minutes"] for t in trades if t["outcome"] == "win"]
    loss_times = [t["hold_time_minutes"] for t in trades if t["outcome"] == "loss"]
    return {
        "avg_win_hold_min": sum(win_times) / len(win_times) if win_times else 0,
        "avg_loss_hold_min": sum(loss_times) / len(loss_times) if loss_times else 0,
    }
    # RED FLAG: if avg_loss_hold > avg_win_hold, you're cutting winners and riding losers
```

### Tilt Detection

Size escalation after losses suggests emotional trading:

```python
def detect_tilt(trades: list[dict], threshold: float = 1.5) -> list[dict]:
    """Flag trades where size increased >threshold after a loss."""
    tilt_trades = []
    for i in range(1, len(trades)):
        prev, curr = trades[i - 1], trades[i]
        if prev["outcome"] == "loss" and curr["size_sol"] > prev["size_sol"] * threshold:
            tilt_trades.append(curr)
    return tilt_trades
```

## Review Cadence

### Daily Review (5 minutes)

- How many trades today? P&L?
- Did I follow my rules on every trade?
- Any emotional decisions?
- One thing I did well, one thing to improve

### Weekly Review (30 minutes)

- Win rate and profit factor by strategy
- Behavioral pattern check (revenge trades, tilt, FOMO)
- Best and worst trade of the week — what made them different?
- Strategy performance vs. expectations
- Adjust position sizing if needed

### Monthly Review (2 hours)

- Full strategy attribution analysis
- Equity curve review — drawdown periods and recovery
- Compare actual vs. planned risk per trade
- Performance by token type, time of day, day of week
- Are any strategies consistently losing? Consider dropping them
- Review and update strategy parameters

See `references/review_framework.md` for detailed review checklists and questions.

## Partial Exits and Scaled Entries

Real trading involves scaling in and out. The journal handles this with child records:

```python
# Parent trade with two scale-out exits
parent = {
    "id": "T-20250310-001",
    "token": "BONK",
    "direction": "long",
    "entry_date": "2025-03-10T14:30:00Z",
    "entry_price": 0.000023,
    "size_sol": 10.0,
    "strategy": "momentum-breakout",
    "exits": [
        {"date": "2025-03-10T15:00:00Z", "price": 0.000025, "size_pct": 50, "reason": "first-target"},
        {"date": "2025-03-10T16:30:00Z", "price": 0.000028, "size_pct": 50, "reason": "trailing-stop"},
    ]
}
```

See `references/record_format.md` for full documentation of partial exit handling.

## Files

### References
- `references/record_format.md` — Complete 18-field trade record schema, field descriptions, tagging taxonomy, CSV/JSON examples, partial exit handling
- `references/review_framework.md` — Daily/weekly/monthly review checklists, behavioral red flags, performance decay detection

### Scripts
- `scripts/trade_logger.py` — CLI trade logger: add, list, update, compute stats, filter, demo mode (stdlib only)
- `scripts/journal_analyzer.py` — Journal analysis: strategy performance, behavioral patterns, time-based analysis, demo mode (stdlib only)

## Dependencies

Both scripts use Python standard library only (`json`, `datetime`, `argparse`, `collections`). No external packages required.

```bash
# No installation needed — stdlib only
python scripts/trade_logger.py --demo
python scripts/journal_analyzer.py --demo
```

## Disclaimer

This skill provides tools for trade record-keeping and performance analysis. It does not provide financial advice, trading recommendations, or guarantee any trading outcomes. All analysis is informational and for personal review purposes only.
