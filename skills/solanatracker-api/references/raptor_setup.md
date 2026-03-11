# Raptor DEX Aggregator — Setup & Deployment

Raptor is a self-hosted Rust binary by SolanaTracker that aggregates swap quotes across 25+ Solana DEXes. Free during public beta.

## Quick Start

```bash
# Clone the binary repo
git clone https://github.com/solanatracker/raptor-binary
cd raptor-binary

# Run with minimum required config
RPC_URL="https://your-solana-rpc.com" \
YELLOWSTONE_ENDPOINT="https://your-yellowstone-grpc.com" \
./raptor

# Default: listens on 0.0.0.0:8080
```

**Requirements**: Solana RPC endpoint + Yellowstone gRPC endpoint (for pool indexing and Jet TPU transaction submission) + signature file in the working directory.

## Signature File

Raptor requires a `signature` file in the same directory where the binary runs. This file authenticates your instance with the SolanaTracker backend.

```bash
# The signature file must be present alongside the raptor binary
ls raptor-binary/
# raptor          ← the binary
# signature       ← required auth file (provided by SolanaTracker)

# If you move the binary, copy the signature file too
cp raptor /opt/raptor/
cp signature /opt/raptor/
cd /opt/raptor && ./raptor
```

Without the signature file, Raptor will fail to start or fail to submit transactions. The file is included in the `raptor-binary` repo clone.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RPC_URL` | Yes | — | Solana RPC endpoint |
| `YELLOWSTONE_ENDPOINT` | Yes | — | Yellowstone gRPC endpoint |
| `BIND_ADDR` | No | `0.0.0.0:8080` | Listen address |
| `INCLUDE_DEXES` | No | All | Comma-separated DEX filter |
| `SKIP_POOL_INDEXER_WAIT` | No | false | Skip initial pool index sync |

## Execution Flow

```
1. GET /quote → Best route across DEXes
2. POST /swap → Unsigned transaction
3. Sign transaction locally (your key, never sent to Raptor)
4. POST /send-transaction → Submit via Yellowstone Jet TPU
5. GET /transaction/{sig} → Confirm status
```

### Step 1: Get Quote

```python
import httpx

RAPTOR = "http://localhost:8080"

resp = httpx.get(f"{RAPTOR}/quote", params={
    "inputMint": "So11111111111111111111111111111111111111112",  # SOL
    "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "amount": 1_000_000_000,  # 1 SOL in lamports
    "slippageBps": 50,
})
quote = resp.json()
print(f"Output: {quote['amountOut']} lamports")
print(f"Price impact: {quote['priceImpact']}%")
print(f"Route: {len(quote['routePlan'])} hops")
```

### Step 2: Build Swap Transaction

```python
resp = httpx.post(f"{RAPTOR}/swap", json={
    "userPublicKey": "YOUR_WALLET_PUBKEY",
    "quoteResponse": quote,
    "wrapUnwrapSol": True,
    "txVersion": "v0",
    "priorityFee": "auto",
    "maxPriorityFee": 100_000,  # max priority fee in lamports
})
swap = resp.json()
# swap["swapTransaction"] is base64-encoded unsigned transaction
```

### Step 3: Sign Locally

```python
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair
import base64

tx_bytes = base64.b64decode(swap["swapTransaction"])
tx = VersionedTransaction.from_bytes(tx_bytes)
keypair = Keypair.from_base58_string(os.getenv("PRIVATE_KEY"))
signed_tx = tx.sign([keypair])
signed_b64 = base64.b64encode(bytes(signed_tx)).decode()
```

### Step 4: Submit Transaction

```python
resp = httpx.post(f"{RAPTOR}/send-transaction", json={
    "transaction": signed_b64,
})
result = resp.json()
print(f"Signature: {result['signature']}")
# Raptor retries for up to 30 seconds or until confirmed
```

### Step 5: Check Status

```python
resp = httpx.get(f"{RAPTOR}/transaction/{result['signature']}")
status = resp.json()
# status: pending | confirmed | failed | expired
```

## DEX Filter Configuration

Limit which DEXes Raptor queries. Useful for targeting specific pool types:

```bash
# Only bonding curve DEXes
INCLUDE_DEXES="pumpfun,moonit,heaven,raydium-launchlab,meteora-curve" ./raptor

# Only major AMMs
INCLUDE_DEXES="raydium,orca,meteora" ./raptor
```

**All supported DEXes**: `raydium` (AMM/CLMM/CPMM), `meteora` (DLMM/Dynamic), `orca` (Whirlpool v1/v2), `pancakeswap`, `pumpfun`, `pumpswap`, `heaven`, `moonit`, `boopfun`, `humidifi`, `tessera`, `solfi`, `alphaq`, `zerofi`, `bisonfi`, `goonfi`, `fluxbeam`, and more.

## Deployment Options

### Bare Metal / VPS

```bash
# Ensure signature file is in the same directory as the binary
ls ./raptor ./signature  # both must exist
chmod +x raptor
RPC_URL="..." YELLOWSTONE_ENDPOINT="..." ./raptor
```

### Docker

```dockerfile
FROM ubuntu:22.04
COPY raptor /usr/local/bin/raptor
COPY signature /usr/local/bin/signature
RUN chmod +x /usr/local/bin/raptor
WORKDIR /usr/local/bin
CMD ["raptor"]
```

```bash
docker run -e RPC_URL="..." -e YELLOWSTONE_ENDPOINT="..." -p 8080:8080 raptor
```

### Fly.io

```toml
# fly.toml
app = "my-raptor"
primary_region = "ewr"  # East US for low latency

[build]
  dockerfile = "Dockerfile"

[env]
  RPC_URL = "https://your-rpc.com"
  YELLOWSTONE_ENDPOINT = "https://your-yellowstone.com"
  INCLUDE_DEXES = "raydium,orca,meteora,pumpfun"

[[services]]
  internal_port = 8080
  protocol = "tcp"
  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]

[[vm]]
  size = "shared-cpu-2x"
  memory = "4gb"
```

```bash
fly deploy
```

## Key Differences from Jupiter

1. **Self-hosted**: Runs on your infrastructure, no external API dependency
2. **No rate limits**: Limited only by your hardware
3. **Separate on-chain program**: Uses `RaptorD5o...` program, not Jupiter's
4. **Jet TPU submission**: Transactions submitted via Yellowstone, not standard RPC
5. **Private key stays local**: Signing happens on your machine, never sent to Raptor
6. **DEX filtering**: Choose exactly which DEXes to include

## Troubleshooting

- **Slow startup**: Initial pool indexing can take 1-2 minutes. Use `SKIP_POOL_INDEXER_WAIT=true` to serve requests during indexing (quotes may be incomplete).
- **Quote returns 0 output**: Token may not have liquidity on any included DEX. Check `INCLUDE_DEXES` filter.
- **Transaction fails**: Check slippage, priority fee, and block height. Raptor retries automatically for 30 seconds.
- **Health check fails**: Verify RPC and Yellowstone endpoints are reachable.
