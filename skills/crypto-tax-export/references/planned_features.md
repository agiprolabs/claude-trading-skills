# Crypto Tax Export — Planned Features Reference

## Export Format Specifications

### Koinly Universal CSV

Koinly accepts a universal CSV format for importing transactions from any source.

**Required columns:**
- `Date` — ISO 8601 or `YYYY-MM-DD HH:MM:SS UTC`
- `Sent Amount` — quantity sent (blank for income)
- `Sent Currency` — ticker symbol
- `Received Amount` — quantity received (blank for disposal-only)
- `Received Currency` — ticker symbol

**Optional columns:**
- `Fee Amount` / `Fee Currency` — transaction fee
- `Net Worth Amount` / `Net Worth Currency` — USD value at time of tx (helps Koinly price lookups)
- `Label` — transaction classification
- `Description` — free text note
- `TxHash` — on-chain transaction signature

**Koinly labels:** `swap`, `staking`, `airdrop`, `liquidity_in`, `liquidity_out`, `cost`, `gift`, `lost`, `fork`, `margin_fee`, `realized_gain`.

**Notes:**
- For swaps, populate both Sent and Received columns.
- For income (staking, airdrops), populate only Received columns.
- For expenses/losses, populate only Sent columns.
- Koinly auto-detects duplicates by TxHash.

### CoinTracker CSV

**Columns:** `Date`, `Received Quantity`, `Received Currency`, `Sent Quantity`, `Sent Currency`, `Fee Amount`, `Fee Currency`, `Tag`.

**Tags:** `trade`, `staking_reward`, `airdrop`, `lp_deposit`, `lp_withdrawal`, `payment`, `gift`.

**Date format:** `MM/DD/YYYY HH:MM:SS` (US format).

**Notes:**
- CoinTracker uses tags to classify income vs trades.
- Fees should be in the same currency as the sent side when possible.

### CoinLedger CSV

**Columns:** `Date (UTC)`, `Type`, `Received Currency`, `Received Amount`, `Sent Currency`, `Sent Amount`, `Fee Currency`, `Fee Amount`, `Exchange/Wallet`.

**Types:** `Trade`, `Income`, `Gift Received`, `Mining`, `Staking Reward`, `Airdrop`, `Spending`, `Lost/Stolen`.

**Date format:** `YYYY-MM-DD HH:MM:SS`.

**Notes:**
- The `Exchange/Wallet` field should identify the source (e.g., "Jupiter", "Raydium", "Phantom Wallet").
- CoinLedger pairs each trade row into buy/sell internally.

### TokenTax CSV

**Columns:** `Type`, `BuyAmount`, `BuyCurrency`, `SellAmount`, `SellCurrency`, `FeeAmount`, `FeeCurrency`, `Exchange`, `Group`, `Comment`, `Date`.

**Types:** `Trade`, `Income`, `Staking`, `Airdrop`, `Spending`, `Gift`, `Lost`, `Mining`.

**Date format:** `YYYY-MM-DD HH:MM:SS UTC`.

**Group field:** Optional grouping label for related transactions.

### TurboTax / TaxAct CSV

Both accept a simplified Form 8949-style CSV.

**Columns:** `Description of Property`, `Date Acquired`, `Date Sold`, `Proceeds`, `Cost Basis`, `Gain or Loss`.

**Date format:** `MM/DD/YYYY`.

**Notes:**
- Proceeds and Cost Basis are in USD.
- Gain or Loss = Proceeds - Cost Basis.
- Short-term and long-term should be in separate sections or files.

## Form 8949 Field Mapping

### Column Definitions

| Column | Field | Source | Notes |
|---|---|---|---|
| (a) | Description of property | `"{amount} {currency}"` | e.g., "2.5 SOL" |
| (b) | Date acquired | Trade journal / on-chain timestamp | MM/DD/YYYY |
| (c) | Date sold or disposed of | Disposal timestamp | MM/DD/YYYY |
| (d) | Proceeds | USD value at disposal | Sale price minus exchange fees |
| (e) | Cost or other basis | USD value at acquisition | Purchase price plus fees |
| (f) | Code | IRS code if applicable | Usually blank for crypto |
| (g) | Adjustment amount | Wash sale or other adjustments | Usually 0 |
| (h) | Gain or loss | `(d) - (e) + (g)` | Negative = loss |

### Check Box Rules

- **(A)** Basis reported to IRS — Rarely applies to crypto (no 1099-B from DEXs).
- **(B)** Basis NOT reported to IRS — Most common for DEX trades.
- **(C)** Form 1099-B not received — Use when no 1099-B was issued.

### Part I vs Part II

- **Part I** — Short-term: acquired and disposed within 365 days.
- **Part II** — Long-term: held for more than 365 days.
- Holding period starts the day after acquisition.

## Solana Transaction Type Classification

### Classification Rules

| Tx Pattern | Tax Type | Sent | Received | Label |
|---|---|---|---|---|
| Jupiter swap (single-hop) | Trade | Input token | Output token | swap |
| Jupiter swap (multi-hop) | Trade | First input | Final output | swap |
| LP deposit (add liquidity) | Disposal | Token A + Token B | LP token | liquidity_in |
| LP withdrawal (remove liquidity) | Acquisition | LP token | Token A + Token B | liquidity_out |
| Staking reward claim | Income | — | Reward token | staking |
| Airdrop receipt | Income | — | Airdrop token | airdrop |
| Token migration (1:1) | Non-taxable | Old token | New token | migration |
| Failed transaction | Non-taxable | — | — | (exclude) |
| NFT purchase | Trade | SOL/token | NFT | swap |
| Rent recovery (account close) | Non-taxable | — | SOL (rent) | cost |

### Multi-Hop Swap Handling

Jupiter routes through intermediate tokens for better pricing. For tax:
1. Parse the swap instruction to find the initial input and final output.
2. Ignore intermediate token transfers within the same transaction.
3. Record as a single trade: input token -> output token.
4. Transaction fee is the SOL fee on the outer transaction.

### Identifying Failed Transactions

A Solana transaction is failed if:
- `meta.err` is not `null` in the transaction response.
- The transaction status is `Err`.
- Inner instructions may have executed partially but the overall tx reverted.

Failed transactions still consume SOL for fees. The fee is **not** automatically deductible but may be claimed as a business expense if trading is a business activity.

## Reconciliation Methodology

### Step 1: Collect Sources

- **Journal trades**: Internal records with timestamps, amounts, tx hashes.
- **On-chain history**: Fetched via Helius `getSignaturesForAddress` + parsed transactions.

### Step 2: Primary Match (by tx hash)

Match journal entries to on-chain transactions by `tx_hash` / signature. This is the strongest match.

### Step 3: Secondary Match (by timestamp + amount)

For journal entries without tx hashes, attempt fuzzy matching:
- Timestamp within 60-second window.
- Amount within 0.1% relative tolerance.
- Same token pair.

### Step 4: Classify Unmatched

- **Journal-only entries**: Potentially from off-chain venues (CEX) or manual errors.
- **On-chain-only entries**: Missed journal entries — need to be added.
- **Amount mismatches**: Possible slippage discrepancies or partial fills.

### Step 5: Generate Report

Output a reconciliation report with:
- Match rate percentage.
- List of unmatched entries with suggested actions.
- List of mismatched amounts with differences.
- Summary statistics (total trades, total volume, date range).

## Planned Enhancements

- **Wash sale detection**: Flag disposals where the same or substantially identical asset was repurchased within 30 days (note: IRS has not issued definitive guidance on wash sale rules for crypto as of 2025, but proposed regulations may apply starting 2026).
- **Multi-wallet aggregation**: Combine exports across multiple Solana wallets into a single tax report.
- **CEX import parsing**: Ingest CSVs from Coinbase, Kraken, Binance and merge with on-chain data.
- **Lot tracking UI**: Visual tool for specific identification lot selection.
- **Schedule D summary**: Auto-generate Schedule D totals from Form 8949 line items.
- **International formats**: Support for HMRC (UK), ATO (Australia), CRA (Canada) reporting requirements.
