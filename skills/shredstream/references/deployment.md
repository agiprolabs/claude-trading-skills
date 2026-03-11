# ShredStream — Deployment & Infrastructure Guide

## Requirements

### Network
- **Public IP** — Required. NAT is not supported (shreds arrive via UDP)
- **UDP port 20000** — Open for incoming shreds (configurable via `SRC_BIND_PORT`)
- **Host networking** — Docker bridge mode drops UDP multicast. Use `--network host`
- **Low-jitter connection** — Bare metal preferred over cloud VMs

### Hardware (Recommended for HFT)
- **CPU**: Modern AMD (EPYC 9354/9005 series) or Intel Xeon
- **RAM**: 32GB+ (proxy itself is lightweight, but co-located services need more)
- **NIC**: 10Gbps+ with kernel bypass (DPDK/AF_XDP) for lowest latency
- **Storage**: NVMe SSD (for any logging/persistence)

### Software
- **Rust toolchain** (for building from source) or Docker
- **Solana CLI** (for keypair generation): `sh -c "$(curl -sSfL https://release.anza.xyz/stable/install)"`

## Region Selection

Choose regions closest to your server and to major validator clusters.

| Region | Code | Best For |
|--------|------|----------|
| New York | `ny` | US East coast, most Solana validators |
| Amsterdam | `amsterdam` | Europe, good validator density |
| Frankfurt | `frankfurt` | Europe, major datacenter hub |
| London | `london` | Europe |
| Salt Lake City | `salt-lake-city` | US West |
| Singapore | `singapore` | Asia-Pacific |
| Tokyo | `tokyo` | Asia-Pacific |
| Dublin | `dublin` | Europe |

**Max 2 regions per proxy instance.** Run multiple instances for more regions.

### Recommended Co-Location
For lowest latency, co-locate in datacenters near Solana validator clusters:
- **Frankfurt**: OVH, Equinix FR5
- **New York**: Equinix NY, TeraSwitch
- **Amsterdam**: Equinix AM, Interxion
- **Tokyo**: Equinix TY

Co-location trims 20-50ms vs. random cloud placement.

## Firewall Configuration

Each Jito region uses specific IP ranges for shred delivery. You must allow UDP traffic from these IPs on your shred receive port (default 20000).

Check the current IP allowlist at: https://docs.jito.wtf/lowlatencytxnfeed/

General rule:
```bash
# Allow UDP from Jito Block Engine IPs (example, verify current IPs in docs)
sudo ufw allow proto udp from <JITO_IP> to any port 20000
```

Also allow outbound HTTPS (443) for gRPC connection to the Block Engine.

## Running the Proxy

### Build from Source

```bash
git clone https://github.com/jito-labs/shredstream-proxy.git --recurse-submodules
cd shredstream-proxy
cargo build --release
```

### Systemd Service (Production)

```ini
[Unit]
Description=Jito ShredStream Proxy
After=network.target

[Service]
Type=simple
User=solana
Environment=RUST_LOG=info
ExecStart=/opt/shredstream/target/release/jito-shredstream-proxy shredstream \
    --block-engine-url https://mainnet.block-engine.jito.wtf \
    --auth-keypair /opt/shredstream/shred_auth.json \
    --desired-regions ny,amsterdam \
    --dest-ip-ports 127.0.0.1:8001 \
    --grpc-service-port 7777
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp shredstream.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now shredstream
sudo journalctl -u shredstream -f  # monitor logs
```

### Docker (Host Networking)

```bash
docker run -d --name shredstream \
  --network host \
  --restart unless-stopped \
  -e RUST_LOG=info \
  -e BLOCK_ENGINE_URL=https://mainnet.block-engine.jito.wtf \
  -e AUTH_KEYPAIR=/app/shred_auth.json \
  -e DESIRED_REGIONS=ny,amsterdam \
  -e DEST_IP_PORTS=127.0.0.1:8001 \
  -e GRPC_SERVICE_PORT=7777 \
  -v /opt/shredstream/shred_auth.json:/app/shred_auth.json:ro \
  jitolabs/jito-shredstream-proxy shredstream
```

### Fly.io Deployment

For distributed setups, run the proxy on Fly.io near your target region:

```toml
# fly.toml
app = "my-shredstream"
primary_region = "ewr"  # Newark (close to NY)

[build]
image = "jitolabs/jito-shredstream-proxy"

[env]
RUST_LOG = "info"
BLOCK_ENGINE_URL = "https://mainnet.block-engine.jito.wtf"
DESIRED_REGIONS = "ny"
GRPC_SERVICE_PORT = "7777"

[[services]]
internal_port = 7777
protocol = "tcp"
[[services.ports]]
port = 7777

[[services]]
internal_port = 20000
protocol = "udp"
[[services.ports]]
port = 20000
```

**Note**: Fly.io may not support raw UDP well on all regions. Test thoroughly.

## Verification

### Check Shred Receipt
```bash
# Should see continuous stream of ~1200-byte UDP packets
sudo tcpdump -i any 'udp and dst port 20000' -c 10

# Count packets per second
sudo tcpdump -i any 'udp and dst port 20000' -w /dev/null 2>&1 | head -1
```

### Check gRPC Output
```bash
# If you have grpcurl installed
grpcurl -plaintext localhost:7777 shredstream.ShredstreamProxy/SubscribeEntries
```

### Check Proxy Logs
```bash
# Look for successful heartbeat responses and shred counts
journalctl -u shredstream --since "5 minutes ago" | grep -E "heartbeat|shred|entries"
```

## Monitoring

| Metric | How to Check | Alert On |
|--------|-------------|----------|
| Shreds/second | `tcpdump` packet count | < 100/sec (stream may be dead) |
| Heartbeat TTL | Proxy logs | Missed heartbeats (reconnection needed) |
| gRPC clients connected | Proxy logs | Unexpected disconnections |
| Entry deserialization errors | Proxy logs | Non-zero error rate |
| Slot gaps | Compare slots in entries | Gaps > 2 consecutive slots |

## Common Issues

### No Shreds Arriving
1. Check keypair is whitelisted (re-apply if needed)
2. Verify UDP port is open: `sudo ufw status | grep 20000`
3. Check Block Engine URL is reachable: `curl -s https://mainnet.block-engine.jito.wtf`
4. Ensure no NAT between you and the internet
5. Try different regions

### High Latency
1. Move closer to validators (Frankfurt/NY/Amsterdam)
2. Switch from cloud VM to bare metal
3. Check for CPU contention: `htop`
4. Verify NIC is not saturated

### Docker Shred Loss
- **Use host networking** (`--network host`), not bridge mode
- Bridge mode fragments UDP multicast and drops packets
- If host networking is unavailable, use `SRC_BIND_PORT` and explicit port mapping
