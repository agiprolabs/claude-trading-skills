---
name: strategy-framework
description: Standardized template for defining trading strategies with entry rules, exit rules, position sizing, risk parameters, and performance criteria
---

# Strategy Framework

A standardized system for defining, documenting, testing, and managing trading strategies. This skill provides templates and tools that enforce discipline, enable reproducibility, and make strategies testable.

## Why a Strategy Framework Matters

Trading without a written strategy framework leads to:
- **Inconsistency**: ad-hoc decisions driven by emotion rather than rules
- **Untestability**: vague ideas that cannot be backtested or evaluated
- **Scope creep**: strategies that drift without version-controlled definitions
- **Unmanaged risk**: missing stop losses, position limits, or drawdown halts

A strategy framework forces you to:
1. State a falsifiable hypothesis about a market inefficiency
2. Define precise, machine-testable entry and exit rules
3. Specify position sizing and risk parameters before trading
4. Set minimum performance criteria for continuation or retirement
5. Track changes through versioned strategy documents

## Strategy Definition Template

Every strategy must be documented using the standard template. The full copy-paste template is in `references/strategy_template.md`.

### Core Sections

**Identity**
```
Name: SOL-EMA-Cross v1.0
Asset class: Solana tokens (top 50 by 24h volume)
Timeframe: Primary 1H, confirmation 4H
Style: Trend following
```

**Edge Hypothesis**: State what market inefficiency you are exploiting and why it exists.

```
Hypothesis: Solana mid-cap tokens exhibit momentum persistence
on the 1H timeframe due to retail herding behavior and low
institutional participation. EMA crossovers capture the
initiation of these trends.
```

**Entry Rules**: Specific, testable conditions combined with AND/OR logic.

```python
def entry_signal(data: pd.DataFrame) -> bool:
    """All conditions must be True (AND logic)."""
    ema_cross = data["ema_12"] > data["ema_26"]  # EMA 12 crossed above 26
    ema_rising = data["ema_26"].diff(3) > 0       # 26 EMA trending up
    volume_ok = data["volume"] > data["vol_sma_20"] * 1.5  # Volume confirmation
    regime_ok = data["adx"] > 20                  # Trending regime
    return ema_cross & ema_rising & volume_ok & regime_ok
```

**Exit Rules**: Every strategy needs multiple exit mechanisms.

| Exit Type | Method | Parameters |
|-----------|--------|------------|
| Stop Loss | ATR-based | 2.0 × ATR(14) below entry |
| Take Profit | Risk multiple | 3.0 × risk (3:1 R:R) |
| Trailing Stop | Chandelier | 3.0 × ATR(14) from highest high |
| Time Stop | Bar count | Close if flat after 20 bars |
| Signal Exit | EMA reversal | EMA 12 crosses below EMA 26 |

**Position Sizing**: Method and parameters. See the `position-sizing` skill for details.

```python
risk_per_trade = 0.02        # 2% of portfolio
stop_distance_pct = 0.05     # 5% from entry (ATR-derived)
position_size = (portfolio * risk_per_trade) / stop_distance_pct
```

**Risk Parameters**: Portfolio-level guardrails. See the `risk-management` skill.

```
Max concurrent positions: 5
Risk per trade: 2% of portfolio
Daily loss limit: 5% of portfolio
Max drawdown halt: 15% — stop trading, review strategy
Correlated exposure limit: 10% (e.g., meme tokens combined)
```

**Filters**: Conditions that prevent entry even if signals fire.

```python
def filters_pass(token: dict, market: dict) -> bool:
    """All filters must pass before entry is allowed."""
    volume_ok = token["volume_24h"] > 500_000      # Min $500K volume
    liquidity_ok = token["liquidity"] > 100_000    # Min $100K liquidity
    age_ok = token["age_days"] > 7                 # Not brand new
    holders_ok = token["holder_count"] > 500       # Sufficient distribution
    regime_ok = market["regime"] != "crisis"       # No crisis regime
    return all([volume_ok, liquidity_ok, age_ok, holders_ok, regime_ok])
```

**Performance Criteria**: When to continue, review, or retire.

```
Continue: Sharpe > 1.0, PF > 1.5, Win Rate > 40%, MDD < 20%
Review:   Any metric degrades 25% from baseline
Retire:   Rolling 30-day Sharpe < 0, or 3 consecutive losing months
```

## Strategy Lifecycle

### 1. Hypothesis

Identify a market inefficiency and explain why it exists and why it might persist.

**Good hypothesis**: "New PumpFun tokens that reach 80+ SOL in bonding curve within 10 minutes have a 65% probability of graduating to Raydium, creating a predictable price spike at graduation."

**Bad hypothesis**: "SOL will go up." (Not specific, not testable, no edge identified.)

### 2. Definition

Write the full strategy document using the template in `references/strategy_template.md`. Every field must be filled. If you cannot fill a field, the strategy is not ready.

### 3. Backtest

Test on historical data using `vectorbt` or equivalent. Requirements:
- Minimum 100 trades in the test period
- Use walk-forward validation (train on 70%, test on 30%)
- Account for slippage and fees (see `slippage-modeling` skill)
- Report both in-sample and out-of-sample metrics

### 4. Paper Trade

Run the strategy in simulation for at least 2 weeks (or 30 trades, whichever is longer).
- Compare paper results to backtest expectations
- If results differ by more than 25%, investigate before proceeding

### 5. Small Live

Trade with minimum viable size (enough to cover fees, small enough to be inconsequential).
- Run for at least 30 trades
- Compare to paper trade results

### 6. Scale

If small-live metrics match expectations (within 25% of backtest):
- Increase position size gradually (25% increments per week)
- Monitor metrics continuously

### 7. Monitor

Ongoing performance tracking:
- Daily: P&L, trade count, win rate
- Weekly: Sharpe ratio, profit factor, drawdown
- Monthly: Full strategy review against performance criteria

### 8. Retire

Stop using a strategy when:
- Rolling 30-day Sharpe drops below 0
- Three consecutive losing months
- Market regime permanently shifts (e.g., regulatory change)
- A better strategy replaces it for the same edge

## Strategy Evaluation Criteria

Minimum thresholds before a strategy should be traded live:

| Metric | Trend Following | Mean Reversion | Scalping |
|--------|----------------|----------------|----------|
| Min Trades | 100 | 100 | 500 |
| Sharpe (OOS) | > 1.0 | > 1.0 | > 1.5 |
| Profit Factor | > 1.5 | > 1.5 | > 1.3 |
| Max Drawdown | < 20% | < 15% | < 10% |
| Win Rate | > 35% | > 55% | > 55% |
| Avg Win/Avg Loss | > 2.0 | > 1.0 | > 1.0 |

## Strategy Types for Crypto

Detailed descriptions of each strategy type are in `references/strategy_types.md`.

### Momentum / Trend Following
- **Edge**: Price trends persist due to behavioral biases and information asymmetry
- **Indicators**: EMA crossovers, SuperTrend, ADX, MACD
- **Win rate**: 35-45%, relies on large winners
- **Best regime**: Trending markets with moderate volatility

### Mean Reversion
- **Edge**: Price oscillates around equilibrium due to overreaction
- **Indicators**: RSI, Bollinger Bands, z-score, VWAP deviation
- **Win rate**: 55-65%, relies on high win rate with smaller gains
- **Best regime**: Ranging markets with low-moderate volatility

### Breakout
- **Edge**: Compressed volatility leads to directional expansion
- **Indicators**: Bollinger Band squeeze, Donchian channels, volume breakout
- **Win rate**: 30-40%, relies on catching large moves
- **Best regime**: Transitioning from low to high volatility

### Copy Trading / Wallet Following
- **Edge**: Skilled wallets have informational or analytical advantages
- **Indicators**: Wallet PnL history, trade frequency, token selection
- **Win rate**: Depends on followed wallet quality
- **Best regime**: Any (depends on followed wallet's strategy)

### PumpFun Sniping
- **Edge**: Predictable price dynamics around token creation and graduation
- **Strategies**: Creation snipe, volume confirmation, graduation play
- **Win rate**: Highly variable (20-60% depending on approach)
- **Best regime**: High retail activity periods

### Arbitrage
- **Edge**: Price discrepancies across DEXs or between spot and perpetuals
- **Indicators**: Price feeds from multiple venues, funding rates
- **Win rate**: > 80% when executed correctly
- **Best regime**: High volatility, fragmented liquidity

### Market Making
- **Edge**: Capturing bid-ask spread while managing inventory risk
- **Indicators**: Order book depth, volatility, inventory position
- **Win rate**: > 60%, relies on volume and spread capture
- **Best regime**: Stable markets with consistent volume

## Common Strategy Mistakes

1. **No written rules**: Trading on intuition, unable to backtest or reproduce
2. **Curve fitting**: Optimizing parameters until backtest looks perfect, fails live
3. **Missing stops**: "I'll exit when it feels right" leads to catastrophic losses
4. **Ignoring regime**: Using a trend strategy in a ranging market (or vice versa)
5. **Survivorship bias**: Only backtesting tokens that still exist
6. **Lookahead bias**: Using future information in backtest signals
7. **Ignoring costs**: Not accounting for slippage, fees, and market impact
8. **Over-trading**: Entering on marginal signals to "stay active"
9. **Strategy hopping**: Abandoning strategies after normal losing streaks
10. **No retirement plan**: Continuing to trade a broken strategy out of attachment

## Integration with Other Skills

| Skill | Integration |
|-------|------------|
| `vectorbt` | Backtest strategy definitions programmatically |
| `pandas-ta` | Compute technical indicators for entry/exit signals |
| `regime-detection` | Market regime filters for strategy activation |
| `exit-strategies` | Detailed exit rule implementation |
| `position-sizing` | Position size calculation methods |
| `risk-management` | Portfolio-level risk parameter enforcement |
| `slippage-modeling` | Realistic execution cost estimation |
| `feature-engineering` | ML feature computation from strategy signals |

## Files

### References
- `references/strategy_template.md` — Complete copy-paste strategy definition template
- `references/strategy_types.md` — Detailed guide to each strategy type with parameters and examples

### Scripts
- `scripts/define_strategy.py` — Interactive strategy definition tool with `--demo` mode
- `scripts/strategy_scorecard.py` — Strategy evaluation scorecard with GO/REVIEW/NO-GO recommendations
