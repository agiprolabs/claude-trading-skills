# Slippage Curves — Mathematical Models and Empirical Estimation

## Constant-Product AMM Slippage

In a constant-product AMM (xy = k), the price impact of a trade is deterministic.

### Buy Side (SOL to TOKEN)

Given a pool with `x` SOL and `y` TOKEN reserves:

```
k = x * y                    (invariant)
x_new = x + Δx               (add SOL)
y_new = k / x_new             (new TOKEN reserve)
tokens_out = y - y_new         (tokens received)
tokens_out = y * Δx / (x + Δx)
```

**Price impact** (slippage):

```
effective_price = Δx / tokens_out = (x + Δx) / y
spot_price = x / y
slippage = effective_price / spot_price - 1
slippage = Δx / (x + Δx)
```

**Key insight**: Slippage depends only on the ratio of trade size to pool reserve, not on the token price.

### Sell Side (TOKEN to SOL)

Symmetrically:

```
slippage = Δy / (y + Δy)
```

Where `Δy` is the number of tokens being sold and `y` is the token reserve.

### Worked Example

Pool: 50 SOL / 5,000,000 TOKEN (spot price = 0.00001 SOL/TOKEN)

**Buying 1 SOL worth of TOKEN:**

```
Δx = 1 SOL, x = 50 SOL
slippage = 1 / (50 + 1) = 1.96%
tokens_out = 5,000,000 * 1 / (50 + 1) = 98,039 TOKEN
effective_price = 1 / 98,039 = 0.00001020 SOL/TOKEN
```

**Buying 5 SOL worth:**

```
slippage = 5 / (50 + 5) = 9.09%
tokens_out = 5,000,000 * 5 / (50 + 5) = 454,545 TOKEN
```

**Buying 0.1 SOL worth:**

```
slippage = 0.1 / (50 + 0.1) = 0.20%
```

### Trade Size to Slippage Table (50 SOL reserve)

| Trade Size (SOL) | Slippage | Tokens Received |
|-------------------|----------|-----------------|
| 0.1 | 0.20% | 9,980 |
| 0.5 | 0.99% | 49,505 |
| 1.0 | 1.96% | 98,039 |
| 2.0 | 3.85% | 192,308 |
| 5.0 | 9.09% | 454,545 |
| 10.0 | 16.67% | 833,333 |
| 25.0 | 33.33% | 1,666,667 |

## Concentrated Liquidity (CLMM) Slippage

CLMM pools (Orca Whirlpool, Raydium CLMM, Meteora DLMM) concentrate liquidity in a price range `[p_low, p_high]`.

### Effective Depth

Within the active range, a CLMM pool with TVL `L` concentrated in range `[p_low, p_high]` provides the same depth as a constant-product pool with TVL:

```
L_effective = L * p_spot / (sqrt(p_high) - sqrt(p_low))
```

For a $50K CLMM pool concentrated in a +/-5% range around $0.01:

```
p_low = 0.0095, p_high = 0.0105
L_effective ≈ $50K * sqrt(0.01) / (sqrt(0.0105) - sqrt(0.0095))
L_effective ≈ $500K equivalent constant-product depth
```

### Range Exhaustion

If a trade moves the price outside the active range, remaining liquidity drops to zero. The trade fails or routes through other pools. This makes large trades on CLMM pools riskier if ranges are narrow.

### Tick Crossing

CLMM pools have discrete price ticks. Each tick may have different liquidity. Slippage calculation requires summing across ticks:

```
total_slippage = Σ (slippage_at_tick_i * amount_at_tick_i) / total_amount
```

This is complex to compute off-chain. The empirical approach (querying Jupiter) is more practical.

## Empirical Slippage Estimation

### Method

Query Jupiter Quote API at multiple trade sizes and measure actual output:

```python
import httpx

SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS = 1_000_000_000
SIZES = [0.1, 0.5, 1.0, 5.0, 10.0, 25.0]

async def build_slippage_curve(token_mint: str) -> list[dict]:
    """Build empirical slippage curve using Jupiter quotes."""
    results = []
    base_rate = None

    async with httpx.AsyncClient(timeout=15) as client:
        for sol in SIZES:
            resp = await client.get(
                "https://api.jup.ag/quote/v1",
                params={
                    "inputMint": SOL_MINT,
                    "outputMint": token_mint,
                    "amount": str(int(sol * LAMPORTS)),
                    "slippageBps": 5000,
                },
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            out = int(data["outAmount"])
            rate = out / sol if sol > 0 else 0
            if base_rate is None:
                base_rate = rate
            slippage_bps = int((1 - rate / base_rate) * 10000) if base_rate > 0 else 0
            results.append({"sol": sol, "tokens": out, "slippage_bps": max(0, slippage_bps)})

    return results
```

### Advantages Over Analytical Models

1. **Multi-pool routing**: Jupiter splits trades across pools. Empirical measurement captures this.
2. **CLMM complexity**: No need to fetch tick data and compute across ranges.
3. **Real fees**: Jupiter includes swap fees in the quote.
4. **Current state**: Reflects actual on-chain liquidity at query time.

### Limitations

1. **Point-in-time**: Liquidity changes constantly. Curves are valid for minutes, not hours.
2. **Jupiter-specific**: Other aggregators may route differently.
3. **Rate limits**: Querying 6 sizes per token adds up. Batch wisely.

## Multi-Pool Routing Impact

Jupiter splits large trades across multiple pools to minimize slippage. A token with 3 pools of $20K each will have lower slippage than a token with 1 pool of $60K for large trades, because Jupiter can parallelize.

**Empirical observation**: Multi-pool routing typically reduces slippage by 30-60% compared to single-pool execution for trades above 1% of the largest pool.

## Slippage Thresholds by Trade Type

| Trade Type | Target Holding | Max Entry Slippage | Max Exit Slippage | Notes |
|------------|---------------|-------------------|-------------------|-------|
| Scalp | Minutes-hours | 50 bps (0.5%) | 50 bps | Must exit quickly; both sides matter |
| Swing | Hours-days | 200 bps (2%) | 200 bps | More forgiving on entry |
| Position | Days-weeks | 500 bps (5%) | 300 bps | Large position; exit matters more |
| Snipe | Seconds | 1000+ bps | N/A | Speed over price; high risk |

## Curve Fitting for Prediction

For positions between measured sizes, fit a power curve:

```
slippage_bps = a * trade_size^b
```

Where `a` and `b` are fitted from empirical data. For constant-product pools, `b ≈ 1.0`. For multi-pool routing, `b < 1.0` (sub-linear due to splitting).

```python
import numpy as np

def fit_slippage_curve(sizes: list[float], slippages_bps: list[int]) -> tuple[float, float]:
    """Fit power curve to empirical slippage data.

    Returns (a, b) where slippage_bps = a * size^b.
    """
    log_sizes = np.log(sizes)
    log_slips = np.log([max(s, 1) for s in slippages_bps])
    b, log_a = np.polyfit(log_sizes, log_slips, 1)
    return float(np.exp(log_a)), float(b)
```

## Inverting the Curve

Given a maximum slippage budget, find the maximum trade size:

```
max_size = (max_slippage_bps / a) ^ (1/b)
```

This is the primary input to position sizing from liquidity.
