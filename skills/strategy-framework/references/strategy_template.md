# Strategy Definition Template

Copy this template and fill in every section. If you cannot fill a section, the strategy is not ready for testing.

## Template

```markdown
# Strategy: [Name] v[X.Y]

## Overview
- **Asset class**: [e.g., Solana tokens, top 50 by 24h volume]
- **Timeframe**: Primary [1H], Confirmation [4H]
- **Style**: [Trend following / Mean reversion / Breakout / Scalping / Other]
- **Edge hypothesis**: [One paragraph: what inefficiency exists and why it persists]

## Entry Rules

All conditions use AND logic unless noted otherwise.

- Condition 1: [specific, testable — e.g., EMA(12) > EMA(26)]
- Condition 2: [specific, testable — e.g., ADX > 20]
- Condition 3: [specific, testable — e.g., Volume > 1.5x 20-period SMA]
- Condition 4 (optional): [additional confirmation]

**Entry logic**: ALL of conditions 1-3 must be True (AND)

**Entry execution**:
- Order type: [Market / Limit at bid+X bps]
- Slippage tolerance: [X bps]
- Max entry time: [fill within N seconds or cancel]

## Exit Rules

### Stop Loss
- **Method**: [Fixed % / ATR-based / Support level / Volatility-adjusted]
- **Parameters**: [e.g., 2.0 × ATR(14) below entry]
- **Hard stop**: [absolute max loss per trade, e.g., 3% of portfolio]

### Take Profit
- **Method**: [Fixed R:R / Resistance level / Indicator target]
- **Parameters**: [e.g., 3.0 × risk distance above entry]
- **Partial exits**: [e.g., 50% at 2R, 50% at 3R]

### Trailing Stop
- **Method**: [Chandelier / Percentage / Parabolic SAR / ATR trail]
- **Parameters**: [e.g., 3.0 × ATR(14) from highest high since entry]
- **Activation**: [e.g., activate after 1.5R profit reached]

### Time Stop
- **Trigger**: [e.g., close position if flat (< 0.5R move) after 20 bars]
- **Rationale**: [capital is better deployed elsewhere if no movement]

### Signal Exit
- **Condition**: [e.g., EMA(12) crosses below EMA(26)]
- **Overrides**: [does this override trailing stop? take profit?]

### Exit Priority
1. Hard stop loss (always honored)
2. Signal exit
3. Trailing stop
4. Take profit
5. Time stop

## Position Sizing

- **Method**: [Fixed fractional / Volatility-adjusted / Kelly criterion]
- **Risk per trade**: [X% of portfolio]
- **Calculation**:
  ```
  position_size = (portfolio_value × risk_per_trade) / stop_distance
  ```
- **Max position**: [Y% of portfolio in any single trade]
- **Min position**: [Z SOL or $W — must cover fees]

## Risk Parameters

- **Max concurrent positions**: [N]
- **Max correlated positions**: [M positions in same sector/narrative]
- **Daily loss limit**: [X% — stop trading for the day if hit]
- **Weekly loss limit**: [Y% — reduce size by 50% if hit]
- **Max drawdown halt**: [Z% — stop trading entirely, review strategy]
- **Correlated exposure limit**: [W% of portfolio in correlated assets]

## Filters

Conditions that prevent entry even when signals fire.

### Market Filters
- **Regime filter**: [e.g., only trade when ADX > 20 (trending)]
- **Volatility filter**: [e.g., skip if ATR/price > 15% (too volatile)]
- **Correlation filter**: [e.g., skip if BTC correlation > 0.9 during BTC downtrend]

### Token Filters
- **Volume filter**: [minimum 24h volume, e.g., > $500K]
- **Liquidity filter**: [minimum pool liquidity, e.g., > $100K]
- **Age filter**: [minimum token age, e.g., > 7 days]
- **Holder filter**: [minimum holder count, e.g., > 500]
- **Concentration filter**: [top 10 holders < 50% of supply]

### Time Filters
- **Active hours**: [e.g., 08:00-22:00 UTC only]
- **Day filter**: [e.g., avoid weekends for low-liquidity tokens]
- **Event filter**: [e.g., avoid 1H before/after major announcements]

## Performance Criteria

### Continue Trading
- Rolling 30d Sharpe > [1.0]
- Rolling 30d Profit Factor > [1.5]
- Rolling 30d Win Rate > [40%]
- Max drawdown from peak < [20%]

### Review Required
- Any metric degrades [25%] from baseline
- Three consecutive losing weeks
- Significant market regime change detected

### Retire Strategy
- Rolling 30d Sharpe < [0] for [2 consecutive weeks]
- Three consecutive losing months
- Max drawdown halt triggered [twice in 30 days]
- Fundamental edge no longer exists (e.g., protocol change)

## Backtest Results

### In-Sample (Training Period)
- **Period**: [YYYY-MM-DD to YYYY-MM-DD]
- **Total return**: [X%]
- **Sharpe ratio**: [X.XX]
- **Max drawdown**: [X%]
- **Win rate**: [X%]
- **Profit factor**: [X.XX]
- **Trade count**: [N]
- **Avg trade duration**: [N bars]

### Out-of-Sample (Test Period)
- **Period**: [YYYY-MM-DD to YYYY-MM-DD]
- **Total return**: [X%]
- **Sharpe ratio**: [X.XX]
- **Max drawdown**: [X%]
- **Win rate**: [X%]
- **Profit factor**: [X.XX]
- **Trade count**: [N]
- **Degradation from IS**: [X% Sharpe drop, X% PF drop]

### Paper Trade Results
- **Period**: [YYYY-MM-DD to YYYY-MM-DD]
- **Total return**: [X%]
- **Comparison to OOS**: [within X% — acceptable / needs investigation]

## Dependencies
- Data source: [e.g., Birdeye API, DexScreener]
- Indicators: [e.g., pandas-ta EMA, ADX, ATR]
- Execution: [e.g., Jupiter API via jupiter-swap skill]
- Risk: [e.g., position-sizing skill, risk-management skill]

## Notes
- [Any additional context, known limitations, or observations]

## Change Log
- **v1.0** [YYYY-MM-DD]: Initial strategy definition
- **v1.1** [YYYY-MM-DD]: [Description of changes and reason]
```

## Usage Notes

1. **Fill every field**: Empty fields indicate an incomplete strategy. Do not trade an incomplete strategy.
2. **Be specific**: "Buy when RSI is low" is not testable. "Buy when RSI(14) < 30 AND price > EMA(200)" is testable.
3. **Version your changes**: Every parameter change gets a new version number and changelog entry.
4. **Keep it updated**: After backtesting and paper trading, fill in the results sections.
5. **One strategy per document**: Do not combine multiple strategies in one template.
