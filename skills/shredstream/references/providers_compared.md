# Pre-Execution Streaming — Provider Comparison

## Overview

Three products offer pre-execution Solana data (transactions before block confirmation):

| | Jito ShredStream | Shyft RabbitStream | Triton Deshred |
|---|---|---|---|
| **How it works** | Raw shreds from Block Engine via UDP proxy | Shred-level extraction, Yellowstone-compatible format | Blockstore tap before Replay stage |
| **Latency** | 10-50ms from leader | 15-100ms faster than standard gRPC | ~6.3ms p50, ~20ms p90 |
| **Self-hosted?** | Yes (run proxy yourself) | No (managed service) | No (Triton infrastructure) |
| **API format** | Custom gRPC (`SubscribeEntries`) | Yellowstone gRPC (`Subscribe`) | Yellowstone gRPC (`SubscribeDeshred`) |
| **Filtering** | None (all entries) | Transaction filters only | Transaction filters (vote, accounts) |
| **Cost** | Free (beta) + server costs | From $199/mo (Shyft plan) | ~$2,900+/mo (Triton dedicated) |
| **ALT resolution** | No (raw transactions) | Yes | Yes |

## Jito ShredStream (Direct)

**Best for**: Teams running their own infrastructure who want maximum control and lowest cost.

### Pros
- Free during beta (no Jito fees)
- Open-source proxy ([jito-labs/shredstream-proxy](https://github.com/jito-labs/shredstream-proxy))
- Direct from Block Engine — no intermediary
- Can also feed shreds to your own RPC node for faster block building
- gRPC mode eliminates need for a full Solana node

### Cons
- Requires public IP with UDP access (no NAT)
- Must run and maintain the proxy yourself
- No server-side filtering — you get everything, must filter client-side
- Approval process required (keypair whitelisting)
- Entry deserialization is bincode, not protobuf (slightly more work)
- Limited to 2 regions per proxy instance

### Access
1. Generate keypair: `solana-keygen new -o shred_auth.json`
2. Submit public key at: https://web.miniextensions.com/WV3gZjFwqNqITsMufIEp
3. Wait for approval
4. Run proxy with `--grpc-service-port` to enable gRPC streaming

### Regions
amsterdam, dublin, frankfurt, london, ny, salt-lake-city, singapore, tokyo

## Shyft RabbitStream

**Best for**: Teams already using Shyft who want pre-execution data with minimal code changes.

### Pros
- **Drop-in replacement** for Yellowstone gRPC — same `SubscribeRequest` format
- No infrastructure to run — managed service
- Same x-token auth as regular Shyft gRPC
- Server-side transaction filtering (account_include, account_exclude, etc.)
- ALT resolution included
- Multiple regions available

### Cons
- Only transaction filters work (no account/slot/block subscriptions)
- No `meta` field (no execution results, as expected for pre-execution)
- Requires Shyft Build plan or higher ($199+/mo)
- Slightly higher latency than direct ShredStream (goes through Shyft infrastructure)

### Endpoints
- `rabbitstream.ny.shyft.to` (New York)
- `rabbitstream.va.shyft.to` (Virginia)
- `rabbitstream.ams.shyft.to` (Amsterdam)
- `rabbitstream.fra.shyft.to` (Frankfurt)

### Connection
Same as Yellowstone gRPC — just change the endpoint URL:
```python
endpoint = "rabbitstream.ny.shyft.to"  # instead of grpc.ny.shyft.to
# Everything else identical
```

## Triton Deshred

**Best for**: HFT teams who need absolute lowest latency and can afford Triton pricing.

### Pros
- Lowest measured latency: ~6.3ms p50, ~20ms p90
- Integrated into Yellowstone client (same library, different RPC method)
- Server-side filtering: vote, account_include, account_exclude, account_required
- ALT resolution included
- Historical data via Old Faithful

### Cons
- Paid beta, limited availability (waitlist)
- Requires Triton dedicated node (~$2,900+/mo)
- Requires Triton's custom Agave validator fork (not stock Agave)
- New API surface (`SubscribeDeshred` vs `Subscribe`)

### RPC Method
```protobuf
rpc SubscribeDeshred(stream SubscribeDeshredRequest) returns (stream SubscribeUpdateDeshred) {}
```

### Filter Definition
```protobuf
message SubscribeRequestFilterDeshredTransactions {
  optional bool vote = 1;
  repeated string account_include = 2;
  repeated string account_exclude = 3;
  repeated string account_required = 4;
}
```

## Decision Matrix

| If you need... | Use... |
|---|---|
| Lowest cost, willing to run infra | Jito ShredStream (free + server) |
| Minimal code changes from Yellowstone | Shyft RabbitStream |
| Absolute lowest latency | Triton Deshred |
| No self-hosted infrastructure | Shyft RabbitStream or Triton Deshred |
| Server-side filtering | Shyft RabbitStream or Triton Deshred |
| Feed shreds to your own validator | Jito ShredStream |

## Bundled Provider Access

Some RPC providers include ShredStream automatically:
- **Chainstack** — ShredStream on all Solana nodes
- **RPC Fast** — ShredStream gRPC as free add-on to dedicated nodes
- **Everstake** — Connect ($199/mo), Pro ($499/mo), Enterprise (custom)
- **QuickNode** — gRPC products on ShredStream-enabled leader nodes
