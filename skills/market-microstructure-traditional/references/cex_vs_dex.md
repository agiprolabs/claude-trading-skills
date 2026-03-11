# CEX Order Book vs DEX AMM — Structural Comparison

A detailed comparison of the two dominant market structures in crypto:
centralized exchange limit order books (LOB) and decentralized exchange
automated market makers (AMM).

---

## Price Discovery

### LOB (CEX)
Prices emerge from the intersection of buyer and seller limit orders.
Market makers actively quote two-sided markets. Price reflects the
consensus of all participants' information.

**Advantages**: precise price expression, rapid information incorporation,
sub-millisecond updates.

### AMM (DEX)
Prices are determined by a mathematical bonding curve (e.g., x*y=k for
constant product). Price moves only when trades occur.

**Advantages**: always-on liquidity, no dependence on active market makers,
permissionless listing.

**Key difference**: LOB prices update between trades (quote revisions); AMM
prices only update on trades. This makes AMMs slower to incorporate
information, creating arbitrage opportunities that CEX-DEX arb bots exploit.

---

## Spread and Liquidity

### LOB Spread
Set by competing market makers. Narrower spreads indicate:
- More MM competition
- Higher volume (MMs can recoup costs faster)
- Lower volatility (lower inventory risk)
- Better fee tiers (maker rebates subsidize tighter quotes)

Typical BTC/USDT spread on Binance: 0.5-1 bps.

### AMM Implicit Spread
The AMM's "spread" comes from the fee tier plus the curve's price sensitivity:

```
implicit_spread ≈ 2 * fee_tier + price_impact_of_min_trade
```

For concentrated liquidity (Uniswap V3, Orca Whirlpools):

```
effective_spread ≈ 2 * fee_tier / sqrt(concentration_factor)
```

Higher concentration = tighter effective spread but more impermanent loss.

Typical SOL/USDC spread on Orca (5 bps fee tier): 10-15 bps.

---

## Order Types

### LOB
| Order Type | Behavior |
|---|---|
| Limit | Rests on book at specified price |
| Market | Fills immediately at best available |
| Stop-limit | Becomes limit when trigger price hit |
| IOC | Fill what you can, cancel the rest |
| FOK | Fill entirely or cancel |
| Post-only | Reject if would cross the spread |
| Iceberg | Shows only partial size |

### AMM
| Order Type | Behavior |
|---|---|
| Swap | Market order against the pool |
| Limit (via protocol) | Some DEXes offer limit orders (Jupiter, Serum) |
| DCA | Split order over time (Jupiter DCA) |

**Key difference**: LOBs offer far more order type flexibility. AMMs are
essentially market-order-only, though Jupiter and other aggregators add
limit order and DCA features on top.

---

## Adverse Selection

### LOB: Market Maker vs Informed Trader
MMs manage adverse selection by:
- Widening spreads during high-vol periods
- Reducing quote size when information asymmetry is high
- Skewing quotes away from inventory
- Cancelling and repricing in response to correlated asset moves

MM losses to informed flow are compensated by profits from uninformed flow.
The balance determines whether market making is profitable.

### AMM: Liquidity Provider vs Arbitrageur
LPs face adverse selection through **impermanent loss** — arbitrageurs trade
against the pool whenever the AMM price diverges from the true market price.

Key differences from LOB adverse selection:
- LPs cannot reprice (the curve is fixed for a given position)
- LPs cannot selectively avoid informed flow
- Loss is mechanical and predictable, not probabilistic
- Concentrated liquidity amplifies both fee income and IL

```
LP_return = fee_income - impermanent_loss - opportunity_cost
```

---

## Execution Latency

| Venue | Latency | Implications |
|---|---|---|
| Binance (colocated) | < 1 ms | HFT viable, speed advantage matters |
| Binance (API) | 5-50 ms | Fast enough for most strategies |
| Solana DEX | 400 ms (slot time) | Block-level granularity, MEV risk |
| Ethereum DEX | 12 s (block time) | Significant delay, high MEV risk |

**Implication**: latency-sensitive strategies (stat arb, market making) are
only viable on CEX or fast L1/L2 chains. Solana's 400ms slots make it the
most viable chain for on-chain market making.

---

## MEV and Fairness

### CEX
- Front-running is difficult (exchange controls matching engine)
- Colocated traders have speed advantage but cannot see pending orders
- Exchange may run proprietary trading desks (conflict of interest)

### DEX
- Pending transactions are visible in the mempool
- Sandwich attacks extract value from large swaps
- MEV bots compete via priority fees / Jito bundles on Solana
- Mitigation: private mempools, MEV protection (Flashbots Protect, Jito)

**Sandwich attack cost**: typically 10-100 bps on large DEX swaps.
Using MEV protection can eliminate this but may increase latency.

---

## Fee Structures

### CEX: Maker/Taker Model
```
maker_fee: 0.00% to 0.10% (often rebates at high tiers)
taker_fee: 0.03% to 0.10%
```

Makers (limit orders that add liquidity) pay less or receive rebates.
Takers (market orders that remove liquidity) pay more.

### DEX: Fixed Fee Tiers
```
Typical tiers: 1 bps, 5 bps, 30 bps, 100 bps
```

Fees go to LPs. No maker/taker distinction — all trades are "taker"
against the pool. Protocol may take a cut (e.g., Uniswap takes some
fee switch revenue).

**Cost comparison for a $10K trade**:

| Venue | Spread Cost | Fee | MEV Cost | Total |
|---|---|---|---|---|
| Binance (taker) | 1 bps | 10 bps | 0 | ~11 bps |
| Orca (5 bps pool) | 5 bps | 5 bps | 0-20 bps | 10-30 bps |

CEX is generally cheaper for large trades on major pairs. DEX can be
competitive for small trades on long-tail tokens.

---

## Hybrid Models

### CLOB on Chain (Phoenix, OpenBook)
On-chain central limit order books that combine LOB mechanics with
blockchain settlement. Solana's speed makes this viable.

**Tradeoffs**: LOB flexibility + on-chain transparency, but limited by
blockchain throughput and vulnerable to MEV.

### AMM + Order Book (Raydium)
Raydium's hybrid model routes liquidity between an AMM pool and the
OpenBook order book. Provides AMM convenience with LOB depth.

### Intent-Based Systems (Jupiter, CoW Protocol)
Orders express intent ("swap X for Y"), and solvers/aggregators find
the best execution path across multiple venues.

**Advantages**: MEV protection, optimal routing, price improvement.
**Disadvantages**: solver centralization risk, latency.

---

## When to Route Where

### Use CEX When:
- Trading BTC, ETH, SOL, or other major pairs
- Order size > $50K (better depth and lower impact)
- Latency matters (market making, arb)
- You need advanced order types (stop-loss, iceberg)
- Fee tier gives you maker rebates

### Use DEX When:
- Trading long-tail tokens not listed on CEX
- Composability with DeFi is needed (flash loans, MEV strategies)
- Censorship resistance is required
- Trade size is small (< $10K) on liquid pools
- You want transparent, verifiable execution

### Use Aggregator When:
- You want best execution across multiple DEX venues
- Order size is moderate and could benefit from split routing
- You want MEV protection (Jupiter with Jito integration)

---

## Monitoring Cross-Venue Execution

Track these metrics to evaluate venue quality:

```python
@dataclass
class VenueMetrics:
    """Execution quality metrics for a single venue."""
    venue: str
    avg_slippage_bps: float    # vs midprice at decision time
    avg_spread_bps: float      # observed spread
    fill_rate: float           # fraction of orders fully filled
    avg_latency_ms: float      # decision to fill
    fee_bps: float             # average fee paid
    mev_cost_bps: float        # estimated MEV extraction (DEX)

    @property
    def total_cost_bps(self) -> float:
        return self.avg_slippage_bps + self.fee_bps + self.mev_cost_bps
```

Compare venues on total cost, not just spread. A venue with tighter spreads
but higher fees and MEV costs may be worse overall.
