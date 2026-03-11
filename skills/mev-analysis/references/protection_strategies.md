# MEV Protection Strategies

## Strategy 1: Tight Slippage Settings

### Rationale

Sandwich attack profit is bounded by your slippage tolerance. If you set slippage to 50bps, the attacker can extract at most ~50bps of your trade value (minus their costs). Tighter slippage makes sandwiching less profitable or unprofitable.

### Implementation

```python
# Jupiter API quote with tight slippage
params = {
    "inputMint": "So11111111111111111111111111111111111111112",
    "outputMint": token_mint,
    "amount": str(amount_lamports),
    "slippageBps": "50",  # 0.5% — tight for liquid tokens
}
```

### Recommended Settings by Pool Liquidity

| Pool Liquidity (USD) | Slippage (bps) | Rationale |
|-----------------------|-----------------|-----------|
| > $10M | 30-50 | Deep liquidity, minimal natural slippage |
| $1M - $10M | 50-100 | Moderate liquidity, need some buffer |
| $100K - $1M | 100-200 | Thinner books, more natural price impact |
| < $100K | 200-500 | Very thin, high natural slippage, high MEV risk |

### Trade-offs

- **Too tight**: Transaction fails (you still pay base fee, get no execution)
- **Too loose**: Sandwich bots extract maximum value
- **Sweet spot**: Set slippage to ~1.5x your expected price impact

### Dynamic Approach

Monitor recent price volatility and adjust:
```python
def compute_safe_slippage(
    expected_impact_bps: float,
    recent_volatility_bps: float,
    safety_margin: float = 1.5,
) -> int:
    """Compute slippage that covers natural movement but limits MEV."""
    base = expected_impact_bps + recent_volatility_bps
    return max(30, int(base * safety_margin))
```

## Strategy 2: Jito Bundles

### Rationale

By submitting your transaction as a Jito bundle, you control the execution context. No searcher can insert transactions before or after yours within your bundle. You pay a tip for priority inclusion.

### When to Use

- Trade size > 5 SOL
- Trading illiquid tokens (< $1M pool)
- During high-MEV periods (meme coin launches, volatile markets)
- When you need guaranteed execution ordering

### Implementation

```python
import httpx
import base64

JITO_BLOCK_ENGINE = "https://mainnet.block-engine.jito.wtf"

async def get_tip_accounts() -> list[str]:
    """Fetch current Jito tip accounts."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{JITO_BLOCK_ENGINE}/api/v1/bundles",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTipAccounts",
                "params": [],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])

async def send_bundle(
    serialized_txs: list[bytes],
    tip_lamports: int = 100_000,
) -> str:
    """Submit a bundle to Jito block engine.

    Args:
        serialized_txs: List of serialized, signed transactions.
        tip_lamports: Tip amount (1 SOL = 1_000_000_000 lamports).

    Returns:
        Bundle ID string.
    """
    encoded = [base64.b64encode(tx).decode() for tx in serialized_txs]
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{JITO_BLOCK_ENGINE}/api/v1/bundles",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [encoded],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("result", "")
```

### Tip Sizing Guide

| Scenario | Tip (SOL) | Tip (Lamports) |
|----------|-----------|----------------|
| Low priority, small trade | 0.0001 | 100,000 |
| Normal priority | 0.001 | 1,000,000 |
| High priority, large trade | 0.005 | 5,000,000 |
| Urgent (volatile market) | 0.01-0.05 | 10,000,000-50,000,000 |

**Rule of thumb**: Tip should be < 0.1% of trade value. If tip exceeds MEV risk, skip the bundle.

### Bundle Status Checking

```python
async def check_bundle_status(bundle_id: str) -> dict:
    """Check if a bundle was included."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{JITO_BLOCK_ENGINE}/api/v1/bundles",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBundleStatuses",
                "params": [[bundle_id]],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("result", {})
```

## Strategy 3: Private / Protected RPCs

### Rationale

Standard public RPCs forward your transaction to multiple validators, increasing the number of parties that can observe it. Private RPCs minimize this exposure.

### Providers

| Provider | Feature | Endpoint |
|----------|---------|----------|
| Jito | Bundle submission | `mainnet.block-engine.jito.wtf` |
| Helius | Staked connections, priority fees | `mainnet.helius-rpc.com/?api-key=KEY` |
| QuickNode | Private transaction submission | Via QuickNode endpoint |
| Triton | Dedicated RPC with staked connections | Custom endpoint |

### How Staked Connections Help

Validators prioritize transactions from staked connections. With a staked RPC:
- Your transaction goes directly to the leader via a trusted channel
- Less forwarding through intermediary nodes
- Faster inclusion (competitive advantage over public RPC users)

### Implementation

```python
# Use Helius with staked connection for reduced MEV exposure
HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={os.getenv('HELIUS_API_KEY')}"

async def send_protected_transaction(signed_tx_base64: str) -> str:
    """Send transaction via Helius staked connection."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            HELIUS_RPC,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [
                    signed_tx_base64,
                    {"skipPreflight": False, "maxRetries": 3},
                ],
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json().get("result", "")
```

## Strategy 4: Trade Splitting

### Rationale

MEV profitability scales with trade size. Splitting a large trade into smaller pieces makes each individual piece less attractive to sandwich.

### When to Split

- Trade is > 1% of pool liquidity
- Estimated sandwich cost > $5
- Token is actively targeted by MEV bots (high volume micro-cap)

### Implementation

```python
import asyncio

async def execute_split_trades(
    total_sol: float,
    pool_liquidity_usd: float,
    max_pct_per_trade: float = 0.5,
    delay_seconds: int = 30,
    sol_price: float = 150.0,
) -> list[dict]:
    """Execute a trade in smaller pieces to reduce MEV exposure.

    Note: This is a framework. In production, each piece requires
    building, signing, and submitting a real transaction.
    """
    total_usd = total_sol * sol_price
    trade_pct = (total_usd / pool_liquidity_usd) * 100

    if trade_pct <= max_pct_per_trade:
        return [{"piece": 1, "sol": total_sol, "status": "single_trade"}]

    n = max(2, int(trade_pct / max_pct_per_trade) + 1)
    per_trade = total_sol / n
    results = []

    for i in range(n):
        if i > 0:
            await asyncio.sleep(delay_seconds)
        results.append({
            "piece": i + 1,
            "sol": round(per_trade, 4),
            "status": "submitted",
        })
    return results
```

### Trade-offs

- **Pro**: Each piece has lower MEV risk
- **Con**: Total execution takes longer; price may move against you
- **Con**: More transaction fees (base fee per trade)
- **Con**: Potential information leakage if pattern is detected

## Strategy 5: Jupiter MEV Protection

### Dynamic Slippage

Jupiter's dynamic slippage mode adjusts the slippage parameter based on:
- Current market volatility
- Historical fill rates at different slippage levels
- Pool depth and expected price impact

```python
params = {
    "inputMint": input_mint,
    "outputMint": output_mint,
    "amount": str(amount_lamports),
    "dynamicSlippage": "true",
    "prioritizationFeeLamports": "auto",
}
```

### Transaction Landing Improvements

Jupiter v6 includes retry logic and priority fee optimization that reduces the chance of failed transactions when using tight slippage.

## Decision Matrix

Use this matrix to select protection level:

| Trade Size | Liquid Token (>$5M pool) | Mid Liquidity ($500K-$5M) | Low Liquidity (<$500K) |
|-----------|--------------------------|---------------------------|------------------------|
| < 1 SOL | No protection needed | Tight slippage (50-100bps) | Tight slippage (100-200bps) |
| 1-10 SOL | Tight slippage (50bps) | Jito bundle + tight slippage | Jito bundle + split |
| 10-50 SOL | Tight slippage + private RPC | Jito bundle + split (2-3x) | Split (5x+) + Jito bundles |
| > 50 SOL | Split (2-3x) + Jito | Split (5x+) + Jito + private RPC | Avoid or OTC |

## Cost-Benefit Analysis

Only protect when MEV risk exceeds protection cost (tip + extra fees + delay).

**Rule of thumb:** Under 0.5 SOL in liquid pools: skip protection. 0.5-5 SOL: tight slippage. 5-50 SOL: Jito bundle + tight slippage. Over 50 SOL: full stack (split + Jito + private RPC).
