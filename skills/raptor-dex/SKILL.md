---
name: raptor-dex
description: Self-hosted Solana DEX aggregator by SolanaTracker — multi-hop routing across 25+ DEXes, WebSocket streaming, Yellowstone Jet TPU submission, no rate limits
---

# Raptor — Self-Hosted Solana DEX Aggregator

Raptor is a self-hosted Rust binary that aggregates swap quotes across 25+ Solana DEXes. Unlike Jupiter, Raptor runs on your own infrastructure with **no rate limits**, **no API key**, and **no dependency on external API availability**. Free during public beta.

- **Program ID (Mainnet)**: `RaptorD5ojtsqDDtJeRsunPLg6GvLYNnwKJWxYE4m87`
- **GitHub**: [solanatracker/raptor-binary](https://github.com/solanatracker/raptor-binary)
- **Docs**: [docs.solanatracker.io/raptor/overview](https://docs.solanatracker.io/raptor/overview)

## Quick Start

```bash
# Clone the binary repo (includes required signature file)
git clone https://github.com/solanatracker/raptor-binary
cd raptor-binary

# Run with required environment variables
export RPC_URL="https://your-solana-rpc.com"
export YELLOWSTONE_ENDPOINT="https://your-yellowstone-grpc.com"
export YELLOWSTONE_TOKEN="your-token"  # if required by provider
./raptor
# Listens on 0.0.0.0:8080 by default
```

**Requirements**: Solana RPC endpoint + Yellowstone gRPC endpoint (for pool indexing). Raptor uses very few RPC calls during normal operation since pool state is streamed via Yellowstone.

**Signature file**: The `signature` file must be in the same directory as the Raptor binary. It authenticates your instance and is included in the repo clone. If you move the binary, copy the signature file with it.

## Execution Flow

```
1. GET  /quote              → Best route across 25+ DEXes
2. POST /swap               → Unsigned versioned transaction
3. Sign locally              → Your private key never leaves your machine
4. POST /send-transaction   → Submit via Yellowstone Jet TPU
5. GET  /transaction/{sig}  → Confirm status (pending/confirmed/failed/expired)
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/quote` | Get swap quote with multi-hop routing |
| `POST` | `/swap` | Build swap transaction from quote |
| `POST` | `/swap-instructions` | Get swap instructions only (no tx wrapper) |
| `POST` | `/quote-and-swap` | Quote + transaction in one request |
| `POST` | `/send-transaction` | Submit via Yellowstone Jet TPU with auto-retry |
| `GET` | `/transaction/:signature` | Track transaction status and parsed events |
| `GET` | `/health` | Health check (pools, cache, Yellowstone connection) |

## Get a Quote

```python
import httpx

RAPTOR = "http://localhost:8080"

resp = httpx.get(f"{RAPTOR}/quote", params={
    "inputMint": "So11111111111111111111111111111111111111112",   # SOL
    "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "amount": 1_000_000_000,  # 1 SOL in lamports
    "slippageBps": 50,
})
quote = resp.json()
print(f"Output: {quote['amountOut']} lamports")
print(f"Price impact: {quote['priceImpact']}%")
print(f"Route: {len(quote['routePlan'])} hops")
```

### Quote Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `inputMint` | string | Yes | Input token mint address |
| `outputMint` | string | Yes | Output token mint address |
| `amount` | integer | Yes | Amount in smallest unit (lamports) |
| `slippageBps` | string | No | Basis points or `"dynamic"` (default: 50) |
| `dexes` | string | No | Comma-separated DEX filter |
| `excludeDexes` | string | No | DEXes to exclude |
| `maxHops` | integer | No | 1-4 hops (default: 4) |
| `directRouteOnly` | boolean | No | Only single-hop routes |
| `pools` | string | No | Comma-separated pool address filter |
| `feeBps` | integer | No | Platform fee 0-1000 bps |
| `feeAccount` | string | No | Fee recipient wallet |

## Build and Sign a Swap

```python
import base64
import os

# Step 2: Build transaction from quote
resp = httpx.post(f"{RAPTOR}/swap", json={
    "quoteResponse": quote,
    "userPublicKey": "YOUR_WALLET_PUBKEY",
    "wrapUnwrapSol": True,
    "txVersion": "v0",
    "priorityFee": "auto",       # min|low|auto|medium|high|veryHigh|turbo|unsafeMax
    "maxPriorityFee": 100_000,    # cap in lamports
})
swap = resp.json()
# swap["swapTransaction"] is base64-encoded unsigned transaction

# Step 3: Sign locally (private key never sent to Raptor)
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair

tx_bytes = base64.b64decode(swap["swapTransaction"])
tx = VersionedTransaction.from_bytes(tx_bytes)
keypair = Keypair.from_base58_string(os.getenv("PRIVATE_KEY"))
signed_tx = VersionedTransaction(tx.message, [keypair])
signed_b64 = base64.b64encode(bytes(signed_tx)).decode()

# Step 4: Submit via Yellowstone Jet TPU
resp = httpx.post(f"{RAPTOR}/send-transaction", json={
    "transaction": signed_b64,
})
result = resp.json()
print(f"Signature: {result['signature']}")

# Step 5: Track status
resp = httpx.get(f"{RAPTOR}/transaction/{result['signature']}")
status = resp.json()
# status: pending | confirmed | failed | expired
print(f"Status: {status['status']}, Latency: {status.get('latency_ms')}ms")
```

## WebSocket Streaming

Real-time quote streaming with slot-based updates when pool state changes:

```python
import asyncio, websockets, json

async def stream_quotes():
    async with websockets.connect("ws://localhost:8080/stream") as ws:
        await ws.send(json.dumps({
            "type": "subscribe",
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "amount": 1_000_000_000,
            "slippageBps": "50",
        }))
        async for msg in ws:
            data = json.loads(msg)
            if data.get("type") == "quote":
                print(f"Out: {data['data']['amountOut']} (slot {data['data']['contextSlot']})")
```

`/stream/swap` variant pre-builds transactions ready for signing, with automatic resend every 10 slots to prevent expiry.

## Supported DEXes (25+)

**Raydium**: AMM, CLMM, CPMM, LaunchLab | **Meteora**: DLMM, Dynamic AMM, DAMM V2, Curve, DBC | **Orca**: Whirlpool v1/v2 | **Bonding Curves**: Pump.fun, Pumpswap, Heaven, MoonIt, Boopfun | **PropAMM**: Humidifi, Tessera, Solfi V1/V2, AlphaQ, ZeroFi, BisonFi, GoonFi V2 | **Other**: FluxBeam, PancakeSwap V3

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RPC_URL` | Yes | — | Solana RPC endpoint |
| `YELLOWSTONE_ENDPOINT` | Yes | — | Yellowstone gRPC endpoint |
| `YELLOWSTONE_TOKEN` | No | — | Auth token (if provider requires) |
| `BIND_ADDR` | No | `0.0.0.0:8080` | Listen address |
| `INCLUDE_DEXES` | No | all | Comma-separated DEX filter |
| `EXCLUDE_DEXES` | No | none | DEXes to exclude |
| `WORKER_THREADS` | No | CPU cores | Worker thread count |
| `ENABLE_WEBSOCKET` | No | false | Enable `/stream` endpoints |
| `ENABLE_YELLOWSTONE_JET` | No | false | Enable Jet TPU for `/send-transaction` |
| `ENABLE_ARBITRAGE` | No | false | Enable circular arbitrage routes |

### CLI Flags

```bash
./raptor --include-dexes raydium,orca,meteora \
         --enable-websocket \
         --enable-yellowstone-jet \
         --workers 4
```

### DEX Filtering Examples

```bash
# Only bonding curve DEXes (for PumpFun sniping)
INCLUDE_DEXES="pumpfun,pumpswap,heaven,moonit,boopfun" ./raptor

# Only major AMMs
INCLUDE_DEXES="raydium,orca,meteora" ./raptor
```

## Priority Fee Levels

| Level | Use Case |
|-------|----------|
| `min` / `low` | Cost-saving, non-urgent |
| `auto` / `medium` | Recommended default |
| `high` / `veryHigh` | Faster confirmation |
| `turbo` / `unsafeMax` | Maximum speed, competitive scenarios |

## Raptor vs Jupiter

| Feature | Raptor | Jupiter |
|---------|--------|---------|
| Self-hosted | Yes | No |
| Rate limits | None (your hardware) | API rate limits |
| DEX coverage | 25+ | 30+ |
| Latency | Network-local | Remote API |
| Cost | Free (beta) | Free (hosted) |
| Tx submission | Yellowstone Jet TPU | Standard RPC |
| On-chain program | `RaptorD5o...` | `JUP...` |
| API key required | No | No |

## Deployment

See `references/deployment.md` for Docker, Fly.io, and bare metal setup.

## Files

### References
- `references/api_reference.md` — Complete HTTP and WebSocket API with request/response schemas
- `references/deployment.md` — Docker, Fly.io, bare metal deployment with signature file handling
- [docs.solanatracker.io/raptor/overview](https://docs.solanatracker.io/raptor/overview) — Official Raptor documentation
- [github.com/solanatracker/raptor-binary](https://github.com/solanatracker/raptor-binary) — Binary releases and README

### Scripts
- `scripts/raptor_quote.py` — Get and compare swap quotes with --demo mode
- `scripts/raptor_swap.py` — Full swap flow: quote → build → sign → submit → confirm (simulation only in --demo)
