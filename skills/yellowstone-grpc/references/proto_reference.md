# Yellowstone gRPC — Protobuf Reference

Source: [rpcpool/yellowstone-grpc](https://github.com/rpcpool/yellowstone-grpc/blob/master/yellowstone-grpc-proto/proto/geyser.proto)

## Service Definition

```protobuf
service Geyser {
  rpc Subscribe(stream SubscribeRequest) returns (stream SubscribeUpdate) {}
  rpc Ping(PingRequest) returns (PongResponse) {}
  rpc GetLatestBlockhash(GetLatestBlockhashRequest) returns (GetLatestBlockhashResponse) {}
  rpc GetBlockHeight(GetBlockHeightRequest) returns (GetBlockHeightResponse) {}
  rpc GetSlot(GetSlotRequest) returns (GetSlotResponse) {}
  rpc IsBlockhashValid(IsBlockhashValidRequest) returns (IsBlockhashValidResponse) {}
  rpc GetVersion(GetVersionRequest) returns (GetVersionResponse) {}
}
```

`Subscribe` is bidirectional streaming — you send `SubscribeRequest` messages and receive `SubscribeUpdate` messages continuously.

## SubscribeRequest

```protobuf
message SubscribeRequest {
  map<string, SubscribeRequestFilterAccounts> accounts = 1;
  map<string, SubscribeRequestFilterSlots> slots = 2;
  map<string, SubscribeRequestFilterTransactions> transactions = 3;
  map<string, SubscribeRequestFilterTransactions> transactions_status = 10;
  map<string, SubscribeRequestFilterBlocks> blocks = 4;
  map<string, SubscribeRequestFilterBlocksMeta> blocks_meta = 5;
  map<string, SubscribeRequestFilterEntry> entry = 8;
  optional CommitmentLevel commitment = 6;
  repeated SubscribeRequestAccountsDataSlice accounts_data_slice = 7;
  optional SubscribeRequestPing ping = 9;
  optional uint64 from_slot = 11;
}
```

Map keys are user-defined labels. They appear in `SubscribeUpdate.filters` to identify which subscription matched.

## SubscribeUpdate (Response)

```protobuf
message SubscribeUpdate {
  repeated string filters = 1;  // which named filters matched
  oneof update_oneof {
    SubscribeUpdateAccount account = 2;
    SubscribeUpdateSlot slot = 3;
    SubscribeUpdateTransaction transaction = 4;
    SubscribeUpdateTransactionStatus transaction_status = 10;
    SubscribeUpdateBlock block = 5;
    SubscribeUpdatePing ping = 6;
    SubscribeUpdatePong pong = 9;
    SubscribeUpdateBlockMeta block_meta = 7;
    SubscribeUpdateEntry entry = 8;
  }
  google.protobuf.Timestamp created_at = 11;
}
```

## Transaction Update

```protobuf
message SubscribeUpdateTransaction {
  SubscribeUpdateTransactionInfo transaction = 1;
  uint64 slot = 2;
}

message SubscribeUpdateTransactionInfo {
  bytes signature = 1;            // 64 bytes, base58-encode for display
  bool is_vote = 2;
  Transaction transaction = 3;    // from solana-storage.proto
  TransactionStatusMeta meta = 4; // execution results
  uint64 index = 5;               // position within the block
}
```

### Transaction (Inner)

```protobuf
message Transaction {
  repeated bytes signatures = 1;  // first is the tx signature
  Message message = 2;
}

message Message {
  MessageHeader header = 1;
  repeated bytes account_keys = 2;    // all account pubkeys (32 bytes each)
  bytes recent_blockhash = 3;
  repeated CompiledInstruction instructions = 4;
  bool versioned = 5;
  repeated MessageAddressTableLookup address_table_lookups = 6;
}

message MessageHeader {
  uint32 num_required_signatures = 1;
  uint32 num_readonly_signed_accounts = 2;
  uint32 num_readonly_unsigned_accounts = 3;
}

message CompiledInstruction {
  uint32 program_id_index = 1;  // index into account_keys
  bytes accounts = 2;           // indices into account_keys
  bytes data = 3;               // instruction data (program-specific)
}
```

### TransactionStatusMeta (Post-Execution)

```protobuf
message TransactionStatusMeta {
  TransactionError err = 1;
  uint64 fee = 2;
  repeated uint64 pre_balances = 3;   // SOL balances before (lamports)
  repeated uint64 post_balances = 4;  // SOL balances after (lamports)
  repeated InnerInstructions inner_instructions = 5;
  repeated string log_messages = 6;
  repeated TokenBalance pre_token_balances = 7;
  repeated TokenBalance post_token_balances = 8;
  repeated Reward rewards = 9;
  repeated bytes loaded_writable_addresses = 12;
  repeated bytes loaded_readonly_addresses = 13;
  ReturnData return_data = 14;
  optional uint64 compute_units_consumed = 15;
}
```

### Token Balance

```protobuf
message TokenBalance {
  uint32 account_index = 1;  // index into account_keys
  string mint = 2;           // token mint address (base58)
  UiTokenAmount ui_token_amount = 3;
  string owner = 4;          // token account owner (base58)
}

message UiTokenAmount {
  double ui_amount = 1;      // human-readable amount
  uint32 decimals = 2;
  string amount = 3;         // raw amount as string
}
```

### Inner Instructions

```protobuf
message InnerInstructions {
  uint32 index = 1;  // which top-level instruction generated these
  repeated InnerInstruction instructions = 2;
}

message InnerInstruction {
  uint32 program_id_index = 1;
  bytes accounts = 2;
  bytes data = 3;
  optional uint32 stack_height = 4;
}
```

## Account Update

```protobuf
message SubscribeUpdateAccount {
  SubscribeUpdateAccountInfo account = 1;
  uint64 slot = 2;
  optional bool is_startup = 3;
}

message SubscribeUpdateAccountInfo {
  bytes pubkey = 1;           // 32 bytes
  uint64 lamports = 2;
  bytes owner = 3;            // program that owns this account (32 bytes)
  bool executable = 4;
  uint64 rent_epoch = 5;
  bytes data = 6;             // account data (variable length)
  uint64 write_version = 7;
  optional bytes txn_signature = 8;  // which tx caused this update
}
```

## Commitment Levels

```protobuf
enum CommitmentLevel {
  PROCESSED = 0;   // fastest, may be rolled back
  CONFIRMED = 1;   // supermajority voted
  FINALIZED = 2;   // irreversible
}
```

## Slot Status

```protobuf
enum SlotStatus {
  SLOT_PROCESSED = 0;
  SLOT_CONFIRMED = 1;
  SLOT_FINALIZED = 2;
  SLOT_FIRST_SHRED_RECEIVED = 3;
  SLOT_COMPLETED = 4;
  SLOT_CREATED_BANK = 5;
  SLOT_DEAD = 6;
}
```

## Parsing Checklist

When processing a `SubscribeUpdateTransaction`:

1. **Signature**: `base58.b58encode(info.signature).decode()`
2. **Account keys**: Decode each 32-byte entry in `message.account_keys` to base58
3. **Instructions**: For each `CompiledInstruction`:
   - Program = `account_keys[program_id_index]`
   - Accounts = `[account_keys[i] for i in accounts]`
   - Data = raw bytes, first 8 bytes are typically the instruction discriminator
4. **Inner instructions**: CPI calls generated during execution — same structure as top-level
5. **Token changes**: Compare `pre_token_balances` vs `post_token_balances` for swap amounts
6. **SOL changes**: Compare `pre_balances` vs `post_balances` for fee and SOL transfer analysis
7. **Logs**: `meta.log_messages` contain program logs (useful for debugging)
8. **Compute**: `meta.compute_units_consumed` for gas analysis
