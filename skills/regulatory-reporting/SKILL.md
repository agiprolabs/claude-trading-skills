---
name: regulatory-reporting
description: "[STUB] Regulatory report generation including IRS Form 8949, Schedule D, FinCEN FBAR, and state-specific crypto reporting requirements"
license: MIT
metadata:
  author: agipro
  version: "0.1.0"
  category: trading
---

# Regulatory Reporting

> **STATUS: STUB** — This skill outlines planned capabilities for crypto tax and regulatory reporting. All generated output must be reviewed by a qualified tax professional before filing. Nothing in this skill constitutes tax or legal advice.

## Overview

Track and generate required regulatory reports for cryptocurrency trading activity. Covers U.S. federal forms (IRS Form 8949, Schedule D), FinCEN foreign account reporting (FBAR), state-specific crypto obligations, large-transaction flagging, and deadline tracking.

Crypto tax reporting is complex and evolving. Rules change frequently, cost-basis methods vary by jurisdiction, and DeFi activities (swaps, LP positions, airdrops, staking rewards) have ambiguous treatment under current guidance. This skill provides a structured framework for organizing trade data into the formats regulators expect — but a tax professional must validate every filing.

## Disclaimer

> **WARNING**: This skill is for informational and educational purposes only. It does NOT constitute tax, legal, or financial advice. Cryptocurrency tax law is complex, jurisdiction-specific, and rapidly evolving. You MUST consult a qualified tax professional (CPA, EA, or tax attorney with crypto expertise) before relying on any output from this skill for actual tax filings. Errors in tax reporting can result in penalties, interest, and legal consequences. The authors accept no liability for any use of this material.

## Current Status

This is a **STUB** skill. The code and references provided are starting points that demonstrate data structures and basic calculations. They have NOT been validated against current IRS guidance or any state tax authority requirements.

### What Exists Now

- Basic Form 8949 line-item generation from trade data (see `scripts/form_8949_generator.py`)
- Regulatory requirements overview (see `references/planned_features.md`)
- Demo mode with sample trade data

### What Is Planned

- Complete IRS Form 8949 and Schedule D PDF generation
- FinCEN FBAR generation when foreign exchange accounts exceed $10,000
- State-specific reporting requirement detection and templates
- Reporting threshold tracking and deadline calendar
- Large transaction flagging ($10,000+ cash-equivalent transactions)
- Foreign account reporting requirements (FATCA Form 8938)
- Wash sale detection and adjustment (where applicable)
- Cost-basis method selection (FIFO, LIFO, Specific ID, HIFO)
- DeFi-specific event classification (swaps, LP entry/exit, staking, airdrops)
- Actual IRS-compatible CSV/PDF form data output

## Prerequisites

```bash
# No external dependencies for the demo script
python scripts/form_8949_generator.py --demo
```

For a production implementation, the following would be needed:

```bash
uv pip install pandas reportlab  # PDF generation
```

## Key Concepts

### IRS Form 8949 — Sales and Dispositions of Capital Assets

Form 8949 reports each individual sale or disposition of a capital asset. For crypto, every trade, swap, or spending event is a taxable disposition. Key fields:

| Column | Description |
|--------|-------------|
| (a) | Description of property (e.g., "2.5 BTC") |
| (b) | Date acquired |
| (c) | Date sold or disposed of |
| (d) | Proceeds (sale price in USD) |
| (e) | Cost or other basis |
| (f) | Adjustment code (e.g., W for wash sale) |
| (g) | Adjustment amount |
| (h) | Gain or loss (d minus e, adjusted by g) |

Transactions are split into **Part I** (short-term, held one year or less) and **Part II** (long-term, held more than one year).

### Schedule D — Capital Gains and Losses

Schedule D aggregates the totals from Form 8949:
- Line 1b/8b: Totals from Form 8949 Part I / Part II (basis reported to IRS)
- Line 1c/8c: Totals where basis was NOT reported to IRS
- Line 7/15: Net short-term / long-term capital gain or loss
- Line 16: Combined net gain or loss

### FinCEN FBAR (FinCEN Form 114)

Required when the aggregate value of foreign financial accounts exceeds $10,000 at any point during the calendar year. Crypto held on foreign exchanges (e.g., Binance for non-U.S. entities) may trigger this requirement — though IRS guidance on whether crypto accounts are "foreign financial accounts" remains evolving.

- **Filing deadline**: April 15 (automatic extension to October 15)
- **Penalty for non-filing**: Up to $12,500 per non-willful violation; up to $100,000 or 50% of account balance for willful violations

### Large Transaction Reporting

Businesses receiving $10,000+ in cash (which may include crypto under recent guidance) must file IRS Form 8300 within 15 days. Individual traders generally do not file Form 8300, but exchanges may report large transactions.

## Quick Start

```python
"""Generate Form 8949 line items from trade history."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

@dataclass
class Trade:
    asset: str
    quantity: Decimal
    date_acquired: date
    date_sold: date
    proceeds_usd: Decimal
    cost_basis_usd: Decimal

def classify_holding_period(trade: Trade) -> str:
    """Return 'short-term' or 'long-term' based on holding period."""
    holding_days = (trade.date_sold - trade.date_acquired).days
    return "short-term" if holding_days <= 365 else "long-term"

def compute_gain_loss(trade: Trade) -> Decimal:
    """Compute capital gain or loss for a single trade."""
    return trade.proceeds_usd - trade.cost_basis_usd

# Example
trade = Trade(
    asset="SOL",
    quantity=Decimal("10"),
    date_acquired=date(2025, 1, 15),
    date_sold=date(2025, 8, 20),
    proceeds_usd=Decimal("2500.00"),
    cost_basis_usd=Decimal("1800.00"),
)
gain = compute_gain_loss(trade)
period = classify_holding_period(trade)
print(f"{trade.asset}: {period} gain of ${gain}")
# SOL: short-term gain of $700.00
```

## Use Cases

1. **End-of-year tax preparation** — Export trade history from exchanges, generate Form 8949 line items, calculate Schedule D totals, and hand the organized data to your tax professional.

2. **Quarterly estimated tax tracking** — Monitor cumulative realized gains throughout the year to estimate quarterly tax payments (IRS Form 1040-ES).

3. **FBAR threshold monitoring** — Track aggregate balances across foreign exchange accounts to determine whether FBAR filing is required.

4. **Audit preparation** — Maintain organized records of all dispositions with cost-basis documentation in case of an IRS inquiry.

5. **Multi-state filing** — Identify state-specific crypto reporting obligations when trading from states with additional requirements.

## Files

### References
- `references/planned_features.md` — Regulatory requirements overview, Form 8949/Schedule D field descriptions, FBAR thresholds, state requirements summary, and reporting deadlines

### Scripts
- `scripts/form_8949_generator.py` — Basic Form 8949 line-item generator from trade data with `--demo` mode; no external dependencies

## Limitations

- **Not legal or tax advice.** This is a software tool, not a tax professional.
- **U.S.-focused.** International tax obligations are not covered.
- **Evolving rules.** Crypto tax guidance changes frequently; this skill may not reflect the latest IRS notices or rulings.
- **No DeFi classification yet.** Complex DeFi events (LP positions, yield farming, rebasing tokens) are not yet handled.
- **No wash sale certainty.** Whether wash sale rules apply to crypto is unsettled; the skill flags potential wash sales but cannot make definitive determinations.
- **Cost-basis methods limited.** Only FIFO is implemented in the demo; LIFO, HIFO, and Specific ID are planned.

## Reporting Deadlines (U.S. Federal)

| Form | Deadline | Extension |
|------|----------|-----------|
| Form 8949 / Schedule D | April 15 | October 15 (with Form 4868) |
| FinCEN FBAR (Form 114) | April 15 | October 15 (automatic) |
| Form 8300 | 15 days after transaction | None |
| FATCA Form 8938 | With tax return | With tax return extension |
| 1040-ES (quarterly) | Apr 15, Jun 15, Sep 15, Jan 15 | None |

## Contributing

This is a stub skill with significant room for expansion. Contributions welcome in these areas:

- Additional cost-basis methods (LIFO, HIFO, Specific ID)
- DeFi event classification (LP entry/exit, staking, airdrops, bridging)
- State-specific requirement databases
- Wash sale detection algorithms
- PDF form generation (IRS-compatible output)
- International tax jurisdiction support
- Integration with exchange API export formats

All contributions must include appropriate disclaimers and must not provide specific tax advice. See the project CLAUDE.md for contribution guidelines.

## Related Skills

- `portfolio-analytics` — Portfolio performance tracking that feeds into tax reporting
- `trade-journal` — Trade logging that can serve as source data for Form 8949
