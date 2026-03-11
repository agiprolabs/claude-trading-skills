---
name: yellowstone-grpc
description: Real-time Solana transaction and account streaming via Yellowstone gRPC (Geyser plugin)
---

# Yellowstone gRPC — Real-Time Solana Streaming

Stream every transaction, account update, slot, and block on Solana in real-time using Yellowstone gRPC. This is the foundation for any latency-sensitive Solana trading system — replacing REST polling with push-based streaming at ~5ms slot latency.

## Why Yellowstone gRPC

| Method | Slot Latency (p90) | Use Case |
|--------|-------------------|----------|
| REST polling (`getTransaction`) | ~150ms+ | Historical lookups |
| WebSocket (`onLogs`) | ~10ms | Simple notifications |
| **Yellowstone gRPC** | **~5ms** | **Production trading systems** |

Yellowstone is a Geyser plugin that exposes Solana validator data over gRPC. Every major RPC provider runs it. You subscribe to filtered streams of transactions, account changes, slots, blocks, and entries — and the data pushes to you.

## Quick Start

### 1. Get Access

You need a gRPC-enabled RPC provider. See `references/providers.md` for full comparison.

| Provider | gRPC Entry Price | Notes |
|----------|-----------------|-------|
| Shyft | $199/mo | Best value, 7 regions, unlimited bandwidth |
| Helius | $999/mo | LaserStream, DAS APIs included |
| Triton One | ~$2,900/mo | Created Yellowstone, lowest latency |
| QuickNode | Plan-dependent | Marketplace add-on |
| Chainstack | $49/mo (1 stream) | Budget option, limited filters |
| Alchemy | Free tier available | Compute-unit metered |

### 2. Install Dependencies

```bash
# Python
uv pip install grpcio grpcio-tools protobuf base58 solders python-dotenv

# Generate Python stubs from proto files
git clone https://github.com/rpcpool/yellowstone-grpc.git
python -m grpc_tools.protoc \
  -I./yellowstone-grpc/yellowstone-grpc-proto/proto/ \
  --python_out=./generated \
  --pyi_out=./generated \
  --grpc_python_out=./generated \
  ./yellowstone-grpc/yellowstone-grpc-proto/proto/*.proto
```

```toml
# Rust — Cargo.toml
[dependencies]
yellowstone-grpc-client = "6.0.0"
yellowstone-grpc-proto = "6.0.0"
tokio = { version = "1", features = ["rt-multi-thread", "macros"] }
futures = "0.3"
bs58 = "0.5"
```

```bash
# TypeScript
npm install @triton-one/yellowstone-grpc @solana/web3.js
```

### 3. Environment Setup

```bash
export GRPC_ENDPOINT="https://grpc.ny.shyft.to"  # your provider endpoint
export GRPC_TOKEN="your-x-token-here"              # from provider dashboard
```

### 4. Connect and Subscribe

```python
import grpc
import os
from generated import geyser_pb2, geyser_pb2_grpc

endpoint = os.environ["GRPC_ENDPOINT"].replace("https://", "")
token = os.environ["GRPC_TOKEN"]

# Authenticated TLS channel
auth_creds = grpc.metadata_call_credentials(
    lambda ctx, cb: cb((("x-token", token),), None)
)
channel = grpc.secure_channel(
    endpoint,
    grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(), auth_creds
    ),
    options=[("grpc.max_receive_message_length", 64 * 1024 * 1024)],
)
stub = geyser_pb2_grpc.GeyserStub(channel)
```

## Core Concepts

### Subscription Types

| Type | What You Get | Use Case |
|------|-------------|----------|
| `transactions` | Full transaction with metadata | DEX swap monitoring, copy trading |
| `accounts` | Account data on change | Pool reserve tracking, token supply |
| `slots` | Slot progression events | Block timing, confirmation tracking |
| `blocks` | Full block contents | Block-level analysis |
| `blocks_meta` | Block metadata only | Lightweight block tracking |
| `entry` | Block entries (shred groups) | Low-level validator data |
| `transactions_status` | Tx status without full data | Lightweight confirmation |

### Filter Logic

- Multiple filter **types** (transactions + accounts) = **AND** — you get updates matching any type
- Values within arrays (multiple addresses in `account_include`) = **OR**
- Named filters let you distinguish which filter matched in the response
- Sending a new `SubscribeRequest` **replaces** all previous filters

### Commitment Levels

| Level | Speed | Safety | Use For |
|-------|-------|--------|---------|
| `PROCESSED` | Fastest | May be rolled back | Time-critical signals |
| `CONFIRMED` | ~400ms slower | Supermajority voted | Most trading use cases |
| `FINALIZED` | ~6-12s slower | Irreversible | Settlement verification |

## Common Subscription Patterns

### Watch All Swaps on a DEX Program

```python
# Filter: all non-vote, non-failed transactions involving PumpFun
request = geyser_pb2.SubscribeRequest(
    transactions={
        "pumpfun": geyser_pb2.SubscribeRequestFilterTransactions(
            account_include=["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"],
            vote=False,
            failed=False,
        )
    },
    commitment=geyser_pb2.CommitmentLevel.PROCESSED,
)
```

### Track Specific Wallets

```python
request = geyser_pb2.SubscribeRequest(
    transactions={
        "whales": geyser_pb2.SubscribeRequestFilterTransactions(
            account_include=[
                "WalletAddress1...",
                "WalletAddress2...",
            ],
            vote=False,
            failed=False,
        )
    },
    commitment=geyser_pb2.CommitmentLevel.CONFIRMED,
)
```

### Monitor Pool Reserves (Account Subscription)

```python
request = geyser_pb2.SubscribeRequest(
    accounts={
        "raydium_pools": geyser_pb2.SubscribeRequestFilterAccounts(
            account=["PoolAddress1...", "PoolAddress2..."],
        )
    },
    commitment=geyser_pb2.CommitmentLevel.PROCESSED,
)
```

### Reduce Bandwidth with Data Slicing

```python
# Only get the first 40 bytes of account data (e.g., just the discriminator + key fields)
request = geyser_pb2.SubscribeRequest(
    accounts={
        "token_accounts": geyser_pb2.SubscribeRequestFilterAccounts(
            owner=["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"],
            filters=[
                geyser_pb2.SubscribeRequestFilterAccountsFilter(
                    token_account_state=True
                )
            ],
        )
    },
    accounts_data_slice=[
        geyser_pb2.SubscribeRequestAccountsDataSlice(offset=0, length=40)
    ],
)
```

## Parsing Transaction Updates

When you receive a `SubscribeUpdateTransaction`, extract:

```python
for update in stream:
    if update.HasField("transaction"):
        tx = update.transaction
        info = tx.transaction
        sig = base58.b58encode(info.signature).decode()
        slot = tx.slot

        msg = info.transaction.message
        account_keys = [base58.b58encode(k).decode() for k in msg.account_keys]

        # Instructions
        for ix in msg.instructions:
            program = account_keys[ix.program_id_index]
            accounts = [account_keys[i] for i in ix.accounts]
            data = ix.data  # bytes — decode per program IDL

        # Token balance changes (post-execution)
        meta = info.meta
        for tb in meta.post_token_balances:
            mint = tb.mint
            owner = tb.owner
            amount = tb.ui_token_amount.ui_amount
```

See `references/proto_reference.md` for complete field documentation.

## Production Architecture

```
[gRPC Stream] → [Bounded Channel] → [Processing Workers]
                   (1K-100K cap)      ├─ Parse instructions
                                      ├─ Update state / DB
                                      └─ Trigger actions
```

**Critical patterns:**
- Decouple I/O from processing — never block the gRPC stream
- Reconnect with exponential backoff (100ms → 60s cap)
- Use `from_slot` to resume after disconnection (subtract ~32 slots for reorg safety)
- Ping every 15-30 seconds to keep connection alive
- Filter `vote: false` always — vote transactions are ~70% of all traffic
- Set `max_receive_message_length` to 64MB+ (default 4MB is too small)

See `references/performance.md` for full production checklist.

## Key Program IDs for Trading

| Program | Address | What It Does |
|---------|---------|-------------|
| PumpFun | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | Token launches, bonding curve trades |
| PumpSwap | `PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP` | PumpFun graduated token swaps |
| Raydium AMM | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` | Legacy AMM swaps |
| Raydium CLMM | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | Concentrated liquidity |
| Raydium CPMM | `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C` | Constant product MM |
| Orca Whirlpool | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | Concentrated liquidity |
| Meteora DLMM | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | Dynamic liquidity MM |
| Jupiter V6 | `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` | Swap aggregator |
| Token Program | `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` | SPL token operations |

## Files

### References
- `references/providers.md` — Provider comparison: endpoints, pricing, auth, features
- `references/subscription_filters.md` — Complete filter reference with examples for every filter type
- `references/proto_reference.md` — Key protobuf message definitions and field documentation
- `references/performance.md` — Connection management, reconnection, backpressure, production checklist

### Scripts
- `scripts/subscribe_transactions.py` — Stream and parse transactions filtered by program ID
- `scripts/monitor_wallets.py` — Watch specific wallets for on-chain activity
