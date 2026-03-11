# Copy Trade Execution Strategy

Monitoring infrastructure, timing considerations, position sizing, and exit strategies for copy trading on Solana.

## Monitoring Approaches

### Option 1 — Polling via RPC (Simplest)

Poll `getSignaturesForAddress` at regular intervals to detect new transactions.

- **Latency**: 5-15 seconds depending on poll interval
- **Complexity**: Low — standard HTTP requests
- **Cost**: Free with any RPC endpoint
- **Best for**: Swing trader wallets where seconds do not matter

```python
import httpx
import time

def poll_wallet(rpc_url: str, wallet: str, interval: int = 10) -> None:
    """Poll for new transactions every `interval` seconds."""
    last_sig = None
    while True:
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "getSignaturesForAddress",
            "params": [wallet, {"limit": 5}]
        }
        resp = httpx.post(rpc_url, json=payload)
        sigs = resp.json().get("result", [])
        if sigs and sigs[0]["signature"] != last_sig:
            for sig in sigs:
                if sig["signature"] == last_sig:
                    break
                print(f"New tx: {sig['signature']}")
            last_sig = sigs[0]["signature"]
        time.sleep(interval)
```

### Option 2 — Helius Enhanced WebSocket (Recommended)

Helius provides parsed transaction data via WebSocket with near-real-time delivery.

- **Latency**: 1-3 seconds after on-chain confirmation
- **Complexity**: Medium — WebSocket connection management
- **Cost**: Free tier includes WebSocket access (limited connections)
- **Best for**: Day traders and scalpers

```python
import asyncio
import json
import websockets

async def monitor_helius(api_key: str, wallet: str) -> None:
    """Monitor wallet via Helius enhanced WebSocket."""
    uri = f"wss://atlas-mainnet.helius-rpc.com/?api-key={api_key}"
    async with websockets.connect(uri) as ws:
        subscribe = {
            "jsonrpc": "2.0", "id": 1,
            "method": "transactionSubscribe",
            "params": [{
                "accountInclude": [wallet]
            }, {
                "commitment": "confirmed",
                "encoding": "jsonParsed",
                "transactionDetails": "full"
            }]
        }
        await ws.send(json.dumps(subscribe))
        while True:
            msg = json.loads(await ws.recv())
            if "params" in msg:
                handle_transaction(msg["params"]["result"])
```

### Option 3 — Yellowstone gRPC (Lowest Latency)

Direct gRPC stream from a validator. Sub-second latency.

- **Latency**: < 500ms from block production
- **Complexity**: High — requires gRPC client, protobuf parsing
- **Cost**: Requires a premium RPC provider (Helius, Triton, or self-hosted)
- **Best for**: Sniper wallets where sub-second execution matters

gRPC setup is beyond the scope of this skill. See your RPC provider's documentation for Yellowstone gRPC configuration.

## Timing Strategies

### Immediate Copy

Execute the copy trade as fast as possible after detection.

- **When to use**: Copying scalpers on tokens with rapid price movement
- **Risk**: Higher slippage, potential sandwich attacks, may buy the top
- **Implementation**: WebSocket or gRPC monitoring with pre-built Jupiter swap transactions

### Delayed Copy (Confirmation Wait)

Wait for the transaction to confirm (1-2 slots) before executing.

- **When to use**: Copying swing traders, tokens with stable liquidity
- **Risk**: Price may have moved, but you have confirmation the trade succeeded
- **Implementation**: Polling or WebSocket with a short delay before execution

### Filtered Copy

Detect the trade, run safety checks on the token, then decide whether to copy.

- **When to use**: All copy trading (recommended default)
- **Checks before copying**:
  1. Token liquidity > minimum threshold (e.g., $50K)
  2. Holder concentration not excessive (top 10 holders < 50%)
  3. Token is not on a known scam list
  4. Your aggregate exposure to this token < maximum per-token limit
  5. Daily copy-trade loss limit not exceeded

```python
def should_copy_trade(
    token_address: str,
    trade_size_sol: float,
    portfolio_state: dict,
) -> tuple[bool, str]:
    """Decide whether to copy a detected trade."""
    # Check daily loss limit
    if portfolio_state["daily_copy_loss"] < -portfolio_state["daily_limit"]:
        return False, "Daily copy-trade loss limit reached"
    # Check per-token exposure
    existing = portfolio_state["positions"].get(token_address, 0)
    if existing + trade_size_sol > portfolio_state["max_per_token"]:
        return False, "Per-token exposure limit reached"
    # Check concurrent position count
    if len(portfolio_state["positions"]) >= portfolio_state["max_positions"]:
        return False, "Maximum concurrent positions reached"
    return True, "Trade approved"
```

## Position Sizing

### Fixed Amount

Allocate a constant SOL amount per copy trade regardless of the source wallet's size.

```python
def fixed_size(base_amount: float = 0.5) -> float:
    """Fixed position size per copy trade."""
    return base_amount
```

**Pros**: Simple, predictable risk per trade.
**Cons**: Ignores the source wallet's conviction level.

### Proportional

Match the copied wallet's allocation as a fraction of their estimated portfolio.

```python
def proportional_size(
    their_trade_size: float,
    their_portfolio_estimate: float,
    your_portfolio: float,
) -> float:
    """Scale position proportionally to the source wallet."""
    their_fraction = their_trade_size / max(their_portfolio_estimate, 1.0)
    return their_fraction * your_portfolio
```

**Pros**: Mirrors conviction level.
**Cons**: Requires estimating the source wallet's total portfolio, which is imprecise.

### Confidence-Scaled

Base amount adjusted by your confidence in the wallet.

```python
def confidence_scaled_size(
    base_amount: float,
    copy_score: float,
    max_multiplier: float = 2.0,
) -> float:
    """Scale position by copy-trade suitability score."""
    multiplier = min(copy_score / 100.0, 1.0) * max_multiplier
    return base_amount * multiplier
```

**Pros**: More capital to higher-conviction wallets.
**Cons**: Requires maintaining accurate copy scores.

## Exit Strategies

### Mirror Exit

Exit when the copied wallet exits. Requires continued monitoring of the wallet after entry.

- **Pros**: Leverages the wallet's exit timing intelligence
- **Cons**: Adds monitoring complexity; if monitoring fails, you have no exit signal
- **Implementation**: Same monitoring infrastructure, watching for sell transactions on your held tokens

### Independent Exit

Use your own stop loss and take profit levels, ignoring the copied wallet's exit.

- **Recommended defaults**:
  - Stop loss: -20% from entry
  - Take profit: +50% from entry (or trailing stop at -15% from peak)
- **Pros**: Simple, does not depend on continued monitoring
- **Cons**: May exit too early or too late relative to the wallet

### Hybrid (Recommended)

Mirror the wallet's exit but maintain an independent safety stop loss.

```python
def hybrid_exit_check(
    entry_price: float,
    current_price: float,
    wallet_exited: bool,
    stop_loss_pct: float = -0.20,
) -> tuple[bool, str]:
    """Check if position should be exited."""
    pnl_pct = (current_price - entry_price) / entry_price
    if pnl_pct <= stop_loss_pct:
        return True, f"Stop loss hit: {pnl_pct:.1%}"
    if wallet_exited:
        return True, "Mirroring wallet exit"
    return False, "Hold"
```

## Pre-Execution Checklist

Before executing any copy trade, verify:

1. [ ] Token address is valid and not on a known scam list
2. [ ] Token has sufficient liquidity (> $25K in pool)
3. [ ] Position size does not exceed per-trade or per-token limits
4. [ ] Daily loss limit has not been reached
5. [ ] Maximum concurrent positions not exceeded
6. [ ] Jupiter quote obtained with acceptable slippage (< 5%)
7. [ ] Transaction simulation succeeds (no revert)

## Handling Failed Trades

### The Copied Wallet's Trade Reverts
If the source transaction reverts, do nothing. This is a non-event.

### Your Copy Trade Reverts
Common causes and remedies:
- **Insufficient SOL for fees**: Maintain a fee buffer (0.01 SOL minimum)
- **Slippage exceeded**: Increase slippage tolerance or reduce position size
- **Token is a honeypot**: The source wallet may have bypassed restrictions you cannot
- **Rate limited by RPC**: Switch to a backup RPC endpoint

### Partial Fills
Jupiter may partially fill your swap. Track the actual filled amount, not the requested amount, for P&L calculation.
