# Trading Skills — Complete Catalog

This document provides detailed descriptions of all 62 trading skills organized by category.

---

## Market Data & APIs

### birdeye-api
Solana token market data aggregator. Provides prices, OHLCV, trading volume, token metadata, trader activity, and market overview across all Solana DEXes. Free tier: 100 req/min. Required for most Solana-specific workflows.

### dexscreener-api
Multi-chain DEX pair data. No authentication required. Covers 80+ chains with pair search, price data, liquidity, volume, and price changes. Best for quick lookups and cross-chain comparisons.

### solanatracker-api
Solana token data with PumpFun integration. Graduating token feeds, token profiles, wallet PnL, and top trader discovery. Complementary to Birdeye with unique graduating-token focus.

### helius-api
Enhanced Solana RPC with parsed transaction history, DAS API for token/NFT metadata, webhooks for real-time alerts, and priority fee estimates. Essential for wallet analysis and on-chain monitoring.

### solana-rpc
Direct Solana blockchain interaction via JSON-RPC. Account lookups, token accounts, transaction building, program account queries. Low-level foundation when higher-level APIs don't suffice.

### coingecko-api
Broad crypto market data covering 13,000+ tokens. Global market stats, historical data going back years, exchange volumes, trending tokens, category filters. Free tier: 30 calls/min. Best for macro analysis and long-term historical data.

### defillama-api
DeFi analytics across all chains. TVL, yields, DEX volumes, fees/revenue, stablecoin data, bridge flows. No auth required. Best for macro DeFi analysis and protocol comparison.

---

## Solana Infrastructure

### pumpfun-mechanics
PumpFun bonding curve mathematics, graduation mechanics, and migration to Raydium/PumpSwap. Virtual constant-product CPMM formulas, event parsing (CreateEvent, TradeEvent, CompleteEvent), and instruction decoding.

### solana-tx-building
Versioned transaction construction on Solana. Compute budget management, priority fee estimation, address lookup tables (ALTs), and multi-instruction composition. Foundation for all on-chain execution.

### yellowstone-grpc
Real-time Solana transaction streaming via Yellowstone gRPC (Geyser plugin). Subscription filters for accounts, transactions, slots, and blocks. Providers include Helius, Triton, and Shyft.

### shredstream
Jito ShredStream for pre-block shred access with ~200-400ms latency advantage. How to get access, connection setup, shred parsing, and use cases for latency-sensitive trading.

### jito-bundles
Jito bundle submission for MEV protection on Solana. Bundle building with up to 5 atomic transactions, tip strategies (static and dynamic), block engine endpoints (NY, Amsterdam, Frankfurt, Tokyo), and landing rate optimization. Essential for competitive transaction execution.

### raptor-dex
Self-hosted DEX aggregator by SolanaTracker. Supports 25+ Solana DEXes with no rate limits and no API key required. Yellowstone Jet TPU transaction submission, WebSocket streaming, configurable DEX filtering, and priority fee management. Requires a signature file from SolanaTracker for activation.

---

## On-Chain Analysis

### token-holder-analysis
Token holder distribution and concentration metrics. Top N holders, Gini coefficient, HHI, insider detection, supply analysis. Essential pre-trade safety check for new tokens.

### whale-tracking
Large wallet monitoring and accumulation/distribution detection. Wallet watchlists, activity alerts, cross-token analysis. Identifies early accumulation signals.

### liquidity-analysis
Liquidity depth assessment for DEX pairs. Bid/ask depth, pool TVL trends, CLMM concentration, slippage estimation, LP composition. Informs position sizing and execution strategy.

### wallet-profiling
Behavioral classification and performance analysis for Solana wallets. Win rate estimation, trading style detection (sniper, accumulator, flipper), PnL tracking, and copy-trade suitability scoring.

### sybil-detection
Sybil and wash trading detection on Solana. Co-trade clustering, funding source tracing, bundler identification, creator network analysis. Essential for identifying artificial activity.

---

## Technical Analysis

### pandas-ta
130+ technical indicators built on pandas. Trend (SMA, EMA, SuperTrend), momentum (RSI, MACD, Stochastic), volatility (BBands, ATR, Keltner), volume (OBV, VWAP, CMF). Preferred for Python workflows.

### ta-lib
C-optimized technical analysis with 61 candlestick pattern recognition functions. Best for performance-critical workloads and pattern detection. Requires system-level TA-Lib installation.

### custom-indicators
Crypto-native indicators: NVT ratio, MVRV, exchange flow, funding rate signals, open interest momentum, holder momentum, liquidity score, smart money flow. Beyond standard TA.

---

## Backtesting & Strategy

### vectorbt
Vectorized backtesting for high-performance strategy testing. Parameter optimization sweeps, portfolio simulation, rich metrics (Sharpe, Sortino, Calmar, etc.), built-in plotly visualization.

### backtrader
Event-driven backtesting with bar-by-bar execution. Complex order types (bracket, stop-limit), multiple analyzers, custom indicators, multi-data feeds. Best for strategies with complex order logic.

### strategy-framework
Standardized template for defining strategies: entry rules, exit rules, position sizing, risk parameters, performance criteria. Use before implementing in vectorbt/backtrader.

### walk-forward-validation
Walk-forward validation framework for trading strategies and ML models. Rolling and expanding window splits, purged cross-validation, embargo periods, combinatorial purged CV (CPCV), deflated Sharpe ratio, and probability of backtest overfitting. Essential for detecting overfit strategies.

---

## Portfolio & Risk

### portfolio-analytics
Portfolio-level performance measurement. Return metrics (CAGR, total), risk metrics (volatility, VaR, CVaR), risk-adjusted (Sharpe, Sortino, Calmar), rolling analysis, HTML reports via quantstats.

### position-sizing
Trade sizing methods: fixed fractional, volatility-adjusted (ATR), Kelly criterion, anti-martingale. Maximum position limits by account %, volume %, and pool liquidity.

### risk-management
Portfolio-level controls: max drawdown limits, correlation-adjusted exposure, daily/weekly loss limits, concentration limits, dynamic risk scaling, circuit breakers.

### kelly-criterion
Kelly criterion optimal sizing with fractional variants (0.25-0.5x recommended). Derivation, practical guidance, and integration with other sizing methods.

---

## DeFi Specific

### lp-math
AMM liquidity provision mathematics. Constant product (xy=k) and concentrated liquidity (CLMM) calculations, LP shares, fee accrual, price impact formulas.

### impermanent-loss
IL calculation and modeling across AMM types. IL vs. fees breakeven analysis, CLMM amplified IL, scenario modeling, visualization.

### yield-analysis
DeFi yield evaluation. Fee APR, real vs. nominal yield, net APY after IL and costs, yield comparison, emission sustainability analysis.

### mev-analysis
Solana MEV exposure assessment. Sandwich detection, front-running risk, MEV cost estimation, JIT liquidity patterns, protection strategies (Jito bundles).

### token-economics
Token supply dynamics and valuation. Supply modeling with vesting, inflation analysis, utility assessment, valuation frameworks (P/E, NVT, comparables).

### dex-pool-analysis
AMM pool mechanics comparison across Raydium, Orca, Meteora. Fee structures, pool types (constant product vs CLMM vs dynamic), creation patterns, volume efficiency.

---

## Statistical Methods

### regime-detection
Market regime identification. Hidden Markov Models, change-point detection (ruptures), volatility clustering, trend/range classification.

### volatility-modeling
Volatility estimation and forecasting. GARCH(1,1), EWMA, realized volatility (Parkinson, Garman-Klass), volatility cones.

### cointegration-analysis
Cointegration testing for pairs trading. Engle-Granger, Johansen, Phillips-Ouliaris tests. Rolling cointegration stability.

### mean-reversion
Mean-reversion strategy tools. Hurst exponent, half-life estimation, z-score signals, ADF stationarity testing, Ornstein-Uhlenbeck modeling.

### correlation-analysis
Cross-asset correlation analysis. Pearson/Spearman/Kendall matrices, rolling correlation, hierarchical clustering, tail dependence, regime shifts.

---

## ML for Trading

### signal-classification
ML trading signal classifiers. Binary and multi-class using XGBoost/LightGBM with walk-forward validation, SHAP feature importance, threshold optimization.

### feature-engineering
Feature construction from market data. Price/volume features, technical features, on-chain features, microstructure features. Stationarity, normalization, no-lookahead guarantees.

### rl-execution
Reinforcement learning for execution optimization. Order splitting, adaptive timing, impact minimization. Almgren-Chriss optimal execution framework.

### sentiment-analysis
Market sentiment extraction. Social media (Twitter/X, Reddit, Telegram), news sentiment, fear/greed indices, mention velocity, influencer tracking.

---

## Execution & Trading

### dex-execution
DEX swap execution via Jupiter aggregator on Solana. Quote retrieval, route optimization, transaction building, signing, and confirmation. ⚠️ Always requires explicit user confirmation.

### slippage-modeling
Execution cost estimation. Slippage curves vs. trade size, multi-pool routing, dynamic adjustment, total cost modeling including fees, slippage, and MEV risk.

### copy-trading
Leader wallet discovery and copy-trade execution. Follow sizing, correlation management, exit mirroring, and risk framework for portfolio-level copy exposure.

### exit-strategies
Systematic exit management. Tiered take-profit, trailing stops (ATR, percentage, chandelier), time-based exits, leader-sell exits, and partial position scaling.

---

## Data & Visualization

### trading-visualization
Professional trading charts. Candlesticks (mplfinance), equity curves, drawdowns, correlation heatmaps, return distributions, position timelines. Dark theme default.

### ohlcv-processing
Market data preparation. Resampling, gap handling, anomaly detection, normalization, multi-source merging, split adjustment.

### trade-journal
Trade logging and review. Structured records with strategy tags, rationale, PnL, and analytics for behavioral pattern detection.

---

## Market Microstructure

### market-microstructure
Order flow analysis and trade classification for DEX markets. Lee-Ready algorithm, bulk volume classification, buyer/seller concentration, momentum scoring, volume profiles, wash trading detection.

### market-microstructure-traditional
Traditional market microstructure concepts applied to crypto. Bid-ask spread decomposition (Glosten-Milgrom, Kyle), market maker P&L and inventory management, price impact models (Almgren-Chriss), order book imbalance, execution quality measurement (VWAP, implementation shortfall), and CEX vs DEX structural comparison.

---

## Quantitative Finance

### options-pricing
Black-Scholes pricing, binomial trees, Greeks computation, implied volatility surfaces. Applicable to crypto options (Deribit, Lyra) and traditional markets.

### fixed-income
Bond pricing, yield curves, duration/convexity. DeFi lending rate analysis (Aave, Compound, Solend, Marginfi).

---

## Tax, Accounting & Compliance

### tax-liability-tracking
Real-time gain/loss tracking per trade and portfolio-wide. Short-term vs. long-term classification, running tax liability estimates, and year-end summaries. Supports proportional cost basis for partial sells.

### cost-basis-engine
Five cost basis methods with comparison views: FIFO, LIFO, HIFO (highest-in first-out), specific identification, and average cost (proportional). Lot tracking across wallets, split/merge handling, and method comparison reports.

### wash-sale-detection
Wash sale scanning under 2025 US crypto rules. 61-day window (30 days before and after), substantially identical asset matching, basis adjustment calculations, and flagging for Form 8949 compliance.

### tax-loss-harvesting
Tax-loss harvesting opportunity identification and scoring. Unrealized loss scanning, replacement asset suggestions with wash sale compliance, harvest priority ranking by tax savings, and portfolio rebalancing integration.

### crypto-tax-export
Export trade history to tax software formats. Koinly universal format, CoinTracker CSV, TurboTax 8949, and raw Form 8949 CSV. Handles airdrops, staking rewards, LP entry/exit, and DeFi-specific transactions.

### trade-accounting
Double-entry bookkeeping for trading operations. Journal entries for buys, sells, fees, transfers, staking rewards, and LP positions. Trial balance, income statement, and balance sheet generation.

### regulatory-reporting
Form 8949, Schedule D, and FBAR generation for US crypto tax reporting. Aggregation rules, de minimis thresholds, and compliance checklists. ⚠️ Not tax advice — consult a qualified tax professional.
