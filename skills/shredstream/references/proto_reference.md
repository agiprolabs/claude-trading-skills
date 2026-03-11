# ShredStream — Protobuf & Data Reference

Source: [jito-labs/mev-protos](https://github.com/jito-labs/mev-protos/blob/master/shredstream.proto)

## Proto Definitions

### ShredStream Service (Block Engine ↔ Proxy)

```protobuf
service Shredstream {
  rpc SendHeartbeat(Heartbeat) returns (HeartbeatResponse) {}
}

message Heartbeat {
  shared.Socket socket = 1;   // IP must match incoming packet (anti-spoofing)
  repeated string regions = 2; // desired regions, max 2
}

message HeartbeatResponse {
  uint32 ttl_ms = 1;  // must send next heartbeat within this window
}
```

The proxy sends heartbeats to the Block Engine to maintain the shred stream. If a heartbeat is missed (exceeds `ttl_ms`), the stream stops.

### ShredStream Proxy Service (Proxy ↔ Your Code)

```protobuf
service ShredstreamProxy {
  rpc SubscribeEntries(SubscribeEntriesRequest) returns (stream Entry) {}
}

message SubscribeEntriesRequest {
  // Currently no filters — you get everything
}

message Entry {
  uint64 slot = 1;
  bytes entries = 2;  // bincode-serialized Vec<solana_entry::entry::Entry>
}
```

### Shared Types

```protobuf
message Socket {
  string ip = 1;
  int64 port = 2;
}
```

### Trace Shred (Debugging)

```protobuf
message TraceShred {
  string region = 1;
  google.protobuf.Timestamp created_at = 2;
  uint32 seq_num = 3;  // monotonically increases, resets on restart
}
```

## Solana Entry Structure

The `Entry.entries` field contains bincode-serialized `Vec<solana_entry::entry::Entry>`:

```rust
/// A Solana entry — a batch of transactions with a PoH hash
pub struct Entry {
    pub num_hashes: u64,                    // PoH hashes since previous entry
    pub hash: Hash,                         // resulting PoH hash (32 bytes)
    pub transactions: Vec<VersionedTransaction>,
}

/// A versioned transaction (v0 or legacy)
pub struct VersionedTransaction {
    pub signatures: Vec<Signature>,         // first is the tx signature
    pub message: VersionedMessage,          // legacy or v0
}

/// Transaction message (v0 with ALT support)
pub struct v0::Message {
    pub header: MessageHeader,
    pub account_keys: Vec<Pubkey>,          // static account keys
    pub recent_blockhash: Hash,
    pub instructions: Vec<CompiledInstruction>,
    pub address_table_lookups: Vec<MessageAddressTableLookup>,
}

pub struct CompiledInstruction {
    pub program_id_index: u8,               // index into account_keys
    pub accounts: Vec<u8>,                  // indices into account_keys
    pub data: Vec<u8>,                      // instruction data (program-specific)
}
```

## Parsing Flow

### Step 1: Receive Entry from gRPC

```rust
let entry_msg: Entry = stream.message().await?.unwrap();
let slot = entry_msg.slot;
```

### Step 2: Deserialize Entries

```rust
let entries: Vec<solana_entry::entry::Entry> =
    bincode::deserialize(&entry_msg.entries)
        .expect("failed to deserialize entries");
```

### Step 3: Extract Transactions

```rust
for entry in &entries {
    for tx in &entry.transactions {
        let signature = tx.signatures[0];
        let message = tx.message();

        // Static account keys
        let account_keys = message.static_account_keys();

        // Instructions
        for ix in message.instructions() {
            let program_id = account_keys[ix.program_id_index as usize];
            let accounts: Vec<Pubkey> = ix.accounts
                .iter()
                .map(|&i| account_keys[i as usize])
                .collect();
            let data = &ix.data;

            // Match by program ID
            if program_id == pumpfun_program_id {
                let discriminator = &data[..8];
                // Parse instruction-specific data
            }
        }
    }
}
```

### Step 4: Handle Address Lookup Tables (v0 Transactions)

v0 transactions may reference accounts via Address Lookup Tables (ALTs). These accounts are NOT in `static_account_keys()`. To resolve them:

```rust
// Check if transaction uses ALTs
if let VersionedMessage::V0(msg) = &tx.message {
    for lookup in &msg.address_table_lookups {
        // lookup.account_key = the ALT address
        // lookup.writable_indexes = indices into ALT for writable accounts
        // lookup.readonly_indexes = indices into ALT for readonly accounts

        // To resolve: fetch the ALT account data via RPC
        // let alt_data = rpc.get_account(&lookup.account_key).await?;
        // Parse addresses from ALT data at the specified indices
    }
}
```

**Important**: Without resolving ALTs, you may miss some accounts referenced in instructions. For pre-execution use cases where speed matters, you can:
1. Pre-cache frequently used ALTs (Jupiter, Raydium, etc.)
2. Skip ALT resolution and work only with static keys (misses some accounts)
3. Resolve lazily after initial signal detection

## What You Can Extract (Without Execution)

| Data | Available? | How |
|------|-----------|-----|
| Transaction signature | Yes | `tx.signatures[0]` |
| Signer (fee payer) | Yes | `account_keys[0]` |
| Programs called | Yes | `account_keys[ix.program_id_index]` |
| Instruction data | Yes | `ix.data` (decode per program IDL) |
| Static account keys | Yes | `message.static_account_keys()` |
| ALT-referenced accounts | Partial | Need ALT data to resolve indices |
| Success/failure | No | Transaction hasn't executed yet |
| Balance changes | No | Need execution results |
| Log messages | No | Need execution results |
| Inner instructions (CPI) | No | Need execution results |
| Token balance changes | No | Need execution results |
| Compute units | No | Need execution results |

## Comparison with Yellowstone gRPC Data

| Field | ShredStream Entry | Yellowstone SubscribeUpdateTransaction |
|-------|-------------------|---------------------------------------|
| Signature | `tx.signatures[0]` | `info.signature` |
| Slot | `entry.slot` | `tx_update.slot` |
| Account keys | `msg.static_account_keys()` | `msg.account_keys` (all resolved) |
| Instructions | `msg.instructions()` | `msg.instructions` |
| ALT resolution | Manual (need ALT data) | Automatic (loaded addresses in meta) |
| Execution status | Not available | `meta.err` |
| Balances | Not available | `meta.pre_balances`, `meta.post_balances` |
| Token balances | Not available | `meta.pre_token_balances`, `meta.post_token_balances` |
| Logs | Not available | `meta.log_messages` |
| Inner instructions | Not available | `meta.inner_instructions` |
| Compute units | Not available | `meta.compute_units_consumed` |
| Block position | Entry order within slot | `info.index` |
