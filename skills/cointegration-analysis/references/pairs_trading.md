# Pairs Trading — Framework Reference

## Pair Selection

### Screening Pipeline

1. **Universe definition**: Select liquid tokens with sufficient history (>200 days)
2. **Correlation filter**: Pearson correlation > 0.7 on log prices
3. **Cointegration test**: Engle-Granger p < 0.05 (test both directions)
4. **Spread quality**: Half-life between 5–60 days, Hurst < 0.5
5. **Stability check**: Rolling cointegration p < 0.05 for >80% of windows

### Candidate Ranking

Rank surviving pairs by:
- Lower cointegration p-value (stronger relationship)
- Lower Hurst exponent (stronger mean reversion)
- Shorter half-life (faster convergence)
- Higher spread Sharpe ratio (historical profitability)

## Position Sizing

### Equal Dollar Notional

The standard approach: invest $N long and $N short, adjusted by hedge ratio.

```
Long leg:  Buy Q_y units of Y at price P_y  → notional = Q_y * P_y
Short leg: Sell Q_x units of X at price P_x → notional = Q_x * P_x

Constraint: Q_y * P_y = β * Q_x * P_x
```

where β is the cointegration hedge ratio.

### Practical Sizing

```python
def size_pairs_trade(
    y_price: float,
    x_price: float,
    hedge_ratio: float,
    capital: float,
    max_position_pct: float = 0.10,
) -> tuple[float, float]:
    """Calculate position sizes for a pairs trade.

    Args:
        y_price: Current price of long leg.
        x_price: Current price of short leg.
        hedge_ratio: Cointegration hedge ratio (β).
        capital: Total portfolio capital.
        max_position_pct: Maximum capital per leg as fraction.

    Returns:
        Tuple of (quantity_y, quantity_x).
    """
    leg_capital = capital * max_position_pct
    qty_y = leg_capital / y_price
    qty_x = (qty_y * hedge_ratio * y_price) / x_price
    return qty_y, qty_x
```

## Entry and Exit Rules

### Z-Score Based Entry

Compute the spread z-score using a rolling window:

```
spread_t = Y_t - β * X_t - α
z_t = (spread_t - μ_rolling) / σ_rolling
```

| Signal | Condition | Action |
|---|---|---|
| Long spread | z < -2.0 | Buy Y, sell X |
| Short spread | z > +2.0 | Sell Y, buy X |
| Exit long | z > -0.5 (or z = 0) | Close both legs |
| Exit short | z < +0.5 (or z = 0) | Close both legs |
| Stop loss | \|z\| > 3.0 | Close both legs |
| Time stop | Holding > 2× half-life | Close both legs |

### Entry Threshold Selection

- **Conservative (z = ±2.5)**: Fewer trades, higher win rate, wider stops
- **Standard (z = ±2.0)**: Balanced frequency and profitability
- **Aggressive (z = ±1.5)**: More trades, lower win rate, tighter spread

The threshold should scale with spread volatility. In crypto markets with
higher volatility, use wider thresholds (±2.0 to ±2.5).

### Exit Refinements

- **Partial exit**: Close half at z = ±1.0, remainder at z = 0
- **Trailing exit**: Exit when z crosses back through ±1.0 after hitting ±0.5
- **Profit target**: Close if unrealized P&L exceeds 2× transaction costs

## Risk Management

### Market Neutrality

A properly constructed pairs trade should be approximately market-neutral:

```
Portfolio β ≈ β_y * w_y + β_x * w_x ≈ 0
```

where β_y and β_x are market betas and w_y, w_x are signed weights.

Monitor net market exposure daily. If the legs' market betas diverge, the
position gains directional risk.

### Spread Risk

The spread can widen further before reverting. Key risk metrics:

- **Maximum historical divergence**: Worst-case spread widening in backtest
- **Spread VaR**: Value at risk of the spread position
- **Drawdown duration**: How long spreads have stayed diverged historically

### Capital Requirements

Each leg requires capital (or margin). For a fully funded pairs trade:

```
Capital required = Notional_long + Notional_short + buffer
Buffer = 20-30% of total notional for adverse moves
```

### Transaction Cost Budget

Four transactions per round trip:

| Transaction | Cost |
|---|---|
| Enter long leg | ~0.3% |
| Enter short leg | ~0.3% |
| Exit long leg | ~0.3% |
| Exit short leg | ~0.3% |
| **Total round trip** | **~1.2%** |

The expected spread convergence must exceed 1.2% after costs to be profitable.
With z-score entry at ±2.0 and exit at 0, the expected move is 2σ of the
spread. If σ is small relative to costs, the pair is not tradeable.

### Stop Loss Rules

1. **Z-score stop**: Close if |z| > 3.0 (spread is >3σ diverged)
2. **Dollar stop**: Close if combined loss exceeds 2% of portfolio
3. **Time stop**: Close if position open longer than 2× half-life
4. **Cointegration break**: Close if rolling p-value > 0.10

## Performance Metrics

### Spread-Level Metrics

- **Spread Sharpe ratio**: annualized return / annualized volatility of spread
- **Maximum spread divergence**: largest |z| observed during trade
- **Average convergence time**: mean bars from entry to exit
- **Mean reversion ratio**: fraction of trades that converge

### Strategy-Level Metrics

- **Win rate**: percentage of trades with positive P&L (target: >55%)
- **Profit factor**: gross profit / gross loss (target: >1.5)
- **Average P&L per trade**: net of transaction costs
- **Maximum drawdown**: largest peak-to-trough decline
- **Sharpe ratio**: annualized (target: >1.0 for pairs strategies)
- **Number of trades**: sufficient for statistical significance (>30)

### Comparison Benchmarks

Always compare pairs strategy against:
- Buy-and-hold each leg individually
- Equal-weight long both legs
- Risk-free rate

## Monitoring and Maintenance

### Daily Checks

1. **Cointegration p-value**: Recompute on trailing 60-day window
2. **Hedge ratio drift**: Compare current vs estimation-period ratio
3. **Spread z-score**: Current position in spread distribution
4. **Market exposure**: Net beta of the combined position

### Re-Estimation Triggers

Re-estimate the hedge ratio when:
- Rolling p-value exceeds 0.05 for 5+ consecutive days
- Hedge ratio drifts >15% from estimation value
- Half-life doubles or halves from estimated value

### Pair Abandonment Criteria

Stop trading a pair when:
- Rolling p-value > 0.10 for 10+ consecutive days
- Fundamental change in one of the tokens (tokenomics, protocol upgrade)
- Sustained spread divergence beyond 4σ
- Half-life exceeds 120 days (too slow to be tradeable)

## Crypto-Specific Considerations

### 24/7 Markets

- No overnight gaps — reduces gap risk vs traditional pairs
- Continuous monitoring required (or automated execution)
- Wider intraday volatility requires wider z-score thresholds

### Higher Volatility

- Spreads move faster → shorter half-lives possible
- But also more false signals → wider entry thresholds recommended
- Position size should be reduced relative to equity markets

### DEX Execution

- Both legs should ideally execute atomically to avoid leg risk
- On Solana, use transaction bundles when possible
- Slippage varies by token liquidity — check both legs
- Consider using Jupiter aggregator for best execution

### Funding Rate Arbitrage

A special form of pairs trading:
- Long spot + short perpetual (or vice versa)
- Profit from funding rate payments
- Conceptually similar: the "spread" is the funding rate
- Lower risk than cross-asset pairs (same underlying)

## Example: SOL vs ETH Pairs Trade

```python
# Conceptual workflow — see scripts/pairs_backtest.py for runnable code
# 1. Fetch daily close prices for SOL and ETH (200+ days)
# 2. Test cointegration
t_stat, p_value, _ = coint(sol_prices, eth_prices)
if p_value < 0.05:
    # 3. Estimate hedge ratio
    slope, intercept, _, _, _ = linregress(eth_prices, sol_prices)
    # 4. Compute spread
    spread = sol_prices - slope * eth_prices - intercept
    z = (spread - spread.mean()) / spread.std()
    # 5. Generate signals
    long_signal = z < -2.0   # SOL undervalued vs ETH
    short_signal = z > 2.0   # SOL overvalued vs ETH
```

This is for informational and analytical purposes only. It does not constitute
financial advice or a recommendation to trade.
