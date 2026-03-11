# Yellowstone gRPC — Performance & Production Guide

## Latency Benchmarks

| Method | Slot Latency (p90) | Account Latency (p90) | Notes |
|--------|-------------------|-----------------------|-------|
| REST polling | ~150ms+ | N/A | Polling overhead + HTTP |
| WebSocket (`onLogs`) | ~10ms | ~374ms | Event-based, limited filtering |
| Yellowstone gRPC | ~5ms | ~215ms | Push-based, rich filtering |
| Deshred (Triton only) | ~20ms (p90) | N/A | Pre-execution, ~6.3ms p50 |

## Data Volume Expectations

- **All Solana transactions**: ~2,000-4,000 TPS (including votes)
- **Vote transactions**: ~70% of total — always filter with `vote: false`
- **PumpFun alone**: ~20,000+ trades/hour during active periods
- **Single DEX program filter**: ~100-1,000 updates/second depending on activity
- **Single wallet filter**: ~0.01-10 updates/second depending on activity

## Connection Management

### Max Message Size

The default gRPC max message size (4MB) is too small for Solana. Set it higher:

```python
# Python
options = [("grpc.max_receive_message_length", 64 * 1024 * 1024)]  # 64MB

# For block subscriptions, go higher
options = [("grpc.max_receive_message_length", 1024 * 1024 * 1024)]  # 1GB
```

```rust
// Rust
.max_decoding_message_size(64 * 1024 * 1024)
```

```typescript
// TypeScript
{ "grpc.max_receive_message_length": 64 * 1024 * 1024 }
```

### Keep-Alive / Ping

Send pings every 15-30 seconds to prevent connection timeout:

```python
import time, threading

def ping_loop(request_iterator):
    while True:
        time.sleep(15)
        request_iterator.send(SubscribeRequest(
            ping=SubscribeRequestPing(id=int(time.time()))
        ))
```

Handle pong responses — if you receive a `SubscribeUpdatePing` from the server, respond:

```python
if update.HasField("ping"):
    request_iterator.send(SubscribeRequest(
        ping=SubscribeRequestPing(id=update.ping.id)
    ))
```

### Reconnection with Exponential Backoff

```python
import time, random

def connect_with_backoff(max_delay: float = 60.0):
    delay = 0.1  # start at 100ms
    last_slot = None

    while True:
        try:
            stream = subscribe(from_slot=last_slot)
            delay = 0.1  # reset on success

            for update in stream:
                last_slot = extract_slot(update)
                process(update)

        except grpc.RpcError as e:
            jitter = random.uniform(0, delay * 0.1)
            print(f"Disconnected: {e.code()}. Reconnecting in {delay:.1f}s")
            time.sleep(delay + jitter)
            delay = min(delay * 2, max_delay)
```

### Resume After Disconnection

Use `from_slot` to replay missed data. Subtract ~32 slots for reorg safety:

```python
request = SubscribeRequest(
    transactions={...},
    from_slot=last_processed_slot - 32,
)
```

**Important**: `from_slot` replay may produce duplicate updates. Deduplicate by transaction signature.

Replay depth varies by provider:
- Shyft: ~150 slots
- QuickNode: ~3,000 slots
- Helius: ~24 hours

## Backpressure Architecture

Never process messages in the gRPC receive loop. Decouple I/O from business logic:

```
[gRPC Stream Thread]
    │
    ▼
[Bounded Channel/Queue]  ← backpressure point (1K-100K capacity)
    │
    ▼
[Processing Worker(s)]
    ├─ Parse instructions
    ├─ Update state
    ├─ Trigger signals
    └─ Batch DB writes
```

### Python Implementation

```python
import queue
import threading

msg_queue = queue.Queue(maxsize=10_000)

def grpc_reader(stub, request):
    """Dedicated thread: reads gRPC stream into queue."""
    stream = stub.Subscribe(iter([request]))
    for update in stream:
        try:
            msg_queue.put(update, timeout=1.0)
        except queue.Full:
            print("WARNING: queue full, dropping message")

def processor():
    """Dedicated thread: processes messages from queue."""
    while True:
        update = msg_queue.get()
        handle_update(update)

threading.Thread(target=grpc_reader, args=(stub, request), daemon=True).start()
threading.Thread(target=processor, daemon=True).start()
```

### Rust Implementation

```rust
use tokio::sync::mpsc;

let (tx, mut rx) = mpsc::channel(100_000);

// Spawn gRPC reader
tokio::spawn(async move {
    while let Some(msg) = stream.next().await {
        if tx.send(msg.unwrap()).await.is_err() { break; }
    }
});

// Process in main task
while let Some(update) = rx.recv().await {
    match update.update_oneof {
        Some(UpdateOneof::Transaction(tx)) => handle_transaction(tx),
        _ => {}
    }
}
```

## Database Write Batching

Don't write every update to the database individually. Batch writes:

```python
batch = []
last_flush = time.time()

for update in process_stream():
    batch.append(to_row(update))

    if len(batch) >= 1000 or (time.time() - last_flush) > 1.0:
        db.executemany("INSERT INTO events ...", batch)
        batch.clear()
        last_flush = time.time()
```

## Multi-Connection Patterns

For high-throughput programs, split across multiple gRPC connections:

```
Connection 1: PumpFun transactions      → Worker pool A
Connection 2: Raydium + Orca swaps      → Worker pool B
Connection 3: Tracked wallet activity   → Worker pool C
Connection 4: Pool account updates      → Worker pool D
```

Each connection runs on its own thread/task with independent reconnection logic.

## Monitoring

Track these metrics in production:

| Metric | Alert Threshold | Why |
|--------|----------------|-----|
| Updates received/sec | < expected baseline | Stream may be stalled |
| Queue depth | > 80% capacity | Processing can't keep up |
| Time since last update | > 30 seconds | Connection likely dead |
| Reconnection count | > 5/hour | Provider instability |
| Processing latency | > 100ms p99 | Bottleneck in handlers |
| Dropped messages | > 0 | Queue overflow |

## Production Checklist

- [ ] `vote: false` on all transaction filters
- [ ] `max_receive_message_length` set to 64MB+
- [ ] Exponential backoff reconnection (100ms → 60s cap)
- [ ] `from_slot` resume after disconnection
- [ ] Ping/pong every 15-30 seconds
- [ ] Bounded channel between I/O and processing
- [ ] Database write batching (1000 rows or 1s flush)
- [ ] Duplicate detection on replay (by tx signature)
- [ ] Monitoring: updates/sec, queue depth, reconnection count
- [ ] Graceful shutdown (drain queue before exit)
- [ ] Error classification (retriable vs fatal gRPC errors)
- [ ] Separate connections for independent data streams
