# Trade Record Format — Complete Schema

## Overview

Every trade is a structured record capturing context at entry, outcome at exit, and reflective notes. The schema supports single-fill trades, scaled entries, and partial exits.

## Complete Field Schema (18 Fields)

### Required Fields

| # | Field | Type | Description |
|---|-------|------|-------------|
| 1 | `id` | string | Unique trade ID. Format: `T-YYYYMMDD-NNN` |
| 2 | `token` | string | Token symbol (e.g., `SOL`, `BONK`, `JUP`) |
| 3 | `direction` | string | `long` or `short` |
| 4 | `entry_date` | string | ISO 8601 UTC timestamp of entry |
| 5 | `entry_price` | float | Entry price in USD or SOL |
| 6 | `size_sol` | float | Position size in SOL |
| 7 | `strategy` | string | Strategy tag from taxonomy |
| 8 | `rationale` | string | Written reason for the trade, recorded before entry |
| 9 | `outcome` | string | `win`, `loss`, or `breakeven` |

### Recommended Fields

| # | Field | Type | Description |
|---|-------|------|-------------|
| 10 | `exit_date` | string | ISO 8601 UTC timestamp of final exit |
| 11 | `exit_price` | float | Exit price (or VWAP for scaled exits) |
| 12 | `pnl_sol` | float | Realized P&L in SOL |
| 13 | `pnl_pct` | float | Realized P&L as percentage |
| 14 | `hold_time_minutes` | int | Total hold time in minutes |

### Optional Fields

| # | Field | Type | Description |
|---|-------|------|-------------|
| 15 | `size_usd` | float | Position size in USD at entry |
| 16 | `setup_quality` | int | Self-rated 1-10 quality of the setup |
| 17 | `emotional_state` | string | Emotional state at entry: `calm`, `anxious`, `excited`, `frustrated`, `fomo`, `revenge` |
| 18 | `lessons` | string | Post-trade reflection on what was learned |
| — | `tags` | list[str] | Freeform tags for filtering: `high-conviction`, `scalp`, `swing`, etc. |
| — | `stop_price` | float | Planned stop-loss price |
| — | `target_price` | float | Planned take-profit price |
| — | `risk_reward` | float | Planned risk:reward ratio |
| — | `fees_sol` | float | Transaction fees paid |
| — | `slippage_bps` | float | Observed slippage in basis points |
| — | `exits` | list | Partial exit records (see below) |
| — | `entries` | list | Scaled entry records (see below) |
| — | `screenshot_path` | string | Path to chart screenshot at entry |

## Strategy Tagging Taxonomy

Use a two-level hierarchy: `category-subcategory`.

### Momentum

| Tag | Description |
|-----|-------------|
| `momentum-breakout` | Price breaks key level with volume confirmation |
| `trend-continuation` | Entry on pullback within established trend |
| `pullback-entry` | Buy the dip in an uptrend |
| `volume-spike` | Unusual volume triggers entry |
| `new-high` | Token making new highs, riding momentum |

### Mean Reversion

| Tag | Description |
|-----|-------------|
| `range-fade` | Fade the edges of an established range |
| `oversold-bounce` | RSI/BB-based oversold entry |
| `deviation-snap` | Entry when price deviates N std devs from VWAP |
| `gap-fill` | Trading a gap fill |

### Event-Driven

| Tag | Description |
|-----|-------------|
| `listing-play` | New CEX/DEX listing momentum |
| `catalyst-trade` | Known upcoming catalyst (airdrop, launch) |
| `news-reaction` | Trading the reaction to news/announcement |

### On-Chain

| Tag | Description |
|-----|-------------|
| `whale-follow` | Following large wallet activity |
| `wallet-copy` | Copying a tracked profitable wallet |
| `flow-signal` | DEX flow imbalance signal |
| `holder-shift` | Significant change in holder distribution |

### DeFi

| Tag | Description |
|-----|-------------|
| `lp-entry` | Providing liquidity to a pool |
| `yield-farm` | Yield farming position |
| `arb-capture` | Arbitrage opportunity |

### Discretionary

| Tag | Description |
|-----|-------------|
| `gut-feel` | No formal setup — mark these for review |
| `revenge` | Re-entry after loss — always flag |
| `fomo` | Fear of missing out entry — always flag |

## Rationale Templates

Record rationale **before** placing the trade to enforce deliberation.

### Momentum Template

```
[TOKEN] breaking [LEVEL] on [TIMEFRAME] with [CONFIRMATION].
Volume is [X]x average. Target [PRICE] ([X]% up), stop [PRICE] ([X]% down).
R:R = [X]:1. Sizing [X] SOL ([X]% of portfolio).
```

### Mean Reversion Template

```
[TOKEN] at [X] standard deviations from [MEAN_TYPE] on [TIMEFRAME].
Historical reversion rate at this level: [X]%. Target reversion to [PRICE].
Stop beyond [PRICE] ([X] additional std devs). R:R = [X]:1.
```

### On-Chain Template

```
[SIGNAL_TYPE] detected: [DESCRIPTION].
Wallet [ADDRESS_PREFIX] has [X]% historical accuracy on similar trades.
Entry at [PRICE], target [PRICE], stop [PRICE].
```

### Event-Driven Template

```
Catalyst: [EVENT] expected [DATE/TIME].
Historical precedent: [SIMILAR_EVENTS] resulted in [X]% avg move.
Entry at [PRICE], exit plan: [DESCRIPTION].
```

## Partial Exits

When scaling out of a position, use the `exits` array:

```json
{
  "id": "T-20250310-001",
  "token": "SOL",
  "entry_price": 142.50,
  "size_sol": 10.0,
  "exits": [
    {
      "date": "2025-03-10T15:00:00Z",
      "price": 145.00,
      "size_pct": 33,
      "size_sol": 3.3,
      "reason": "first-target",
      "pnl_sol": 0.058
    },
    {
      "date": "2025-03-10T16:00:00Z",
      "price": 148.00,
      "size_pct": 33,
      "size_sol": 3.3,
      "reason": "second-target",
      "pnl_sol": 0.127
    },
    {
      "date": "2025-03-10T17:30:00Z",
      "price": 144.00,
      "size_pct": 34,
      "size_sol": 3.4,
      "reason": "trailing-stop",
      "pnl_sol": 0.036
    }
  ],
  "pnl_sol": 0.221,
  "exit_price": 145.67
}
```

The parent `exit_price` is the VWAP of all exits. The parent `pnl_sol` is the sum.

## Scaled Entries

When scaling into a position, use the `entries` array:

```json
{
  "id": "T-20250310-002",
  "token": "JUP",
  "entries": [
    {"date": "2025-03-10T10:00:00Z", "price": 0.85, "size_sol": 3.0, "reason": "initial"},
    {"date": "2025-03-10T11:00:00Z", "price": 0.82, "size_sol": 3.0, "reason": "add-on-dip"},
    {"date": "2025-03-10T12:30:00Z", "price": 0.80, "size_sol": 4.0, "reason": "final-add"}
  ],
  "entry_price": 0.821,
  "size_sol": 10.0
}
```

The parent `entry_price` is the VWAP of all entries.

## JSON Storage Format

```json
{
  "journal_version": "1.0",
  "trader_id": "anon",
  "created": "2025-01-01T00:00:00Z",
  "updated": "2025-03-10T14:30:00Z",
  "trades": []
}
```

## CSV Export Format

CSV uses flat columns. Partial exits are collapsed to summary values.

```csv
id,token,direction,entry_date,entry_price,size_sol,size_usd,strategy,setup_quality,rationale,exit_date,exit_price,pnl_sol,pnl_pct,outcome,hold_time_minutes,emotional_state,lessons
T-20250310-001,SOL,long,2025-03-10T14:30:00Z,142.50,5.0,712.50,momentum-breakout,8,"4h resistance break with volume",2025-03-10T16:45:00Z,146.20,0.648,2.60,win,135,calm,"Patience through pullback"
```

## Field Validation Rules

| Field | Validation |
|-------|-----------|
| `id` | Must match `T-YYYYMMDD-NNN` pattern |
| `direction` | Must be `long` or `short` |
| `entry_price` | Must be > 0 |
| `size_sol` | Must be > 0 |
| `outcome` | Must be `win`, `loss`, or `breakeven` |
| `setup_quality` | Must be 1-10 |
| `emotional_state` | Must be from allowed list |
| `pnl_pct` | Computed: `(exit_price - entry_price) / entry_price * 100` for longs |
| `hold_time_minutes` | Computed from entry/exit dates |
