# Solana RPC — Provider Comparison

## Provider Overview

| Provider | Free Tier | Entry Paid | Best For |
|----------|-----------|------------|----------|
| **Helius** | 50K credits/day | $49/mo (500K) | Best all-around, DAS API included |
| **QuickNode** | 50 req/s | $49/mo | Multi-chain, marketplace add-ons |
| **Triton** | No free | ~$300/mo | Yellowstone bundled, low latency |
| **Shyft** | Limited | $49/mo | Yellowstone + RabbitStream |
| **Alchemy** | 300M CU/mo | Scaling | Large free tier, enterprise |
| **Chainstack** | 3M req/mo | $29/mo | Budget option |
| **Public** | Free | — | Testing only |

## Detailed Comparison

### Helius
- **URL format**: `https://mainnet.helius-rpc.com/?api-key=YOUR_KEY`
- **Strengths**: DAS API, Enhanced Transactions, Webhooks, Priority Fee API
- **Free tier**: 50K credits/day (most calls = 1 credit)
- **Paid**: Developer $49/mo (500K), Business $199/mo (2M), Professional $999/mo (10M)
- **WebSocket**: Included
- **Yellowstone**: LaserStream on Professional tier ($999/mo)

### QuickNode
- **URL format**: `https://YOUR_ENDPOINT.solana-mainnet.quiknode.pro/YOUR_KEY`
- **Strengths**: Multi-chain (100+ chains), marketplace add-ons
- **Free tier**: 50 req/s, 10M API credits/mo
- **Paid**: Build $49/mo, Scale $299/mo
- **WebSocket**: Included
- **Yellowstone**: Available as add-on

### Triton (by Triton One)
- **URL format**: Custom endpoint provided
- **Strengths**: Lowest latency, Yellowstone (Dragon's Mouth) bundled, DeShed
- **Free tier**: None
- **Paid**: ~$300/mo+ (contact sales)
- **Yellowstone**: Dragon's Mouth gRPC included
- **Best for**: Professional/HFT operations

### Shyft
- **URL format**: `https://rpc.shyft.to?api_key=YOUR_KEY`
- **Strengths**: Yellowstone + RabbitStream (pre-exec streaming)
- **Free tier**: Limited
- **Paid**: $49/mo (Growth), $199/mo (Premium)
- **Yellowstone**: Included on paid tiers
- **RabbitStream**: Pre-execution data streaming

### Alchemy
- **URL format**: `https://solana-mainnet.g.alchemy.com/v2/YOUR_KEY`
- **Strengths**: Large free tier, auto-scaling, analytics dashboard
- **Free tier**: 300M compute units/mo
- **Paid**: Growth (scaling), Enterprise
- **Note**: CU-based pricing, different methods cost different CUs

## Choosing a Provider

### For development / research
Use **Helius** free tier — best DX, DAS API, and Enhanced Transactions included.

### For production trading
Use **Helius** paid or **Triton** — low latency, reliable, Yellowstone available.

### For multi-chain projects
Use **QuickNode** or **Alchemy** — both support 100+ chains.

### For HFT / latency-sensitive
Use **Triton** — lowest latency, Yellowstone bundled, bare-metal options.

## Public RPC Endpoints

For testing only — rate limited, unreliable, no SLA:
- `https://api.mainnet-beta.solana.com`
- `https://api.devnet.solana.com`
- `https://api.testnet.solana.com`

**Never use public endpoints for trading.** They are rate limited (10-40 req/s), may drop requests under load, and provide no uptime guarantees.

## Environment Setup

```bash
# Add to your shell profile (~/.zshrc or ~/.bashrc)
export SOLANA_RPC_URL="https://mainnet.helius-rpc.com/?api-key=YOUR_KEY"

# For development, also set devnet
export SOLANA_DEVNET_URL="https://api.devnet.solana.com"
```

```python
import os
RPC = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
```
