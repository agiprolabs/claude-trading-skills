---
name: risk-management
description: Portfolio-level risk controls, drawdown management, exposure limits, and circuit breakers for crypto trading
---

# Risk Management

Portfolio-level risk controls for crypto and Solana trading. This skill provides frameworks for drawdown management, exposure limits, circuit breakers, and crypto-specific risk considerations.

## Risk Management Hierarchy

Every decision must respect this priority order:

1. **Survival** — Never risk account ruin. No single trade, day, or week should threaten your ability to continue trading.
2. **Capital preservation** — Protect what you have. Losses compound geometrically; recovery requires outsized gains.
3. **Growth** — Only after survival and preservation are secured, pursue returns.

Violating this hierarchy (chasing growth at the expense of survival) is the primary cause of account blowups.

## Portfolio-Level Controls

### 1. Maximum Drawdown Limits

Halt trading when portfolio drawdown from equity peak reaches a threshold:

| Account Type | Max Drawdown | Action |
|---|---|---|
| Conservative | -15% | Full stop, review all strategies |
| Moderate | -20% | Full stop, reduce to minimum size on recovery |
| Aggressive | -25% | Full stop, mandatory cooling period |

Recovery math makes this critical: a -20% drawdown requires +25% to recover. A -50% drawdown requires +100%. See `references/drawdown_management.md` for the full recovery table.

### 2. Daily Loss Limits

Stop opening new positions after daily P&L (realized + unrealized) hits:

- **Conservative**: -3% of account
- **Moderate**: -4% of account
- **Aggressive**: -5% of account

Reset at midnight UTC. Three consecutive days hitting the daily limit triggers a weekly halt.

### 3. Weekly Loss Limits

Reduce size or halt after weekly P&L reaches:

- **Reduce size by 50%**: -5% weekly loss
- **Minimum size only**: -7% weekly loss
- **Full halt**: -10% weekly loss

### 4. Concentration Limits

Maximum allocation to any single dimension:

| Dimension | Max Concentration |
|---|---|
| Single token (blue chip) | 10% of account |
| Single token (mid-cap) | 5% |
| Single token (small-cap) | 2% |
| Single token (PumpFun/micro) | 0.5% |
| Single sector/narrative | 30% |
| Single strategy | 40% |

### 5. Exposure Limits

Total deployed capital constraints:

- **Normal conditions**: 50–80% deployed, 20–50% cash reserve
- **Elevated risk**: 30–50% deployed
- **Drawdown >10%**: 20–30% deployed
- **Max concurrent positions**: 5–10 depending on account size

### 6. Correlation Management

Crypto assets correlate >0.7 during sell-offs. Effective diversification requires:

- Treat all meme tokens as a single correlated bucket
- Limit total meme exposure to one position-size equivalent
- Diversify across *strategies* (trend, mean-reversion, scalp), not just tokens
- Monitor rolling correlation and reduce when correlations spike

See `references/exposure_limits.md` for detailed limits by token type and strategy.

## Drawdown Management

### Response Framework

| Drawdown | Status | Response |
|---|---|---|
| 0–5% | Normal | Continue trading at full size |
| 5–10% | Caution | Reduce position sizes by 25–50% |
| 10–15% | Warning | Minimum position sizes only |
| 15–20% | Critical | Halt new trades, manage existing positions only |
| >20% | Emergency | Full stop, review everything before resuming |

### Recovery Requirements

| Loss | Required Gain to Recover |
|---|---|
| -5% | +5.3% |
| -10% | +11.1% |
| -15% | +17.6% |
| -20% | +25.0% |
| -30% | +42.9% |
| -40% | +66.7% |
| -50% | +100.0% |

The asymmetry accelerates rapidly. Managing small drawdowns prevents them from becoming catastrophic. See `references/drawdown_management.md` for the full framework.

## Circuit Breakers

Automated controls that restrict trading when conditions are met:

### Time-Based
- No trading for 24 hours after hitting daily loss limit
- 48-hour cooling period after weekly loss limit
- Mandatory weekly review day (no new positions)

### Loss-Based
- 3 consecutive losses → reduce size 50%
- 5 consecutive losses → minimum size only
- 7 consecutive losses → halt 24 hours, full review

### Volatility-Based
- Portfolio volatility >2× rolling average → reduce exposure 50%
- Market-wide liquidation events → pause all new entries
- Individual token volatility spike → exit or tighten stops

### Emotional (Self-Assessed)
- Recognize tilt: anger after losses, urge to "make it back"
- FOMO: rushing entries without proper analysis
- Overconfidence: increasing size after a win streak without justification

See `references/circuit_breakers.md` for implementation details.

## Risk Metrics

### Value at Risk (VaR)

95th-percentile daily loss estimate using historical returns:

```python
import numpy as np

def historical_var(returns: list[float], confidence: float = 0.95) -> float:
    """Calculate historical VaR at given confidence level."""
    sorted_returns = sorted(returns)
    index = int((1 - confidence) * len(sorted_returns))
    return abs(sorted_returns[index])

# Example: 95% VaR of 3.2% means on 95% of days, loss won't exceed 3.2%
```

### Expected Shortfall (CVaR)

Average loss in the worst (1 - confidence)% of scenarios:

```python
def expected_shortfall(returns: list[float], confidence: float = 0.95) -> float:
    """Average loss beyond VaR threshold."""
    sorted_returns = sorted(returns)
    index = int((1 - confidence) * len(sorted_returns))
    tail = sorted_returns[:index]
    return abs(sum(tail) / len(tail)) if tail else 0.0
```

### Maximum Drawdown

```python
def max_drawdown(equity_curve: list[float]) -> float:
    """Peak-to-trough decline as a fraction."""
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        dd = (peak - value) / peak
        max_dd = max(max_dd, dd)
    return max_dd
```

### Additional Metrics

- **Win/loss streak tracking**: Detect hot/cold streaks for circuit breaker logic
- **Rolling Sharpe ratio**: 30-day rolling risk-adjusted returns
- **Calmar ratio**: Annualized return / max drawdown
- **Sortino ratio**: Return / downside deviation (penalizes only negative volatility)

## Crypto-Specific Risks

### Smart Contract Risk
- Never allocate >5% of account to a single unaudited protocol
- Diversify across audited protocols for yield strategies
- Monitor exploit databases and social channels for emerging threats

### Rug Pull Risk
- Size inversely with token age: newer tokens get smaller positions
- Verify: locked liquidity, renounced mint authority, holder distribution
- Cross-reference with `token-holder-analysis` skill for red flags

### Bridge and Custody Risk
- Don't hold >20% on any single platform or bridge
- Self-custody the majority of trading capital
- Budget for bridge fees and delays in execution planning

### MEV and Execution Risk
- Budget 1–3% for MEV/slippage on Solana DEX trades
- Use priority fees during congestion
- See `slippage-modeling` skill for detailed cost estimation

### Correlation Spikes
- In crashes, crypto correlations approach 1.0
- Your "diversified" portfolio may behave as one position
- Stress-test portfolio assuming all positions drop simultaneously

## PumpFun Risk Framework

PumpFun and similar meme token platforms require a distinct risk approach:

### Core Principle
Treat every PumpFun trade as a potential 100% loss. Size accordingly.

### Position Limits
- **Per-token maximum**: 0.1–0.5 SOL
- **Daily PumpFun budget**: Fixed allocation (e.g., 2 SOL/day)
- **Never exceed budget**: When daily allocation is gone, stop

### Tracking
- Track PumpFun P&L separately from main portfolio
- Calculate PumpFun win rate and expectancy independently
- Don't let PumpFun losses affect main portfolio risk limits

### Risk Adjustments
- No stop-losses on PumpFun (assume 100% loss at entry)
- Take profits aggressively: 2×, 3×, 5× partial exits
- Time-based exit: close within hours, not days

## Integration with Other Skills

- **`position-sizing`**: Use risk limits from this skill to constrain position sizes
- **`exit-strategies`**: Circuit breakers override exit strategies (forced exits)
- **`portfolio-analytics`**: Feed portfolio metrics back for risk assessment
- **`liquidity-analysis`**: Adjust position limits based on available liquidity
- **`slippage-modeling`**: Factor execution costs into risk calculations

## Files

### References
- `references/drawdown_management.md` — Drawdown math, response framework, causes, and remediation
- `references/exposure_limits.md` — Position limits by token type, portfolio limits, correlation management
- `references/circuit_breakers.md` — Implementation details for all circuit breaker types

### Scripts
- `scripts/risk_dashboard.py` — Portfolio risk dashboard with limit checking and color-coded status
- `scripts/drawdown_analyzer.py` — Equity curve drawdown analysis with response recommendations

## Quick Start

```bash
# Run the risk dashboard with demo data
python scripts/risk_dashboard.py --demo

# Analyze drawdowns on a demo equity curve
python scripts/drawdown_analyzer.py --demo
```
