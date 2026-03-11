# Claude Trading Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)
[![Skills](https://img.shields.io/badge/Skills-62-brightgreen.svg)](#whats-included)
[![Agent Skills](https://img.shields.io/badge/Standard-Agent_Skills-blueviolet.svg)](https://agentskills.io)
[![Works with](https://img.shields.io/badge/Works_with-Claude_Code_|_Cursor_|_Codex_|_Gemini_CLI-blue.svg)](#getting-started)

A comprehensive collection of **62 ready-to-use trading, DeFi, and quantitative finance [Agent Skills](https://agentskills.io)**. Works with Claude Code, Cursor, Codex, Gemini CLI, and [30+ other tools](https://agentskills.io). Transform your AI agent into a trading analyst capable of executing complex multi-step workflows across market data analysis, on-chain research, backtesting, risk management, tax compliance, and more.

**Crypto/DeFi-first. Extensible to all of quant finance.**

<p align="center">
  <img src="claude-trading-skills.gif" alt="Claude Trading Skills Demo" width="800"/>
</p>

> ⚠️ **Disclaimer**: This is an analysis and research toolkit. Nothing produced by these skills constitutes financial advice. Always do your own research.

> ⭐ **If you find this repository useful**, please consider giving it a star! It helps others discover these tools and encourages continued development.

---

## 📋 Table of Contents

- [Why Use This?](#-why-use-this)
- [What's Included](#-whats-included)
- [Getting Started](#-getting-started)
- [Quick Examples](#-quick-examples)
- [Prerequisites](#-prerequisites)
- [Available Skills](#-available-skills)
- [Contributing](#-contributing)
- [Troubleshooting](#-troubleshooting)
- [FAQ](#-faq)
- [Citation](#-citation)
- [License](#-license)

---

## 🚀 Why Use This?

### ⚡ Accelerate Your Research
- **Skip API boilerplate** — Skills handle Birdeye, DexScreener, Jupiter, Helius, CoinGecko, DeFiLlama integration
- **Production-ready code** — Tested patterns for backtesting, risk management, and portfolio analytics
- **Multi-step workflows** — Chain data retrieval → analysis → visualization in a single prompt

### 🎯 Comprehensive Coverage
- **62 Skills** across 16 categories covering the full trading workflow
- **7 Market Data APIs** — Solana-native and cross-chain data sources
- **6 Solana Infrastructure** tools for real-time streams, shreds, bundles, DEX aggregation, and transaction building
- **5 On-Chain Analysis** tools for wallet profiling, whale tracking, sybil detection, and liquidity analysis
- **Statistical + ML** methods purpose-built for trading
- **7 Tax & Compliance** tools for cost basis, wash sales, tax-loss harvesting, and reporting

### 🔧 Easy Integration
- **One-click setup** via Claude Code plugin or manual copy for any [Agent Skills](https://agentskills.io)-compatible tool
- **Automatic discovery** — Your agent finds and uses relevant skills based on your request
- **Extensible** — Add equities, options, futures skills following the same pattern

---

## 📦 What's Included

### Skill Categories

| Category | Skills | Description |
|----------|--------|-------------|
| 📊 **Market Data & APIs** | 7 | Birdeye, DexScreener, SolanaTracker, CoinGecko, Helius, Solana RPC, DeFiLlama |
| 🔌 **Solana Infrastructure** | 6 | PumpFun mechanics, transaction building, Yellowstone gRPC, ShredStream, Jito bundles, Raptor DEX aggregator |
| 🔗 **On-Chain Analysis** | 5 | Wallet profiling, holder analysis, whale tracking, liquidity, sybil detection |
| 📈 **Technical Analysis** | 3 | pandas-ta, TA-Lib, crypto-native custom indicators |
| 🔄 **Backtesting & Strategy** | 4 | vectorbt, Backtrader, strategy framework, walk-forward validation |
| ⚖️ **Portfolio & Risk** | 4 | Portfolio analytics, position sizing, risk management, Kelly criterion |
| 🏦 **DeFi Specific** | 6 | LP math, impermanent loss, yield analysis, MEV, tokenomics, DEX pool analysis |
| 📐 **Statistical Methods** | 5 | Regime detection, volatility modeling, cointegration, mean reversion, correlation |
| 🤖 **ML for Trading** | 4 | Signal classification, feature engineering, RL execution, sentiment |
| ⚡ **Execution & Trading** | 4 | DEX execution, slippage modeling, copy-trading, exit strategies |
| 📉 **Data & Visualization** | 3 | Trading charts, OHLCV processing, trade journaling |
| 🔬 **Market Microstructure** | 2 | DEX orderflow analysis, traditional LOB theory, market making |
| 🔮 **Quant Finance** | 2 | Options pricing, fixed income |
| 🧾 **Tax, Accounting & Compliance** | 7 | Cost basis, wash sales, tax-loss harvesting, exports, bookkeeping, reporting |

Each skill includes:
- ✅ Comprehensive documentation (`SKILL.md`)
- ✅ Code examples with working snippets
- ✅ Use cases and integration guidance
- ✅ Reference materials in `references/`

---

## 🎯 Getting Started

This repo follows the open [Agent Skills](https://agentskills.io) standard and works with any compatible agent.

### Option A: Claude Code Plugin (Recommended)

The fastest way to install. Requires Claude Code v1.0.33+.

**Step 1: Add the marketplace**

```
/plugin marketplace add agiprolabs/claude-trading-skills
```

**Step 2: Install the plugin**

```
/plugin install trading-skills@agiprolabs-claude-trading-skills
```

**That's it!** All 62 skills are now available. Claude will automatically discover and use them when relevant to your trading tasks. Skills are namespaced as `/trading-skills:skill-name`.

**Managing the plugin:**

```
/plugin                                                    # Browse installed plugins
/plugin disable trading-skills@agiprolabs-claude-trading-skills   # Disable
/plugin enable trading-skills@agiprolabs-claude-trading-skills    # Re-enable
/plugin uninstall trading-skills@agiprolabs-claude-trading-skills # Remove
/reload-plugins                                            # Apply changes without restart
```

### Option B: Manual Copy (Any Agent Skills-Compatible Tool)

Works with Claude Code, Cursor, Codex, Gemini CLI, and [30+ other tools](https://agentskills.io).

**Step 1: Clone the repository**

```bash
git clone https://github.com/agiprolabs/claude-trading-skills.git
```

**Step 2: Copy skills to your agent's skills directory**

| Scope | Claude Code | Cursor | Codex | Gemini CLI |
|-------|-------------|--------|-------|------------|
| Global (all projects) | `~/.claude/skills/` | `~/.cursor/skills/` | `~/.codex/skills/` | `~/.gemini/skills/` |
| Project (one project) | `.claude/skills/` | `.cursor/skills/` | `.codex/skills/` | `.gemini/skills/` |

```bash
# Global install — choose your tool:
cp -r claude-trading-skills/skills/* ~/.claude/skills/   # Claude Code
cp -r claude-trading-skills/skills/* ~/.cursor/skills/   # Cursor
cp -r claude-trading-skills/skills/* ~/.codex/skills/    # Codex
cp -r claude-trading-skills/skills/* ~/.gemini/skills/   # Gemini CLI

# Or project-level install (Claude Code example):
mkdir -p .claude/skills
cp -r /path/to/claude-trading-skills/skills/* .claude/skills/
```

Your agent will automatically discover the skills and use them when relevant to your trading tasks.

> **Note**: Agent Skills are supported by 30+ tools including Claude Code, Cursor, Codex, Gemini CLI, VS Code Copilot, Roo Code, Goose, OpenHands, and more. See [agentskills.io](https://agentskills.io) for the full list.

---

## 💡 Quick Examples

### 🔍 Token Deep Dive

```
Use available skills. Analyze this Solana token: [MINT_ADDRESS]. Get current price and volume 
from Birdeye, check holder distribution and top 10 concentration, analyze liquidity depth across 
DEX pools, compute RSI/MACD/BBands on 1h candles, estimate slippage for a 0.5 SOL entry, and 
give me a risk assessment with suggested position size assuming 2% portfolio risk.
```

**Skills Used**: birdeye-api, token-holder-analysis, liquidity-analysis, dex-pool-analysis, pandas-ta, slippage-modeling, risk-management, position-sizing

### 📊 Strategy Backtest

```
Use available skills. Backtest a simple RSI mean-reversion strategy on SOL/USDC 1h candles for 
the past 6 months. Entry when RSI(14) < 30, exit when RSI > 70. Use 1% risk per trade with 
ATR(14)*2 stop loss. Show me equity curve, drawdown chart, and key metrics (Sharpe, max DD, 
win rate, profit factor).
```

**Skills Used**: birdeye-api, ohlcv-processing, pandas-ta, vectorbt, portfolio-analytics, trading-visualization

### 🏦 DeFi Yield Comparison

```
Use available skills. Compare yield opportunities for SOL across Raydium, Orca, and Meteora 
LP pools. Calculate impermanent loss at ±25% and ±50% price moves. Show me net APY after IL 
for each pool, and rank them by risk-adjusted yield. Include MEV risk assessment.
```

**Skills Used**: defillama-api, dex-pool-analysis, lp-math, impermanent-loss, yield-analysis, mev-analysis, trading-visualization

### 🐋 Whale Monitoring

```
Use available skills. Analyze the top 20 holders of [TOKEN_MINT]. Identify which wallets have 
been accumulating in the past 7 days. Check if any are known profitable traders. Show me the 
holder distribution with a Gini coefficient and flag any concentration risks.
```

**Skills Used**: helius-api, token-holder-analysis, whale-tracking, solana-onchain, trading-visualization

### 🧾 Tax-Aware Position Management

```
Use available skills. I'm tracking cost basis for my SOL trades using proportional (average)
cost basis for my accumulate/house-money strategy. I bought 10 SOL at $150, then 5 SOL at $180.
Now I want to sell 3 SOL at $200. Calculate my cost basis, realized gain, and remaining position.
Then check if any of my recent sells trigger wash sale rules, and show me what my Form 8949
entries would look like. Export the results in Koinly-compatible format.
```

**Skills Used**: cost-basis-engine, tax-liability-tracking, wash-sale-detection, crypto-tax-export, regulatory-reporting

### 🤖 ML Signal Pipeline

```
Use available skills. Build a feature set for [TOKEN] using 1h OHLCV data: RSI, MACD, 
Bollinger Band width, volume ratio, and holder count momentum. Train an XGBoost classifier 
to predict >2% returns in the next 4 hours. Use walk-forward validation with 30-day train, 
7-day test windows. Show feature importance and classification metrics.
```

**Skills Used**: birdeye-api, ohlcv-processing, pandas-ta, custom-indicators, feature-engineering, signal-classification, trading-visualization

---

## ⚙️ Prerequisites

- **Python**: 3.9+ (3.12+ recommended)
- **uv**: Python package manager (required for installing skill dependencies)
- **Client**: Any agent that supports the [Agent Skills](https://agentskills.io) standard (Claude Code, Cursor, Codex, Gemini CLI, etc.)
- **System**: macOS, Linux, or Windows with WSL2
- **API Keys** (as needed):
  - Birdeye (free tier at birdeye.so)
  - Helius (free tier at helius.dev)
  - CoinGecko Pro (optional, free tier has rate limits)
- **Dependencies**: Automatically handled by individual skills (check `SKILL.md` files for specific requirements)

### Installing uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify
uv --version
```

---

## 📚 Available Skills

### 📊 Market Data & APIs (7 skills)
- **birdeye-api** — Solana token data: prices, OHLCV, volume, metadata, trader activity
- **dexscreener-api** — Multi-chain DEX pair data, no auth required
- **solanatracker-api** — Solana token data, graduating tokens, PumpFun integration
- **coingecko-api** — Broad crypto market data: 13,000+ tokens, global stats, historical data
- **helius-api** — Enhanced Solana RPC: parsed transactions, DAS, webhooks
- **solana-rpc** — Direct Solana blockchain interaction via JSON-RPC
- **defillama-api** — DeFi analytics: TVL, yields, volumes, fees, bridges

### 🔌 Solana Infrastructure (6 skills)
- **pumpfun-mechanics** — Bonding curve math, graduation, migration, event parsing
- **solana-tx-building** — Versioned transactions, priority fees, compute budget, ALTs
- **yellowstone-grpc** — Real-time Solana streams via Yellowstone gRPC (Geyser)
- **shredstream** — Jito ShredStream for pre-block shred access (~200-400ms edge)
- **jito-bundles** — Bundle submission for MEV protection, tip strategies, block engine API
- **raptor-dex** — Self-hosted DEX aggregator: 25+ DEXes, no rate limits, Yellowstone Jet TPU

### 🔗 On-Chain Analysis (5 skills)
- **token-holder-analysis** — Holder distribution, concentration metrics, insider detection
- **whale-tracking** — Large wallet monitoring, accumulation/distribution detection
- **liquidity-analysis** — Depth analysis, pool TVL, slippage estimation, LP composition
- **wallet-profiling** — Behavioral classification, win rate, PnL tracking, style detection
- **sybil-detection** — Co-trade clustering, wash trading detection, bundler analysis

### 📈 Technical Analysis (3 skills)
- **pandas-ta** — 130+ indicators: RSI, MACD, Bollinger Bands, SuperTrend, Ichimoku, etc.
- **ta-lib** — C-optimized indicators + 61 candlestick pattern recognition functions
- **custom-indicators** — Crypto-native: NVT, MVRV, exchange flow, funding rate signals

### 🔄 Backtesting & Strategy (4 skills)
- **vectorbt** — High-performance vectorized backtesting with parameter optimization
- **backtrader** — Event-driven backtesting with rich order types and analyzers
- **strategy-framework** — Standardized strategy definition and documentation template
- **walk-forward-validation** — Time-series-aware validation, overfit detection, CPCV

### ⚖️ Portfolio & Risk (4 skills)
- **portfolio-analytics** — Sharpe, Sortino, Calmar, max drawdown, quantstats reports
- **position-sizing** — Fixed fractional, volatility-adjusted, Kelly-based sizing
- **risk-management** — Portfolio-level controls: drawdown limits, correlation, circuit breakers
- **kelly-criterion** — Optimal sizing with fractional Kelly variants

### 🏦 DeFi Specific (6 skills)
- **lp-math** — AMM math: constant product, CLMM, price impact, LP shares
- **impermanent-loss** — IL calculation, IL vs. fees breakeven, CLMM IL amplification
- **yield-analysis** — Real vs. nominal yield, net APY, emission sustainability
- **mev-analysis** — Sandwich detection, front-running risk, Solana MEV mechanics
- **token-economics** — Supply modeling, vesting, inflation, valuation frameworks
- **dex-pool-analysis** — AMM pool mechanics, fee analysis, pool comparison across DEXes

### 📐 Statistical Methods (5 skills)
- **regime-detection** — HMM, change-point detection, volatility clustering
- **volatility-modeling** — GARCH, EWMA, realized volatility, volatility cones
- **cointegration-analysis** — Engle-Granger, Johansen, rolling cointegration
- **mean-reversion** — Hurst exponent, half-life, z-score signals, ADF testing
- **correlation-analysis** — Rolling correlation, hierarchical clustering, tail dependence

### 🤖 ML for Trading (4 skills)
- **signal-classification** — XGBoost/LightGBM classifiers with walk-forward validation
- **feature-engineering** — Feature computation from OHLCV, on-chain, and alternative data
- **rl-execution** — Reinforcement learning for execution optimization
- **sentiment-analysis** — Social/news sentiment extraction and signal generation

### ⚡ Execution & Trading (4 skills)
- **dex-execution** — DEX swap execution via Jupiter aggregator (⚠️ requires user confirmation)
- **slippage-modeling** — Execution cost estimation and optimal trade sizing
- **copy-trading** — Leader wallet discovery, follow sizing, exit mirroring
- **exit-strategies** — Tiered take-profit, trailing stops, time-based and signal-based exits

### 📉 Data & Visualization (3 skills)
- **trading-visualization** — Candlesticks, equity curves, drawdowns, heatmaps
- **ohlcv-processing** — Data cleaning, resampling, gap handling, normalization
- **trade-journal** — Structured trade logging and performance review

### 🔬 Market Microstructure (2 skills)
- **market-microstructure** — DEX orderflow analysis, trade classification, volume profiles, wash trading detection
- **market-microstructure-traditional** — LOB theory, spread decomposition, market making, CEX vs DEX comparison

### 🔮 Quantitative Finance (2 skills)
- **options-pricing** — Black-Scholes, Greeks, implied vol surfaces, crypto options
- **fixed-income** — Bond pricing, yield curves, DeFi lending rate analysis

### 🧾 Tax, Accounting & Compliance (7 skills)
- **tax-liability-tracking** — Real-time gain/loss tracking per trade and portfolio-wide
- **cost-basis-engine** — FIFO, LIFO, HIFO, specific ID, and average cost basis methods
- **wash-sale-detection** — 61-day window wash sale scanning under 2025 US crypto rules
- **tax-loss-harvesting** — Opportunity scoring, replacement asset suggestions, wash sale compliance
- **crypto-tax-export** — Export to Koinly, CoinTracker, TurboTax, and Form 8949 CSV formats
- **trade-accounting** — Double-entry bookkeeping for trading operations
- **regulatory-reporting** — Form 8949, Schedule D, FBAR generation and compliance checks

> 📖 For detailed documentation on all skills, see [trading-skills.md](trading-skills.md)

---

## 🤝 Contributing

We welcome contributions! There's room for dozens more skills covering additional chains, CEX integrations, and advanced strategies.

### How to Contribute

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-skill`)
3. **Follow** the existing directory structure and documentation patterns
4. **Ensure** all new skills include comprehensive `SKILL.md` files with valid frontmatter
5. **Test** your examples and scripts thoroughly (include `--demo` mode)
6. **Commit** your changes (`git commit -m 'Add amazing skill'`)
7. **Push** to your branch (`git push origin feature/amazing-skill`)
8. **Submit** a pull request with a clear description of your changes

### Contribution Guidelines

- ✅ **Adhere to the [Agent Skills specification](https://agentskills.io/specification)** — valid `SKILL.md` frontmatter, naming conventions, directory structure
- ✅ Keep `SKILL.md` under 500 lines — move detailed content to `references/`
- ✅ Include `--demo` mode in scripts so they work without API keys
- ✅ Use `uv pip install` for all dependency installation examples
- ✅ API keys from environment variables only — never hardcode
- ✅ No financial advice language — frame all outputs as "analysis" or "information"

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guidelines.

### Ideas for New Skills
- CEX API integrations (Binance, Bybit, Coinbase)
- Other chain analysis (Ethereum, Base, Arbitrum)
- Options strategies and Greeks visualization
- Funding rate arbitrage
- Cross-exchange arbitrage detection
- Social graph analysis (who follows who on-chain)
- Gas/priority fee optimization
- Portfolio rebalancing automation

---

## 🔧 Troubleshooting

**Problem: Skills not loading**
- Verify skill folders are in the correct directory (see [Getting Started](#-getting-started))
- Each skill folder must contain a `SKILL.md` file
- Restart your agent/IDE after copying skills
- For plugin installs: run `/plugin` to check status, try `/reload-plugins`

**Problem: Missing Python dependencies**
- Check the specific `SKILL.md` file for required packages
- Install dependencies: `uv pip install package-name`

**Problem: API rate limits**
- Free tiers have rate limits — review the specific API documentation
- Consider implementing caching or batch requests
- Upgrade to pro tiers for heavy usage

**Problem: API key errors**
- Store keys in environment variables, not in code
- Check the skill's `SKILL.md` for authentication setup
- Verify your credentials and permissions

**Problem: Scripts failing**
- Most scripts support `--demo` mode for testing without API keys
- Check the script's docstring for required environment variables
- Ensure Python 3.9+ is installed

---

## ❓ FAQ

### General

**Q: Is this free to use?**
A: Yes, MIT licensed. Individual skills may reference tools with their own licensing.

**Q: Can I use this for live trading?**
A: The execution skills (dex-execution, raptor-dex) can interact with real markets, but they default to simulation/demo mode and require explicit confirmation. Use at your own risk.

**Q: Why crypto/DeFi first?**
A: The tooling gap is largest in crypto/DeFi. The extensible structure means contributors can add equities, options, and futures skills following the exact same pattern.

**Q: Does this work with tools other than Claude Code?**
A: Yes. Skills follow the open [Agent Skills](https://agentskills.io) standard and work with 30+ compatible tools including Claude Code, Cursor, Codex, Gemini CLI, VS Code Copilot, Roo Code, Goose, and more.

**Q: Why are all skills bundled together instead of separate packages?**
A: Trading is inherently cross-disciplinary. Bundling all skills together makes it easy to chain workflows — e.g., fetching data, computing indicators, backtesting, sizing positions, and exporting tax reports — without worrying about which individual skills to install.

### Installation & Setup

**Q: Do I need all API keys?**
A: No. Many skills (DexScreener, DeFiLlama, Jupiter quotes, CoinGecko free tier) need no authentication. Only install API keys for the services you use.

**Q: Do I need all Python packages installed?**
A: No. Only install the packages you need. Each skill specifies its requirements in its `SKILL.md` file.

**Q: What if a skill doesn't work?**
A: First check the [Troubleshooting](#-troubleshooting) section. If the issue persists, [open an issue](https://github.com/agiprolabs/claude-trading-skills/issues) with detailed reproduction steps.

### Contributing

**Q: Can I contribute my own skills?**
A: Absolutely! We welcome contributions. See [Contributing](#-contributing) for guidelines.

**Q: How do I report bugs or suggest features?**
A: [Open an issue](https://github.com/agiprolabs/claude-trading-skills/issues) with a clear description. For bugs, include reproduction steps and expected vs actual behavior.

---

## 💬 Support

- 📖 **Documentation**: Check the relevant `SKILL.md` and `references/` folders
- 🐛 **Bug Reports**: [Open an issue](https://github.com/agiprolabs/claude-trading-skills/issues)
- 💡 **Feature Requests**: [Submit a feature request](https://github.com/agiprolabs/claude-trading-skills/issues/new)

---

## 📖 Citation

### BibTeX
```bibtex
@software{claude_trading_skills_2026,
  author = {{AGIPro}},
  title = {Claude Trading Skills: Trading, DeFi, and Quantitative Finance Agent Skills},
  year = {2026},
  url = {https://github.com/agiprolabs/claude-trading-skills},
  note = {62 skills covering market data, on-chain analysis, backtesting, risk management, tax compliance, and more}
}
```

### APA
```
AGIPro. (2026). Claude Trading Skills: Trading, DeFi, and quantitative finance Agent Skills [Computer software]. https://github.com/agiprolabs/claude-trading-skills
```

### Plain Text
```
Claude Trading Skills by AGIPro (2026)
Available at: https://github.com/agiprolabs/claude-trading-skills
```

---

## 📄 License

MIT License. See [LICENSE.md](LICENSE.md) for full terms.

**Key Points:**
- ✅ Free for any use (commercial and noncommercial)
- ✅ Open source — modify, distribute, and use freely
- ⚠️ No warranty — provided "as is"
- ⚠️ Not financial advice — this is a research toolkit

---

*Built by traders, for traders. Star ⭐ if you find it useful!*
