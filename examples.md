# Workflow Examples

This document provides detailed, practical examples demonstrating how to combine trading skills to solve real trading and DeFi analysis problems.

> **Always start with:** "Use available skills when possible. Keep the output organized."

---

## Example 1: Pre-Trade Token Analysis

**Objective**: Evaluate a newly graduated Solana token before entering a position.

**Prompt**:
```
Use available skills. Analyze this token [MINT_ADDRESS] for potential entry:
1. Get current price, 24h volume, market cap from Birdeye
2. Check holder distribution — top 10/20/50 concentration, Gini coefficient
3. Analyze liquidity depth across all DEX pools
4. Is the deployer wallet still holding? Any insider concentration?
5. Compute RSI, MACD, Bollinger Bands on 15m candles
6. Estimate slippage for 0.5 SOL and 2 SOL entries
7. Suggest position size assuming 100 SOL portfolio, 2% risk per trade
8. Give me a risk score (1-10) with reasoning
```

**Skills Used**: birdeye-api, token-holder-analysis, liquidity-analysis, dex-pool-analysis, solana-onchain, pandas-ta, slippage-modeling, position-sizing, risk-management

**Expected Output**: Structured report with data tables, indicator charts, risk assessment, and position size recommendation with disclaimer.

---

## Example 2: Momentum Strategy Backtest

**Objective**: Test a multi-timeframe momentum strategy on SOL.

**Prompt**:
```
Use available skills. Backtest this strategy on SOL/USDC:

Entry: Daily close above 20-EMA AND RSI(14) > 50 AND 4h MACD histogram positive
Exit: Trailing stop at 2x ATR(14) from high, or RSI > 80, or 20-EMA cross below
Position sizing: 2% risk based on ATR stop distance

Use 12 months of data. Report: equity curve, drawdown chart, monthly returns table,
Sharpe ratio, max drawdown, win rate, profit factor, average trade duration.
Compare against buy-and-hold SOL over the same period.
```

**Skills Used**: birdeye-api, ohlcv-processing, pandas-ta, strategy-framework, vectorbt, portfolio-analytics, trading-visualization

---

## Example 3: DeFi Yield Farm Evaluation

**Objective**: Find and evaluate the best SOL yield opportunity.

**Prompt**:
```
Use available skills. I have 10 SOL to deploy in DeFi yield. Evaluate:

1. Get all SOL LP pools from DeFiLlama with >$100k TVL
2. For the top 5 by APY, calculate:
   - Real yield (fees only) vs nominal yield (with emissions)
   - Impermanent loss at ±10%, ±25%, ±50% price moves
   - Net APY after IL for each scenario
   - MEV risk assessment
3. Compare against simply staking SOL
4. Rank by risk-adjusted net yield
5. Show me a comparison table and a visualization
```

**Skills Used**: defillama-api, dex-pool-analysis, lp-math, impermanent-loss, yield-analysis, mev-analysis, trading-visualization

---

## Example 4: Copy-Trade Wallet Evaluation

**Objective**: Evaluate a wallet for copy-trading suitability.

**Prompt**:
```
Use available skills. Evaluate this wallet [ADDRESS] as a copy-trade candidate:

1. Get full transaction history (last 30 days)
2. Profile: how many trades, win rate, average PnL, largest win/loss
3. What tokens does this wallet trade? (graduated only or also PumpFun?)
4. Average hold time, typical position size in SOL
5. Does this wallet use stop losses? (evidence of consistent exit patterns)
6. How fast after buying does price typically move? (edge timing)
7. Give me a copy-trade suitability score (1-10) with reasoning
```

**Skills Used**: helius-api, solana-onchain, token-holder-analysis, whale-tracking, portfolio-analytics, trading-visualization

---

## Example 5: Statistical Pairs Trading

**Objective**: Find and backtest a pairs trade in crypto.

**Prompt**:
```
Use available skills. Find cointegrated crypto pairs for pairs trading:

1. Get daily closes for the top 20 Solana tokens by market cap (6 months)
2. Run Engle-Granger cointegration tests for all pairs
3. For the top 3 most cointegrated pairs:
   - Plot spread with z-score bands
   - Estimate half-life of mean reversion
   - Compute Hurst exponent
   - Backtest: enter at z > 2, exit at z < 0.5, stop at z > 3
4. Report results with equity curves and key metrics
```

**Skills Used**: coingecko-api, ohlcv-processing, cointegration-analysis, mean-reversion, regime-detection, vectorbt, portfolio-analytics, trading-visualization

---

## Example 6: ML Signal Pipeline

**Objective**: Build an ML-based entry signal for a specific token.

**Prompt**:
```
Use available skills. Build an ML classifier for [TOKEN]:

1. Fetch 3 months of 1h OHLCV data
2. Engineer features:
   - Technical: RSI(14), MACD, BBand width, ATR(14), OBV momentum
   - Volume: relative volume (vol / 20-period avg), buy/sell ratio
   - On-chain: holder count change rate (if available)
3. Label: 1 if next-4h return > 2%, else 0
4. Train XGBoost with walk-forward validation (14d train, 7d test, rolling)
5. Show:
   - SHAP feature importance plot
   - Precision/recall curve
   - Backtest: trade when model predicts 1 with >0.6 probability
   - Compare against RSI-only baseline
```

**Skills Used**: birdeye-api, ohlcv-processing, pandas-ta, custom-indicators, feature-engineering, signal-classification, vectorbt, portfolio-analytics, trading-visualization

---

## Example 7: Portfolio Risk Report

**Objective**: Generate a comprehensive risk report for an active portfolio.

**Prompt**:
```
Use available skills. Generate a risk report for my portfolio:

Positions:
- 5 SOL in Token A [MINT]
- 3 SOL in Token B [MINT]
- 2 SOL in Token C [MINT]
- 10 SOL staked
- 5 SOL in Orca LP

1. Current valuation of each position
2. Correlation matrix between all tokens
3. Portfolio VaR (95% and 99%, 1-day)
4. Max drawdown scenario analysis
5. Concentration risk assessment
6. Suggestions for improving diversification
7. Overall risk score with breakdown
```

**Skills Used**: birdeye-api, correlation-analysis, portfolio-analytics, risk-management, impermanent-loss, trading-visualization

---

## Example 8: Tax-Aware Trading Workflow

**Objective**: Execute an accumulate/house-money strategy with full tax tracking.

**Prompt**:
```
Use available skills. I'm running an accumulate/house-money strategy on SOL memecoins.
Here's my trade history for TOKEN_A [MINT]:

- Buy 1000 tokens at 0.001 SOL each (1 SOL total) on Jan 15
- Buy 500 tokens at 0.002 SOL each (1 SOL total) on Feb 1
- Sell 300 tokens at 0.005 SOL each (1.5 SOL) on Feb 10 (house money recovery)
- Buy 200 tokens at 0.003 SOL each (0.6 SOL) on Feb 20

1. Calculate cost basis using proportional (average) method for the partial sell
2. Show the same trades under FIFO and HIFO for comparison
3. What's my realized gain/loss on the Feb 10 sell under each method?
4. Check if the Feb 20 buy triggers a wash sale (if the Feb 10 sell was a loss)
5. What's my unrealized position and average cost basis now?
6. Show me the Form 8949 entries for the realized trades
7. Export everything in Koinly format
```

**Skills Used**: cost-basis-engine, tax-liability-tracking, wash-sale-detection, regulatory-reporting, crypto-tax-export

**Expected Output**: Comparison table of cost basis methods, wash sale analysis, Form 8949 draft entries, and Koinly CSV export with disclaimer that this is not tax advice.

---

## Example 9: Sybil & Wash Trading Detection

**Objective**: Identify artificial activity on a newly graduated token.

**Prompt**:
```
Use available skills. Investigate [TOKEN_MINT] for suspicious activity:

1. Get the first 100 buyers after graduation
2. Cluster wallets by funding source — which wallets were funded by the same parent?
3. Check for co-trading patterns — wallets that consistently buy/sell the same tokens together
4. Identify any bundled transactions (multiple buys in the same block from related wallets)
5. What percentage of volume is likely wash trading?
6. Flag the top 5 most suspicious wallet clusters with evidence
7. Recalculate holder concentration excluding sybil clusters
```

**Skills Used**: helius-api, sybil-detection, token-holder-analysis, wallet-profiling, trading-visualization

---

## Tips for Effective Prompts

1. **Always start with**: "Use available skills when possible"
2. **Be specific**: Include mint addresses, timeframes, and parameter values
3. **Request structure**: Ask for tables, charts, and organized output
4. **Combine skills**: The best analysis chains multiple skills together
5. **Include risk context**: Mention your portfolio size and risk tolerance
6. **Request disclaimers**: Remind that output is analysis, not financial advice
