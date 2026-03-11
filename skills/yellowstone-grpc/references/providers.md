# Yellowstone gRPC — Provider Comparison

## Shyft

- **Entry price**: $199/mo (Build plan)
- **Endpoints**: `grpc.{region}.shyft.to` — NY, VA, MIA, AMS, FRA, LON, SGP
- **Auth**: x-token from dashboard, or IP whitelisting
- **Bandwidth**: Unlimited (no metering)
- **Connections**: 10 (Build), 20 (Grow/$349), 50 (Accelerate/$649)
- **Dedicated nodes**: From $1,800/mo (unlimited connections, 5-10ms latency advantage)
- **Historical replay**: Up to 150 slots lookback
- **Unique feature**: RabbitStream — pre-execution shred-level data (transactions before confirmation, no metadata)
- **DeFi parsing examples**: [github.com/Shyft-to/solana-defi](https://github.com/Shyft-to/solana-defi) — Raydium, PumpFun, Orca, Meteora parsers
- **Connection management**: Clear stale connections via `https://grpc.{region}.shyft.to/clear-connections?xtoken=YOUR_TOKEN`
- **Best for**: Price-sensitive teams, PumpFun/DEX trading, good regional coverage

## Helius (LaserStream)

- **Entry price**: $999/mo (Professional plan, mainnet gRPC)
- **Endpoints**:
  - US East: `laserstream-mainnet-ewr.helius-rpc.com`
  - US West: `laserstream-mainnet-slc.helius-rpc.com`
  - Europe: `laserstream-mainnet-fra.helius-rpc.com`
  - Asia: `laserstream-mainnet-tyo.helius-rpc.com`
  - Devnet: `laserstream-devnet-ewr.helius-rpc.com`
- **Auth**: API key as x-token
- **Bandwidth**: Credit-based + data add-ons ($500/5TB, scaling tiers)
- **Historical replay**: Up to 24 hours
- **Unique features**: DAS API (token/NFT metadata), enhanced webhooks, auto-reconnect, multi-node failover
- **Best for**: Teams already using Helius RPC/DAS, need rich Solana APIs beyond streaming

## Triton One (Dragon's Mouth)

- **Entry price**: ~$2,900/mo (dedicated nodes)
- **Bandwidth**: ~$0.08/GB
- **Auth**: x-token
- **Created Yellowstone**: Triton built and open-sources the Yellowstone gRPC plugin
- **Unique features**:
  - **Deshred** (`SubscribeDeshred`): Pre-execution transaction streaming (~6.3ms p50, ~20ms p90). Paid beta, limited availability
  - **Fumarole**: Multi-node HA aggregator for persistent streaming
  - **Old Faithful**: Historical data replay (full archive)
  - **Whirligig**: Enhanced WebSocket proxy over Yellowstone
- **Best for**: HFT/MEV, lowest raw latency, enterprise infrastructure

## QuickNode

- **Entry price**: Marketplace add-on (price depends on base plan)
- **Port**: 10000 (separate from RPC)
- **Endpoint format**: `your-endpoint.solana-mainnet.quiknode.pro:10000`
- **Auth**: Built into endpoint URL
- **Rate limits**: Tied to plan RPS (e.g., 125 RPS on Accelerate)
- **Historical replay**: Up to 3000 slots via `from_slot`
- **Best for**: Teams already on QuickNode, flexible add-on model

## Chainstack

- **Entry price**: $49/mo (1 stream)
- **Tiers**: $49/1 stream, $149/5 streams, $449/25 streams
- **Limits**: Up to 50 accounts per stream, 5 concurrent filters of same type
- **Features**: Jito ShredStream enabled by default on all nodes
- **Best for**: Budget option, teams needing ShredStream bundled

## Alchemy

- **Entry price**: Free tier (30M compute units/mo)
- **Bandwidth**: ~$0.08/GB for gRPC
- **Pay-as-you-go**: $5 per 11M compute units
- **Best for**: Experimentation, low-volume testing

## GetBlock

- **Entry price**: Included with Dedicated Solana Node subscription
- **Auth**: Access token created after node deployment
- **Features**: Single TLS endpoint (no separate port config)
- **Best for**: Teams with existing GetBlock dedicated nodes

## Provider Selection Guide

| Priority | Recommended |
|----------|------------|
| Lowest cost with gRPC | Chainstack ($49/mo, limited) or Shyft ($199/mo, full) |
| Best value for trading | **Shyft** ($199-649/mo, unlimited bandwidth, 7 regions) |
| Rich Solana APIs + gRPC | Helius ($999/mo, DAS + webhooks + gRPC) |
| Lowest latency / HFT | **Triton One** (Deshred: ~6ms p50) |
| Free experimentation | Alchemy (free tier, CU-metered) |
| Already on QuickNode | QuickNode add-on |

## Authentication Code (All Providers)

All providers use the same x-token pattern:

```python
import grpc, os

endpoint = os.environ["GRPC_ENDPOINT"].replace("https://", "")
token = os.environ["GRPC_TOKEN"]

auth = grpc.metadata_call_credentials(
    lambda ctx, cb: cb((("x-token", token),), None)
)
channel = grpc.secure_channel(
    endpoint,
    grpc.composite_channel_credentials(grpc.ssl_channel_credentials(), auth),
    options=[("grpc.max_receive_message_length", 64 * 1024 * 1024)],
)
```

```rust
use yellowstone_grpc_client::GeyserGrpcClient;
let mut client = GeyserGrpcClient::connect(endpoint, Some(token), None).await?;
```

```typescript
import Client from "@triton-one/yellowstone-grpc";
const client = new Client(endpoint, token, {
  "grpc.max_receive_message_length": 64 * 1024 * 1024,
});
```
