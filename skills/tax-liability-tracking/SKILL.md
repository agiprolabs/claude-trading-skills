---
name: tax-liability-tracking
description: Real-time tax liability analysis for active crypto traders with proportional cost basis, gain classification, and tax-aware trading signals
license: MIT
metadata:
  author: agipro
  version: "0.1.0"
  category: trading
---

# Tax Liability Tracking

Real-time tax liability analysis purpose-built for active Solana traders. Track proportional cost basis across partial sells, classify realized vs unrealized gains, project quarterly tax obligations, and surface tax-aware signals that feed back into trading decisions.

## Why This Matters

Active crypto traders generate hundreds of taxable events per year. Without real-time tracking:

- You do not know your actual after-tax P&L until year-end
- Partial sells (the "house money" play) create cost basis confusion
- Short-term vs long-term classification shifts your effective tax rate by 15-20%
- Tax-loss harvesting windows close without you noticing
- Quarterly estimated payments become guesswork

This skill keeps a running tax ledger alongside your trading activity so every decision incorporates its tax consequence.

## Core Concepts

### Proportional Cost Basis for Partial Sells

This is the most critical concept. When you sell a portion of a position, the cost basis splits proportionally — it does not shift to zero for the remaining tokens.

**Example — The Accumulate / House-Money Play:**

1. **Buy**: 1,000 tokens at $1.00 each. Total cost basis = $1,000.
2. **Partial sell**: Sell 800 tokens at $1.25 each. Proceeds = $1,000.
3. **What happened**:
   - The 800 sold tokens had proportional cost basis = 800 x $1.00 = $800
   - Realized gain on the sale = $1,000 - $800 = **$200**
   - The remaining 200 tokens retain cost basis = 200 x $1.00 = **$200**
   - The remaining tokens are NOT "free" — they carry their original per-unit cost

**Common mistake**: Recording the partial sell as "capital recovered, remaining basis = $0." This understates the realized gain on the partial sell and overstates the gain when the remaining tokens are eventually sold. The total tax owed is the same either way, but the timing and classification (short-term vs long-term) can differ significantly.

### Gain Classification

| Classification | Holding Period | US Federal Rate (2024) |
|---|---|---|
| Short-term capital gain | < 1 year | Ordinary income rate (10-37%) |
| Long-term capital gain | >= 1 year | 0%, 15%, or 20% |

Each tax lot tracks its own acquisition date. Partial sells consume lots in the order specified by your accounting method (FIFO, LIFO, or specific identification).

### SOL-Denominated Trading with USD Reporting

Solana traders typically think in SOL but US tax obligations are denominated in USD. Every taxable event requires:

1. **SOL price at acquisition** — establishes USD cost basis
2. **SOL price at disposition** — establishes USD proceeds
3. **Token price in SOL at both events** — converted to USD via SOL/USD rate

The skill tracks SOL/USD rates at each event timestamp to compute USD-denominated gains.

### Realized vs Unrealized Gains

- **Realized**: Position closed (fully or partially). Taxable event occurred.
- **Unrealized**: Position still open. No tax event yet, but contributes to estimated liability if you plan to close before year-end.

The after-tax P&L view shows both, with unrealized gains marked at current estimated tax rates.

## Capabilities

### Tax Lot Tracking
- Record buys, sells, and token-to-token swaps as taxable events
- Maintain per-lot cost basis with acquisition date
- Support FIFO, LIFO, and specific identification accounting methods
- Handle partial sells with proportional cost basis allocation

### Gain Classification Engine
- Classify each realized gain as short-term or long-term
- Track days remaining until long-term threshold for each open lot
- Flag positions approaching the 1-year boundary

### Quarterly Tax Projection
- Estimate federal tax liability using progressive bracket rates
- Include state tax estimate (configurable rate)
- Project Q1-Q4 estimated payment amounts
- Track cumulative realized gains by quarter

### Tax-Aware Trading Signals
- **Long-term threshold alert**: "Position crosses long-term threshold in N days"
- **Profit-taking cost**: "Taking profit here triggers $X short-term liability"
- **Loss harvesting**: "You have $X in unrealized losses available to harvest"
- **Timing value**: "Selling now vs waiting 30 days saves $X in taxes"
- **Wash sale warning**: "Repurchasing within 30 days may trigger wash sale rules"

### After-Tax P&L View
- Standard trading P&L alongside estimated after-tax P&L
- Per-position breakdown of pre-tax and after-tax returns
- Running year-to-date tax liability total

## Prerequisites

- Python 3.10+
- No external dependencies for core tracking (stdlib only)
- Historical SOL/USD prices for accurate USD conversion
- Trade history in structured format (timestamp, side, token, amount, price)

## Quick Start

```python
from tax_tracker import TaxTracker, Trade

tracker = TaxTracker(
    accounting_method="fifo",
    federal_bracket=0.32,   # Your marginal federal rate
    state_rate=0.05,        # Your state income tax rate
    long_term_rate=0.15,    # Your long-term capital gains rate
)

# Record the accumulate/house-money play
tracker.add_trade(Trade(
    timestamp="2025-06-15T10:00:00Z",
    side="buy",
    token="BONK",
    amount=1_000_000,
    price_usd=0.00002,      # Per-token price in USD
    total_usd=20.00,
))

tracker.add_trade(Trade(
    timestamp="2025-07-20T14:30:00Z",
    side="sell",
    token="BONK",
    amount=800_000,          # Sell 80% to recover capital
    price_usd=0.000025,
    total_usd=20.00,
))

# Check what happened
summary = tracker.position_summary("BONK")
print(f"Realized gain: ${summary.realized_gain:.2f}")
# Realized gain: $4.00  (sold 800k at $0.000025 = $20, basis = $16, gain = $4)

print(f"Remaining basis: ${summary.remaining_cost_basis:.2f}")
# Remaining basis: $4.00  (200k tokens x $0.00002 = $4)

print(f"Classification: {summary.gain_type}")
# Classification: short-term  (held ~35 days)

# Tax-aware signals
signals = tracker.get_signals("BONK", current_price_usd=0.00003)
for signal in signals:
    print(f"  [{signal.type}] {signal.message}")
# [long_term_countdown] Position crosses long-term threshold in 330 days
# [profit_taking_cost] Taking full profit triggers $2.80 short-term liability
```

## Use Cases

### 1. Day Trader Tax Tracking
Track hundreds of daily trades, all short-term. Focus on quarterly estimated payment accuracy and cumulative liability.

### 2. Swing Trader with House-Money Plays
Partial sell to recover capital, let remaining position ride. Proportional cost basis ensures both legs are tracked correctly.

### 3. Long-Term Holder Monitoring
Track positions approaching the 1-year long-term threshold. Signals alert when selling now vs waiting N days changes the tax classification.

### 4. Tax-Loss Harvesting
Identify positions with unrealized losses. Harvest losses to offset gains while being mindful of wash sale rules.

### 5. Year-End Tax Planning
Project remaining quarterly liability, identify optimization opportunities before Dec 31.

### 6. Multi-Token Portfolio
Track cost basis and gains across dozens of tokens simultaneously, with per-token and aggregate views.

## Accounting Methods

### FIFO (First In, First Out)
Sells consume the oldest lots first. Default for most traders. Generally results in more long-term gains if you have been accumulating over time.

### LIFO (Last In, First Out)
Sells consume the newest lots first. Can minimize short-term gains if recent purchases were at higher prices.

### Specific Identification
Choose which lots to sell. Maximum flexibility for tax optimization, but requires careful record-keeping. Must be elected before the trade, not after.

## Integration with Trading Workflow

```
Trade Signal → Tax-Aware Filter → Execute/Defer Decision
                    │
                    ├─ "Short-term gain: $X liability"
                    ├─ "Long-term in N days — consider waiting"
                    ├─ "Loss harvest opportunity: $X offset"
                    └─ "Net after-tax profit: $Y"
```

The tax-aware filter does not block trades — it provides information so the trader can make informed decisions about timing.

## Files

### References
- `references/planned_features.md` — Detailed feature list, proportional cost basis math with worked examples, gain classification rules, quarterly estimation methodology

### Scripts
- `scripts/tax_tracker.py` — Demo implementation with proportional cost basis, gain classification, tax-aware signals, and quarterly projection. Run with `--demo` for an example accumulate/house-money scenario.

## Limitations

- US federal and state tax rules only (no international tax support yet)
- Does not handle staking rewards, airdrops, or DeFi yield as income events (planned)
- Wash sale rules are flagged but not automatically enforced
- Token-to-token swaps treated as sell + buy (two taxable events) per IRS guidance
- Does not generate official tax forms (use for tracking and planning only)

## Disclaimer

Tax calculations produced by this skill are for **informational tracking purposes only**. Cryptocurrency tax law is complex and evolving. All tax figures should be verified by a qualified tax professional before filing. This skill does not constitute tax advice. Consult a CPA or tax attorney for guidance specific to your situation.
