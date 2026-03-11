---
name: shredstream
description: Pre-execution Solana transaction streaming via Jito ShredStream, Shyft RabbitStream, and Triton Deshred
---

# ShredStream — Pre-Execution Solana Data

ShredStream gives you transaction data **before the validator executes the block** — typically 100-500ms earlier than standard Yellowstone gRPC. You see transaction *intent*, not confirmed results.

This is the fastest path to Solana data for time-critical trading strategies.

## How It Works

Solana validators produce blocks by serializing transactions into **shreds** (~1,228 bytes each, sized for UDP MTU). Shreds propagate through Turbine (Solana's fanout protocol, 2-3 hops). ShredStream bypasses Turbine by receiving shreds **directly from leader validators** via Jito's Block Engine.

```
Leader Validator
     │
     ├── Turbine (standard, 2-3 hops, 200-500ms)
     │       └── Your RPC Node → Yellowstone gRPC (post-execution)
     │
     └── Jito Block Engine (direct)
              └── ShredStream Proxy (your server)
                   ├── UDP shreds → Your RPC/Validator (faster block building)
                   └── gRPC entries → Your Trading Bot (decoded transactions)
```

### What You Get vs. What You Don't

| Available (Pre-Execution) | NOT Available (Needs Execution) |
|---------------------------|--------------------------------|
| Transaction signatures | Success/failure status |
| Account keys (pubkeys) | Balance changes (pre/post) |
| Instructions (program, accounts, data) | Log messages |
| Address lookup table references | Inner instructions (CPI) |
| Slot number | Token balance changes |
| | Compute units consumed |

**Key tradeoff**: Speed for completeness. You see what's *about to happen* but can't confirm it actually succeeded. Some transactions you see will ultimately fail.

## Three Ways to Get Pre-Execution Data

| Provider | Product | Latency | Access | Cost |
|----------|---------|---------|--------|------|
| **Jito** | ShredStream Proxy | ~10-50ms from leader | Apply + auth keypair | Free (beta) |
| **Shyft** | RabbitStream | ~15-100ms faster than gRPC | Shyft gRPC plan | From $199/mo |
| **Triton** | Deshred (`SubscribeDeshred`) | ~6.3ms p50 from shred | Triton customer | ~$2,900+/mo |

See `references/providers_compared.md` for detailed comparison.

## Option 1: Jito ShredStream Proxy

The most direct approach — run Jito's open-source proxy on your own server.

### Get Access

1. Generate a Solana keypair: `solana-keygen new -o shred_auth.json`
2. Apply at [Jito's form](https://web.miniextensions.com/WV3gZjFwqNqITsMufIEp) with your public key
3. Wait for approval (your keypair gets whitelisted)
4. No staking requirement, free during beta

### Run the Proxy

```bash
# Clone and build
git clone https://github.com/jito-labs/shredstream-proxy.git --recurse-submodules
cd shredstream-proxy

# Run with gRPC enabled (key flag: --grpc-service-port)
RUST_LOG=info cargo run --release --bin jito-shredstream-proxy -- shredstream \
    --block-engine-url https://mainnet.block-engine.jito.wtf \
    --auth-keypair /path/to/shred_auth.json \
    --desired-regions ny,amsterdam \
    --dest-ip-ports 127.0.0.1:8001 \
    --grpc-service-port 7777
```

Docker (host networking required for UDP):

```bash
docker run -d --name shredstream-proxy --rm \
  --network host \
  -e RUST_LOG=info \
  -e BLOCK_ENGINE_URL=https://mainnet.block-engine.jito.wtf \
  -e AUTH_KEYPAIR=/app/shred_auth.json \
  -e DESIRED_REGIONS=ny,amsterdam \
  -e DEST_IP_PORTS=127.0.0.1:8001 \
  -e GRPC_SERVICE_PORT=7777 \
  -v /path/to/shred_auth.json:/app/shred_auth.json \
  jitolabs/jito-shredstream-proxy shredstream
```

### Configuration

| Parameter | Description | Example |
|-----------|-------------|---------|
| `BLOCK_ENGINE_URL` | Jito block engine endpoint | `https://mainnet.block-engine.jito.wtf` |
| `AUTH_KEYPAIR` | Path to whitelisted Solana keypair | `shred_auth.json` |
| `DESIRED_REGIONS` | Max 2, comma-separated | `ny,amsterdam` |
| `DEST_IP_PORTS` | Where to forward raw shreds (UDP) | `127.0.0.1:8001` |
| `GRPC_SERVICE_PORT` | Enable gRPC entry streaming | `7777` |
| `SRC_BIND_PORT` | Incoming shred UDP port | `20000` |

Available regions: `amsterdam`, `dublin`, `frankfurt`, `london`, `ny`, `salt-lake-city`, `singapore`, `tokyo`

### Verify It's Working

```bash
# Check shreds are arriving via UDP
sudo tcpdump 'udp and dst port 20000'
# Should see many ~1200-byte packets continuously
```

### Consume via gRPC

```rust
use jito_protos::shredstream::{
    shredstream_proxy_client::ShredstreamProxyClient,
    SubscribeEntriesRequest,
};

let mut client = ShredstreamProxyClient::connect("http://127.0.0.1:7777").await?;
let mut stream = client
    .subscribe_entries(SubscribeEntriesRequest {})
    .await?
    .into_inner();

while let Some(entry) = stream.message().await? {
    let entries: Vec<solana_entry::entry::Entry> =
        bincode::deserialize(&entry.entries)?;

    for e in &entries {
        for tx in &e.transactions {
            let sig = tx.signatures[0];
            let msg = tx.message();
            // Parse instructions, accounts, etc.
        }
    }

    println!("Slot {}: {} entries, {} transactions",
        entry.slot,
        entries.len(),
        entries.iter().map(|e| e.transactions.len()).sum::<usize>()
    );
}
```

## Option 2: Shyft RabbitStream

**Drop-in replacement** for Yellowstone gRPC — same `SubscribeRequest` format, just a different endpoint. Easiest way to get pre-execution data without running infrastructure.

```bash
export GRPC_ENDPOINT="https://rabbitstream.ny.shyft.to"
export GRPC_TOKEN="your-shyft-x-token"
```

```python
# Same code as yellowstone-grpc, just different endpoint
import grpc

endpoint = "rabbitstream.ny.shyft.to"
token = os.environ["GRPC_TOKEN"]

# ... standard Yellowstone connection code ...
# Subscribe to transactions — same filter format
request = SubscribeRequest(
    transactions={
        "pumpfun": SubscribeRequestFilterTransactions(
            account_include=["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"],
            vote=False,
            failed=False,
        )
    },
    commitment=CommitmentLevel.PROCESSED,
)
```

**Limitations**: Only transaction filters work. No account, slot, or block subscriptions. The `meta` field is empty (no execution results).

Regional endpoints: `rabbitstream.{ny,va,ams,fra}.shyft.to`

## Option 3: Triton Deshred

Lowest latency (~6.3ms p50) via Triton's `SubscribeDeshred` RPC. Same Yellowstone client, different method.

```rust
// Requires yellowstone-grpc-client with Deshred support
let (mut tx, mut stream) = client.subscribe_deshred().await?;

tx.send(SubscribeDeshredRequest {
    deshred_transactions: hashmap!{
        "pumpfun".to_string() => SubscribeRequestFilterDeshredTransactions {
            vote: Some(false),
            account_include: vec!["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P".into()],
            ..Default::default()
        }
    },
    ..Default::default()
}).await?;
```

**Access**: Triton customers only, paid beta, requires their custom Agave validator fork.

## Parsing Pre-Execution Transactions

Without execution metadata, parsing is simpler but requires program-specific knowledge.

### Identify the Program

```python
# From a raw VersionedTransaction (post-deserialization)
account_keys = [str(k) for k in tx.message.account_keys]
for ix in tx.message.instructions:
    program_id = account_keys[ix.program_id_index]
    if program_id == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":
        # This is a PumpFun instruction
        discriminator = ix.data[:8]
        # Decode instruction data per PumpFun IDL
```

### Instruction Discriminators

Most Solana programs use 8-byte discriminators (Anchor SHA256 hash of the instruction name). Match `instruction.data[:8]` against known values for each program.

```python
# Common approach
PUMPFUN_CREATE = bytes.fromhex("181ec828051c0777")
PUMPFUN_BUY = bytes.fromhex("66063d1201daebea")
PUMPFUN_SELL = bytes.fromhex("33e685a4017f83ad")

disc = ix.data[:8]
if disc == PUMPFUN_BUY:
    # Parse buy parameters from remaining bytes
    ...
```

**Warning**: Discriminator values are program-specific and can change between program versions. Always verify against the current program IDL. See the `pumpfun-mechanics` skill for PumpFun-specific parsing.

## Common Architecture: ShredStream + Yellowstone

Most production systems use both:

```
ShredStream (pre-execution)          Yellowstone gRPC (post-execution)
         │                                      │
         ▼                                      ▼
  Intent Detection                    Confirmation + Reconciliation
  "Wallet X is buying token Y"       "Buy succeeded, wallet now holds Z"
         │                                      │
         ▼                                      ▼
  Pre-compute Response                Execute / Update State
  (route, sign, prepare bundle)       (record PnL, update positions)
```

This gives you the speed advantage of ShredStream for signal detection while using Yellowstone for reliable state management.

## Deployment Requirements

- **Public IP required** — NAT breaks UDP shred delivery
- **Host networking** — Docker bridge mode drops shred packets
- **UDP port 20000** open for incoming shreds
- **Co-locate near validators** — Frankfurt, NY, Amsterdam, London, Tokyo recommended
- **Bare metal preferred** — Cloud VMs add 1-5ms jitter from shared NICs

See `references/deployment.md` for full infrastructure guide.

## Files

### References
- `references/providers_compared.md` — Jito ShredStream vs Shyft RabbitStream vs Triton Deshred
- `references/deployment.md` — Infrastructure requirements, region selection, firewall configuration
- `references/proto_reference.md` — ShredStream protobuf definitions and Entry parsing

### Scripts
- `scripts/parse_shredstream_entries.py` — Decode and analyze ShredStream gRPC entries
- `scripts/rabbitstream_monitor.py` — Connect to Shyft RabbitStream for pre-execution transaction monitoring
