# Trade Classification — Buy/Sell Identification on Solana DEXes

## Core Principle

On AMM-based DEXes, every trade is a swap between two tokens through a liquidity pool.
There is no explicit "buy" or "sell" order type. Classification depends on which token
the trader is spending (input) and which they are receiving (output), relative to the
token you are analyzing.

## Classification Rules

### Rule 1: Quote Token Direction

For any token pair where one side is a quote asset (SOL, USDC, USDT):

| Input Token | Output Token | Classification | Rationale |
|-------------|-------------|----------------|-----------|
| SOL | Target Token | **Buy** | Spending SOL to acquire token |
| USDC/USDT | Target Token | **Buy** | Spending stables to acquire token |
| Target Token | SOL | **Sell** | Liquidating token for SOL |
| Target Token | USDC/USDT | **Sell** | Liquidating token for stables |

### Rule 2: Token-to-Token Swaps

When neither side is a standard quote asset (e.g., Token A swapped for Token B via
a multi-hop route):

- If analyzing Token A: the swap is a **sell** of A
- If analyzing Token B: the swap is a **buy** of B
- The same transaction can be a buy for one token and a sell for another

### Rule 3: Multi-Hop Routes

Jupiter and other aggregators often route through intermediate pools. The classification
should be based on the **net effect** — what the user's wallet started with and ended with:

```python
def classify_swap(input_mint: str, output_mint: str, target_mint: str) -> str:
    """Classify a swap as buy or sell for the target token.

    Args:
        input_mint: The token mint the trader spent.
        output_mint: The token mint the trader received.
        target_mint: The token we are analyzing.

    Returns:
        'buy', 'sell', or 'unknown'.
    """
    if output_mint == target_mint:
        return "buy"
    elif input_mint == target_mint:
        return "sell"
    return "unknown"
```

## Data Source Classification

### Birdeye Trade History

Endpoint: `GET /defi/txs/token`

Birdeye provides pre-classified trades:
```json
{
  "txHash": "5abc...",
  "side": "buy",
  "from": {"address": "So11...", "amount": 1.5},
  "to": {"address": "EPjF...", "amount": 150000},
  "volumeUsd": 225.0,
  "owner": "7xKX..."
}
```

The `side` field is already resolved. Use it directly.

### DexScreener

DexScreener pair data includes volume breakdowns but individual trade classification
requires inspecting pair-level transactions. The `volume.buys` and `volume.sells`
fields on the pair object give aggregate counts.

### Helius Parsed Transactions

Helius returns parsed swap instructions. Extract input/output from the instruction data:

```python
def classify_from_helius(parsed_tx: dict, target_mint: str) -> str | None:
    """Classify a Helius parsed transaction for the target token."""
    for ix in parsed_tx.get("instructions", []):
        if ix.get("programId") in KNOWN_DEX_PROGRAMS:
            transfers = ix.get("innerInstructions", [])
            # Find token transfers to determine input/output
            input_mint = extract_input_mint(transfers)
            output_mint = extract_output_mint(transfers)
            if output_mint == target_mint:
                return "buy"
            if input_mint == target_mint:
                return "sell"
    return None

KNOWN_DEX_PROGRAMS = [
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",  # Jupiter V6
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",   # Orca Whirlpool
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", # Raydium AMM
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", # Raydium CLMM
]
```

## Trade Size Buckets

Classify trades by size to separate whale activity from retail flow:

| Bucket | SOL Equivalent | USD Approximate | Typical Actor |
|--------|---------------|-----------------|---------------|
| Micro | < 0.1 SOL | < $15 | Dust, test txs, sniper bots |
| Small | 0.1 – 1 SOL | $15 – $150 | Retail / casual traders |
| Medium | 1 – 10 SOL | $150 – $1,500 | Active traders |
| Large | 10 – 50 SOL | $1,500 – $7,500 | Serious positions |
| Whale | 50 – 200 SOL | $7,500 – $30,000 | Whales |
| Mega | 200+ SOL | $30,000+ | Institutions / big whales |

**Note:** USD thresholds shift with SOL price. Use SOL-denominated buckets as primary
and show USD as supplementary.

```python
def classify_trade_size(sol_amount: float) -> str:
    """Classify a trade into a size bucket based on SOL amount."""
    if sol_amount < 0.1:
        return "micro"
    elif sol_amount < 1.0:
        return "small"
    elif sol_amount < 10.0:
        return "medium"
    elif sol_amount < 50.0:
        return "large"
    elif sol_amount < 200.0:
        return "whale"
    else:
        return "mega"
```

## Aggregation Periods

Different timeframes reveal different patterns:

| Period | Use Case |
|--------|----------|
| 1 minute | Scalping signals, real-time flow |
| 5 minutes | Short-term momentum, entry timing |
| 1 hour | Intraday pressure, session analysis |
| 4 hours | Swing trading signals |
| 24 hours | Daily sentiment, accumulation/distribution |

### Rolling vs Fixed Windows

- **Fixed windows** (e.g., every hour on the hour) — simpler, good for profiles
- **Rolling windows** (e.g., last 60 minutes from now) — smoother, better for signals

For real-time signals, use rolling windows. For historical profiles, use fixed windows.

## Volume-Weighted Classification (VWAP Method)

An alternative classification approach uses VWAP deviation:

1. Compute the VWAP over a period
2. Trades executed above VWAP lean toward **buy** pressure (buyer willing to pay premium)
3. Trades executed below VWAP lean toward **sell** pressure (seller accepting discount)

```python
def vwap_classify(price: float, vwap: float, threshold: float = 0.001) -> str:
    """Classify trade direction based on VWAP deviation.

    Args:
        price: Execution price of the trade.
        vwap: Volume-weighted average price over the period.
        threshold: Minimum deviation to classify (default 0.1%).

    Returns:
        'buy_pressure', 'sell_pressure', or 'neutral'.
    """
    deviation = (price - vwap) / vwap
    if deviation > threshold:
        return "buy_pressure"
    elif deviation < -threshold:
        return "sell_pressure"
    return "neutral"
```

This method supplements direct buy/sell classification and is especially useful when
the `side` field is unavailable.

## Edge Cases

1. **Wrapped SOL trades** — wSOL (So11...) should be treated the same as native SOL
2. **Stable-to-stable** — USDC→USDT swaps are not buy or sell for either; skip them
3. **Self-referential** — Token→Token swaps through the same pool (rare, usually arb)
4. **Failed transactions** — Always filter for successful transactions only
5. **Partial fills** — Jupiter routes may partially fill; use the actual amounts, not requested
