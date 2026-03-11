# Raptor Deployment Guide

## Prerequisites

- **Solana RPC endpoint** — Any RPC provider (Helius, Triton, QuickNode, etc.)
- **Yellowstone gRPC endpoint** — Required for pool state streaming (Helius, Triton, Shyft)
- **Signature file** — Must be in the same working directory as the binary (included in repo clone)

Raptor uses very few RPC calls during normal operation since pool state is streamed via Yellowstone gRPC.

## Signature File

The `signature` file authenticates your Raptor instance. It is **required** and must be in the same directory where the binary runs.

```bash
# After cloning, both files are present:
ls raptor-binary/
# raptor          ← the binary
# signature       ← required auth file

# If you move the binary, ALWAYS copy the signature file too
cp raptor /opt/raptor/
cp signature /opt/raptor/
cd /opt/raptor && ./raptor   # signature must be in working directory
```

Without the signature file, Raptor will fail to start.

## Bare Metal / VPS

```bash
# Option A: Clone from GitHub
git clone https://github.com/solanatracker/raptor-binary
cd raptor-binary

# Option B: Download binary directly
curl -L https://github.com/solanatracker/raptor/releases/latest/download/raptor-linux-amd64 -o raptor
chmod +x raptor
# You still need the signature file from the repo

# Set environment and run
export RPC_URL="https://your-rpc.com"
export YELLOWSTONE_ENDPOINT="https://your-yellowstone.com"
export YELLOWSTONE_TOKEN="your-token"
./raptor
```

### Recommended: systemd Service

```ini
# /etc/systemd/system/raptor.service
[Unit]
Description=Raptor DEX Aggregator
After=network.target

[Service]
Type=simple
User=raptor
WorkingDirectory=/opt/raptor
ExecStart=/opt/raptor/raptor
Environment=RPC_URL=https://your-rpc.com
Environment=YELLOWSTONE_ENDPOINT=https://your-yellowstone.com
Environment=YELLOWSTONE_TOKEN=your-token
Environment=ENABLE_WEBSOCKET=true
Environment=ENABLE_YELLOWSTONE_JET=true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now raptor
sudo journalctl -u raptor -f  # watch logs
```

## Docker

```dockerfile
FROM ubuntu:22.04
COPY raptor /usr/local/bin/raptor
COPY signature /usr/local/bin/signature
RUN chmod +x /usr/local/bin/raptor
WORKDIR /usr/local/bin
CMD ["raptor"]
```

```bash
docker build -t raptor .
docker run -d \
  -e RPC_URL="https://your-rpc.com" \
  -e YELLOWSTONE_ENDPOINT="https://your-yellowstone.com" \
  -e YELLOWSTONE_TOKEN="your-token" \
  -e ENABLE_WEBSOCKET=true \
  -p 8080:8080 \
  raptor
```

## Fly.io

```toml
# fly.toml
app = "my-raptor"
primary_region = "ewr"  # East US — pick closest to your RPC

[build]
  dockerfile = "Dockerfile"

[env]
  RPC_URL = "https://your-rpc.com"
  YELLOWSTONE_ENDPOINT = "https://your-yellowstone.com"
  INCLUDE_DEXES = "raydium,orca,meteora,pumpfun,pumpswap"
  ENABLE_WEBSOCKET = "true"
  ENABLE_YELLOWSTONE_JET = "true"

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
fly secrets set YELLOWSTONE_TOKEN="your-token"
fly deploy
```

## DEX Filter Presets

```bash
# PumpFun sniping — only bonding curves
INCLUDE_DEXES="pumpfun,pumpswap,heaven,moonit,boopfun" ./raptor

# Major AMMs only
INCLUDE_DEXES="raydium,orca,meteora" ./raptor

# Everything except bonding curves
EXCLUDE_DEXES="pumpfun,pumpswap,heaven,moonit,boopfun" ./raptor
```

## Performance Tuning

| Setting | Recommendation |
|---------|---------------|
| `WORKER_THREADS` | Match CPU cores (default). For quote-heavy loads, try 2x cores |
| `RPC_RATE_LIMIT` | Set to your RPC provider's limit to avoid 429s |
| Region | Co-locate with your RPC and Yellowstone providers |
| Memory | 4GB minimum recommended for full DEX indexing |

## Health Check

```bash
curl http://localhost:8080/health
# Returns: pool count, cache status, Yellowstone connection state
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Slow startup (1-2 min) | Normal — pool indexing via Yellowstone. Use `--no-pool-indexer` to skip (quotes may be incomplete) |
| Quote returns 0 output | Token has no liquidity on included DEXes. Check `INCLUDE_DEXES` |
| Transaction fails | Check slippage, priority fee, and blockhash freshness |
| Signature file missing | Copy from repo clone to working directory |
| WebSocket not connecting | Set `ENABLE_WEBSOCKET=true` or `--enable-websocket` |
| `/send-transaction` 503 | Set `ENABLE_YELLOWSTONE_JET=true` and verify Yellowstone endpoint |
