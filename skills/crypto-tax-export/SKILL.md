---
name: crypto-tax-export
description: Export trade history and tax calculations in formats compatible with Koinly, CoinTracker, CoinLedger, TokenTax, and IRS Form 8949
license: MIT
metadata:
  author: agipro
  version: "0.1.0"
  category: trading
---

# Crypto Tax Export

Export trade history and tax calculations for tax software and IRS filing. Handles Solana-specific transaction types (Jupiter swaps, LP operations, staking rewards, airdrops) and generates CSVs compatible with Koinly, CoinTracker, CoinLedger, TokenTax, TurboTax/TaxAct, and IRS Form 8949.

> **Disclaimer:** This skill provides data formatting and calculation tools only. It does not constitute tax advice. Consult a qualified tax professional for guidance on reporting cryptocurrency transactions. Tax laws vary by jurisdiction and change frequently.

## Prerequisites

- Python 3.10+
- Trade history data (from internal trade journal, on-chain history, or exchange exports)
- For on-chain reconciliation: Solana RPC or Helius API access (see `helius-api` skill)
- For cost basis: historical price data (see `birdeye-api` or `coingecko-api` skills)

## Capabilities

| Capability | Description |
|---|---|
| Multi-format CSV export | Koinly, CoinTracker, CoinLedger, TokenTax, TurboTax, TaxAct |
| IRS Form 8949 generation | Part I (short-term) and Part II (long-term), columns a through h |
| Solana tx classification | Jupiter swaps, multi-hop routes, LP deposits/withdrawals, staking, airdrops |
| Cost basis methods | FIFO, LIFO, HIFO, Specific Identification |
| Reconciliation | Match on-chain history against internal trade journal |
| Failed tx handling | Identify and exclude failed transactions (no taxable event) |

## Supported Export Formats

### Koinly CSV

Koinly expects a universal import format with these columns:

```
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash
```

Labels: `swap`, `staking`, `airdrop`, `liquidity_in`, `liquidity_out`, `cost`, `gift`, `lost`.

### CoinTracker CSV

```
Date,Received Quantity,Received Currency,Sent Quantity,Sent Currency,Fee Amount,Fee Currency,Tag
```

Tags: `trade`, `staking_reward`, `airdrop`, `lp_deposit`, `lp_withdrawal`.

### CoinLedger CSV

```
Date (UTC),Type,Received Currency,Received Amount,Sent Currency,Sent Amount,Fee Currency,Fee Amount,Exchange/Wallet
```

Types: `Trade`, `Income`, `Gift Received`, `Mining`, `Staking Reward`, `Airdrop`.

### TokenTax CSV

```
Type,BuyAmount,BuyCurrency,SellAmount,SellCurrency,FeeAmount,FeeCurrency,Exchange,Group,Comment,Date
```

Types: `Trade`, `Income`, `Staking`, `Airdrop`, `Spending`.

### TurboTax / TaxAct CSV

Both accept a simplified Form 8949 format:

```
Description of Property,Date Acquired,Date Sold,Proceeds,Cost Basis,Gain or Loss
```

### IRS Form 8949

Part I — Short-term (held one year or less). Part II — Long-term (held more than one year).

Columns:
- **(a)** Description of property (e.g., "2.5 SOL")
- **(b)** Date acquired (MM/DD/YYYY)
- **(c)** Date sold or disposed of (MM/DD/YYYY)
- **(d)** Proceeds (sale price in USD)
- **(e)** Cost or other basis (purchase price in USD + fees)
- **(f)** Code, if any (per IRS instructions)
- **(g)** Adjustment amount
- **(h)** Gain or loss (d minus e, adjusted by g)

Check box: **(A)** if basis reported to IRS, **(B)** if not, **(C)** if Form 1099-B not received.

## Solana Transaction Classification

### Jupiter Swaps (Single-Hop)

A direct token-to-token swap. Classified as a **disposal** of the sent token and **acquisition** of the received token. Each side is a taxable event.

```python
tx = {
    "type": "swap",
    "sent": {"amount": 1.5, "currency": "SOL", "usd_value": 225.00},
    "received": {"amount": 50000, "currency": "BONK", "usd_value": 224.50},
    "fee": {"amount": 0.000005, "currency": "SOL", "usd_value": 0.00075},
    "timestamp": "2025-03-15T14:30:00Z",
    "tx_hash": "5abc...def",
}
```

### Jupiter Swaps (Multi-Hop)

A routed swap through intermediate tokens (e.g., SOL -> USDC -> BONK). Only the **initial send** and **final receive** matter for tax purposes. Intermediate hops are not separate taxable events.

### LP Deposits / Withdrawals

- **Deposit**: Sending tokens to an LP is generally treated as a disposal at fair market value.
- **Withdrawal**: Receiving tokens from an LP is an acquisition at fair market value.
- LP tokens received/burned may be tracked for cost basis continuity.

### Staking Rewards

Staking rewards (SOL validator rewards, liquid staking yield) are **income** at fair market value when received. Cost basis equals the FMV at receipt.

### Airdrops

Airdrops are **income** at fair market value when the recipient gains dominion and control. Some jurisdictions differ on when dominion is established.

### Token Migrations

A 1:1 token migration (e.g., protocol upgrade) is generally **not** a taxable event. The new token inherits the cost basis and holding period of the old token.

### Failed Transactions

Failed Solana transactions (status: failed, or inner instruction errors) are **not** taxable events. The transaction fee (SOL) may still be deductible as a cost of doing business in some jurisdictions. Always exclude failed txs from trade export.

## Cost Basis Methods

```python
from enum import Enum

class CostBasisMethod(Enum):
    FIFO = "fifo"      # First In, First Out (IRS default)
    LIFO = "lifo"      # Last In, First Out
    HIFO = "hifo"      # Highest In, First Out (minimizes gains)
    SPEC_ID = "spec_id" # Specific Identification (requires lot tracking)

def compute_gain(
    proceeds: float,
    cost_basis: float,
    adjustments: float = 0.0,
) -> float:
    """Compute gain or loss for Form 8949 column (h)."""
    return proceeds - cost_basis + adjustments
```

## Reconciliation

Reconciling on-chain history with an internal trade journal catches:

1. **Missing trades** — on-chain tx not in journal (manual entry missed)
2. **Phantom trades** — journal entry with no matching on-chain tx
3. **Amount mismatches** — journal amount differs from on-chain amount
4. **Duplicate entries** — same tx recorded twice

Reconciliation workflow:

```python
def reconcile(
    journal_trades: list[dict],
    onchain_txs: list[dict],
    tolerance: float = 0.001,
) -> dict:
    """Match journal entries to on-chain transactions.

    Args:
        journal_trades: Internal trade records with tx_hash field.
        onchain_txs: Parsed on-chain transactions.
        tolerance: Relative tolerance for amount matching.

    Returns:
        Dict with matched, missing_onchain, missing_journal,
        mismatched lists.
    """
    onchain_by_hash = {tx["tx_hash"]: tx for tx in onchain_txs}
    matched, missing_onchain, missing_journal, mismatched = [], [], [], []

    for trade in journal_trades:
        tx = onchain_by_hash.pop(trade.get("tx_hash", ""), None)
        if tx is None:
            missing_onchain.append(trade)
        elif abs(trade["amount"] - tx["amount"]) / max(tx["amount"], 1e-9) > tolerance:
            mismatched.append({"journal": trade, "onchain": tx})
        else:
            matched.append({"journal": trade, "onchain": tx})

    missing_journal = list(onchain_by_hash.values())

    return {
        "matched": matched,
        "missing_onchain": missing_onchain,
        "missing_journal": missing_journal,
        "mismatched": mismatched,
        "summary": {
            "total_journal": len(journal_trades),
            "total_onchain": len(onchain_txs),
            "matched": len(matched),
            "missing_onchain": len(missing_onchain),
            "missing_journal": len(missing_journal),
            "mismatched": len(mismatched),
        },
    }
```

## Quick Start

```python
from scripts.tax_exporter import (
    generate_demo_trades,
    export_koinly_csv,
    export_form_8949_csv,
)

# Generate sample trades
trades = generate_demo_trades()

# Export to Koinly format
export_koinly_csv(trades, "koinly_import.csv")

# Export to Form 8949 format
export_form_8949_csv(trades, "form_8949.csv")
```

Run the demo directly:

```bash
python scripts/tax_exporter.py --demo
```

## Use Cases

### End-of-Year Tax Filing
Export all trades from your journal, reconcile with on-chain history, generate Form 8949 line items, and import into TurboTax or hand to your CPA.

### Tax-Loss Harvesting Review
Export with HIFO cost basis method to identify positions with unrealized losses that could offset gains before year-end.

### Multi-Platform Consolidation
Combine trades from multiple wallets and DEXs into a single Koinly or CoinTracker import file for unified portfolio tax reporting.

### Audit Preparation
Use reconciliation to verify completeness of your trade records against on-chain history. Produce a clean Form 8949 with supporting transaction hashes.

## Files

| File | Description |
|---|---|
| `references/planned_features.md` | Export format specs, Form 8949 mapping, Solana tx classification, reconciliation methodology |
| `scripts/tax_exporter.py` | Demo script: generate trades, export to Koinly CSV and Form 8949 CSV, show format differences |

## Related Skills

- `helius-api` — Fetch and parse Solana transaction history for reconciliation
- `birdeye-api` / `coingecko-api` — Historical price data for cost basis lookups
- `solana-onchain` — Wallet transaction analysis and classification
- `trade-journal` — Internal trade record keeping
