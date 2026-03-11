---
name: mev-analysis
description: MEV exposure assessment, sandwich attack detection, and protection strategies for Solana DEX trading
---

# MEV Analysis for Solana DEX Trading

Maximal Extractable Value (MEV) is the profit that validators and searchers can extract by reordering, inserting, or censoring transactions within a block. On Solana DEXes, MEV primarily manifests as sandwich attacks against swaps, cross-DEX arbitrage, and liquidation extraction. This skill covers detection, estimation, and protection strategies.

## What Is MEV on Solana?

MEV occurs when someone with transaction ordering power profits at other traders' expense. On Solana, the MEV supply chain works as follows:

1. **You submit a swap** through an RPC endpoint
2. **Searchers observe** your transaction (via RPC forwarding, block engine access, or leader TPU sniffing)
3. **Searcher constructs a profitable bundle** (e.g., sandwich your swap)
4. **Bundle submitted to Jito block engine** with a tip to the validator
5. **Validator includes the bundle** in the block, earning the tip
6. **You receive worse execution**; the searcher profits the difference

### How Solana MEV Differs from Ethereum

| Aspect | Ethereum | Solana |
|--------|----------|--------|
| Block time | 12 seconds | ~400ms slots |
| Mempool | Public mempool | No mempool (but tx visible in transit) |
| Ordering | Proposer-builder separation (PBS) | Jito block engine (~85%+ validators) |
| Bundle system | Flashbots bundles | Jito bundles with tips |
| MEV cost | Gas priority fees | Jito tips (SOL) |
| Latency pressure | Moderate | Extreme (sub-100ms decisions) |

Key Solana-specific factors:
- **No public mempool**: Transactions flow RPC → TPU → Leader, but searchers tap into this flow via Jito's block engine and modified validators
- **Known leader schedule**: The leader (block producer) schedule is known ~2 epochs ahead, letting searchers target specific leaders
- **Jito dominance**: ~85%+ of validators run the Jito-modified client, making Jito bundles the primary MEV vector
- **Speed**: 400ms slots mean MEV bots must operate in microseconds, favoring co-located infrastructure

## MEV Types on Solana

### 1. Sandwich Attacks

The most common MEV attack against retail traders.

**Mechanics:**
```
1. Attacker sees your pending swap: Buy 10 SOL worth of TOKEN_X
2. Front-run:  Attacker buys TOKEN_X first  → price rises
3. Your swap:  You buy TOKEN_X at higher price → worse execution
4. Back-run:   Attacker sells TOKEN_X         → profits the difference
```

**Your loss** = price impact from front-run + attacker's profit margin
**Attacker profit** = your_loss - jito_tip - transaction_fees

**Risk factors:**
- Trade size: Larger trades = more profitable to sandwich
- Token liquidity: Illiquid tokens = easier price manipulation
- Slippage setting: Wide slippage = more room for the attacker
- Pool type: CPMM pools more vulnerable than CLMM pools at concentrated ranges

### 2. Arbitrage (Cross-DEX)

Searchers capture price discrepancies between DEXes.

```
Pool A: TOKEN_X = 1.00 USDC
Pool B: TOKEN_X = 1.02 USDC
→ Buy on A, sell on B, profit 0.02 USDC per token (minus fees)
```

This is generally **beneficial** to the market — it equalizes prices across venues. However, your trade may trigger the arbitrage opportunity that the searcher captures.

### 3. Liquidation Extraction

When DeFi positions (Solend, Marginfi, Kamino) become undercollateralized, searchers race to liquidate them and claim the liquidation bonus (typically 5-10%).

### 4. JIT (Just-In-Time) Liquidity

Searchers add concentrated liquidity to a CLMM pool just before a large swap and remove it immediately after, earning swap fees without sustained impermanent loss exposure. This is a sophisticated MEV form that can actually **improve** execution for the swapper.

### 5. Back-Running

Trading immediately after a large swap that moved the price, capturing the reversion. Less harmful than sandwiching because it does not worsen your execution — it profits from the market response to your trade.

## Estimating MEV Exposure

Estimate your MEV risk before executing a trade:

```python
import httpx

def estimate_mev_risk(
    trade_size_sol: float,
    pool_liquidity_usd: float,
    slippage_bps: int,
    token_daily_volume_usd: float,
) -> dict:
    """Estimate sandwich attack profitability for a given trade.

    Returns risk assessment with estimated cost and recommendations.
    """
    # Trade as percentage of pool liquidity
    sol_price = 150.0  # approximate; fetch live price in production
    trade_usd = trade_size_sol * sol_price
    trade_pct_of_pool = (trade_usd / pool_liquidity_usd) * 100

    # Estimated price impact from constant-product AMM
    # price_impact ≈ trade_size / pool_liquidity (simplified)
    price_impact_bps = int(trade_pct_of_pool * 100)

    # Sandwich profitability: attacker captures portion of slippage headroom
    # Rough model: sandwich_profit ≈ 0.5 * slippage_headroom * trade_size
    slippage_headroom_bps = slippage_bps - price_impact_bps
    if slippage_headroom_bps < 0:
        slippage_headroom_bps = 0

    sandwich_profit_usd = (slippage_headroom_bps / 10000) * trade_usd * 0.5
    jito_tip_cost = 0.001 * sol_price  # ~0.001 SOL typical tip
    tx_fees = 0.000015 * sol_price * 2  # two transactions for sandwich

    net_mev_profit = sandwich_profit_usd - jito_tip_cost - tx_fees
    is_profitable_to_sandwich = net_mev_profit > 0.10  # $0.10 minimum

    # Volume ratio indicates MEV bot attention level
    volume_ratio = trade_usd / max(token_daily_volume_usd, 1)

    risk_level = "LOW"
    if is_profitable_to_sandwich and trade_pct_of_pool > 1.0:
        risk_level = "HIGH"
    elif is_profitable_to_sandwich or trade_pct_of_pool > 0.5:
        risk_level = "MEDIUM"

    return {
        "risk_level": risk_level,
        "trade_pct_of_pool": round(trade_pct_of_pool, 2),
        "estimated_price_impact_bps": price_impact_bps,
        "slippage_headroom_bps": slippage_headroom_bps,
        "estimated_sandwich_cost_usd": round(max(net_mev_profit, 0), 2),
        "is_profitable_to_sandwich": is_profitable_to_sandwich,
        "recommendations": _get_recommendations(
            risk_level, trade_size_sol, slippage_bps, trade_pct_of_pool
        ),
    }


def _get_recommendations(
    risk_level: str,
    trade_size_sol: float,
    slippage_bps: int,
    trade_pct_of_pool: float,
) -> list[str]:
    """Generate protection recommendations based on risk assessment."""
    recs = []
    if risk_level == "HIGH":
        recs.append("Use Jito bundle with 0.001-0.005 SOL tip")
        recs.append("Use private/protected RPC endpoint")
    if trade_pct_of_pool > 2.0:
        n_splits = max(2, int(trade_pct_of_pool))
        recs.append(f"Split into {n_splits} trades over 2-5 minutes")
    if slippage_bps > 100:
        recs.append(f"Reduce slippage from {slippage_bps}bps to 50-100bps")
    if risk_level in ("MEDIUM", "HIGH"):
        recs.append("Enable Jupiter dynamic slippage / MEV protection")
    if not recs:
        recs.append("Standard execution is likely safe for this trade size")
    return recs
```

## MEV Protection Strategies

### Strategy 1: Tight Slippage Settings

Set `slippageBps` as low as feasible. Sandwich profit is bounded by your slippage tolerance.

| Token Liquidity | Recommended Slippage |
|----------------|---------------------|
| > $5M pool | 50 bps (0.5%) |
| $1M - $5M pool | 100 bps (1%) |
| $100K - $1M pool | 150-200 bps |
| < $100K pool | 200-500 bps (high risk) |

**Trade-off:** Too-tight slippage causes failed transactions, costing you fees with no execution.

### Strategy 2: Jito Bundles

Submit your swap as a Jito bundle with a priority tip:

```python
import httpx

JITO_BLOCK_ENGINE = "https://mainnet.block-engine.jito.wtf"

async def submit_jito_bundle(
    signed_transactions: list[str],
    tip_lamports: int = 1_000_000,  # 0.001 SOL
) -> str:
    """Submit a transaction bundle to Jito block engine.

    Args:
        signed_transactions: Base64-encoded signed transactions.
        tip_lamports: Tip amount in lamports (1 SOL = 1e9 lamports).

    Returns:
        Bundle ID for tracking.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{JITO_BLOCK_ENGINE}/api/v1/bundles",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [signed_transactions],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("result", "")
```

**Tip guidelines:**
- Normal priority: 0.0001 - 0.001 SOL
- High priority: 0.001 - 0.01 SOL
- Urgent (volatile market): 0.01 - 0.05 SOL

### Strategy 3: Private/Protected RPCs

Send transactions through endpoints that do not expose them to searchers:

- **Jito bundles** (described above)
- **Helius priority fee API** with staked connections
- **QuickNode** private transaction submission
- **Direct TPU forwarding** (requires infrastructure)

### Strategy 4: Trade Splitting

For large trades (> 1% of pool liquidity), split execution:

```python
def compute_split_plan(
    total_sol: float,
    pool_liquidity_usd: float,
    sol_price: float = 150.0,
    max_pct_per_trade: float = 0.5,
) -> list[dict]:
    """Compute a trade splitting plan to minimize MEV exposure."""
    total_usd = total_sol * sol_price
    trade_pct = (total_usd / pool_liquidity_usd) * 100

    if trade_pct <= max_pct_per_trade:
        return [{"sol_amount": total_sol, "delay_seconds": 0}]

    n_splits = max(2, int(trade_pct / max_pct_per_trade) + 1)
    per_trade = total_sol / n_splits
    delay = 30  # seconds between trades

    return [
        {"sol_amount": round(per_trade, 4), "delay_seconds": i * delay}
        for i in range(n_splits)
    ]
```

### Strategy 5: Jupiter MEV Protection

Jupiter v6 includes built-in MEV protection features:
- **Dynamic slippage**: Automatically adjusts slippage to minimize sandwich window
- **Priority fee estimation**: Sets appropriate compute unit price
- **Transaction landing optimization**: Retry logic with increasing priority

Enable via Jupiter API:
```python
params = {
    "inputMint": "So11111111111111111111111111111111111111112",
    "outputMint": token_mint,
    "amount": str(amount_lamports),
    "slippageBps": "50",
    "dynamicSlippage": "true",        # Auto-adjust slippage
    "prioritizationFeeLamports": "auto",  # Auto priority fee
}
```

## Detecting Sandwich Attacks

After a trade, check whether you were sandwiched:

1. **Fetch your transaction** and identify the slot
2. **Fetch all transactions in that slot** involving the same token
3. **Look for the pattern**:
   - Transaction A: Buy TOKEN_X (before your tx in slot ordering)
   - Your transaction: Buy TOKEN_X (worse price than expected)
   - Transaction B: Sell TOKEN_X (after your tx, same signer as A)
4. **Verify**: Signer of A and B is the same wallet (the attacker)
5. **Estimate cost**: Difference between your expected and actual execution price

See `scripts/sandwich_detector.py` for a working implementation.

**Known MEV indicators:**
- Transaction signer has thousands of transactions per day
- Same-slot buy-then-sell of the same token around your swap
- Signer interacts with Jito tip program frequently
- Wallet has no token holdings (just in-and-out)

## Integration with Other Skills

- **`slippage-modeling`**: Use slippage estimates to set protective limits
- **`liquidity-analysis`**: Pool liquidity determines MEV vulnerability
- **`jupiter-api`**: Jupiter's MEV protection features and swap execution
- **`solana-onchain`**: On-chain transaction analysis for sandwich detection
- **`helius-api`**: Transaction parsing and historical analysis

## Files

### References
- `references/solana_mev_mechanics.md` — Solana block production, Jito block engine, MEV supply chain, and transaction flow paths
- `references/protection_strategies.md` — Detailed protection strategies with implementation guidance, cost-benefit analysis, and decision matrix

### Scripts
- `scripts/sandwich_detector.py` — Detects sandwich attacks around a given transaction signature using on-chain data
- `scripts/mev_risk_estimator.py` — Estimates MEV exposure for a planned trade based on token liquidity, trade size, and slippage settings
