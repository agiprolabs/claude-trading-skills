# Yellowstone gRPC — Subscription Filters Reference

## How Filters Work

A `SubscribeRequest` contains named filter maps. Each map key is a label you choose — it appears in the response's `filters` field so you know which subscription matched.

- Multiple filter **types** (transactions + accounts in same request) run independently
- Values within arrays (`account_include: [A, B, C]`) are logical **OR**
- Sending a new `SubscribeRequest` **replaces** all previous filters entirely
- To unsubscribe, send empty maps for all types

## Transaction Filters

Filter real-time transactions by involved accounts, vote status, and failure status.

```protobuf
message SubscribeRequestFilterTransactions {
  optional bool vote = 1;              // include vote transactions?
  optional bool failed = 2;            // include failed transactions?
  optional string signature = 5;       // watch a specific signature
  repeated string account_include = 3; // tx must involve ANY of these
  repeated string account_exclude = 4; // tx must NOT involve ANY of these
  repeated string account_required = 6;// tx must involve ALL of these
}
```

### Filter by Program ID

Subscribe to all successful transactions involving a DEX program:

```python
transactions={
    "raydium_swaps": SubscribeRequestFilterTransactions(
        account_include=["675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"],
        vote=False,
        failed=False,
    )
}
```

### Filter by Multiple Programs

OR logic — matches transactions involving ANY listed program:

```python
transactions={
    "all_dex": SubscribeRequestFilterTransactions(
        account_include=[
            "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # PumpFun
            "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM
            "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",   # Orca
        ],
        vote=False,
        failed=False,
    )
}
```

### Filter by Wallet (Copy Trading)

Watch specific wallets for any on-chain activity:

```python
transactions={
    "tracked_wallets": SubscribeRequestFilterTransactions(
        account_include=[
            "WalletPubkey1...",
            "WalletPubkey2...",
        ],
        vote=False,
        failed=False,
    )
}
```

### Exclude Known Programs

Exclude noisy programs to reduce volume:

```python
transactions={
    "clean_feed": SubscribeRequestFilterTransactions(
        account_include=["TargetWallet..."],
        account_exclude=[
            "Vote111111111111111111111111111111111111111",
            "ComputeBudget111111111111111111111111111111",
        ],
        vote=False,
        failed=False,
    )
}
```

### Require Multiple Accounts (AND logic)

Match only transactions that involve ALL listed accounts:

```python
transactions={
    "wallet_on_pumpfun": SubscribeRequestFilterTransactions(
        account_required=[
            "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # PumpFun
            "SpecificWalletAddress...",                         # Target wallet
        ],
        vote=False,
        failed=False,
    )
}
```

### Watch a Specific Transaction

Track confirmation of a submitted transaction:

```python
transactions={
    "my_tx": SubscribeRequestFilterTransactions(
        signature="5wHu1qwD7q8ZHqDRYBiHMk2aJ4C8tNqVNK5...",
    )
}
```

## Account Filters

Stream account data whenever it changes on-chain. Useful for tracking pool reserves, token balances, and program state.

```protobuf
message SubscribeRequestFilterAccounts {
  repeated string account = 2;    // specific account pubkeys
  repeated string owner = 3;      // accounts owned by these programs
  repeated SubscribeRequestFilterAccountsFilter filters = 4;
  optional bool nonempty_txn_signature = 5;
}
```

### Watch Specific Accounts

```python
accounts={
    "pool_reserves": SubscribeRequestFilterAccounts(
        account=["PoolAccountPubkey1...", "PoolAccountPubkey2..."],
    )
}
```

### Watch All Accounts Owned by a Program

```python
accounts={
    "all_token_accounts": SubscribeRequestFilterAccounts(
        owner=["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"],
        filters=[
            SubscribeRequestFilterAccountsFilter(token_account_state=True)
        ],
    )
}
```

**Warning**: Subscribing to all accounts owned by the Token Program produces enormous data volume. Always add filters to narrow the stream.

### Memcmp Filter (Match Bytes at Offset)

Filter accounts by specific bytes at a given offset in account data:

```python
# Match token accounts for a specific mint (mint pubkey at offset 0)
accounts={
    "sol_token_accounts": SubscribeRequestFilterAccounts(
        owner=["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"],
        filters=[
            SubscribeRequestFilterAccountsFilter(
                memcmp=SubscribeRequestFilterAccountsFilterMemcmp(
                    offset=0,
                    base58="So11111111111111111111111111111111111111112",
                )
            )
        ],
    )
}
```

### Data Size Filter

Match accounts by exact data length:

```python
accounts={
    "sized_accounts": SubscribeRequestFilterAccounts(
        owner=["YourProgramId..."],
        filters=[
            SubscribeRequestFilterAccountsFilter(datasize=165)  # SPL token account size
        ],
    )
}
```

### Lamports Filter

Filter by SOL balance:

```python
accounts={
    "whales": SubscribeRequestFilterAccounts(
        owner=["11111111111111111111111111111111"],
        filters=[
            SubscribeRequestFilterAccountsFilter(
                lamports=SubscribeRequestFilterAccountsFilterLamports(
                    gt=1_000_000_000_000  # > 1000 SOL in lamports
                )
            )
        ],
    )
}
```

## Data Slicing

Reduce bandwidth by requesting only specific byte ranges of account data:

```python
# Only first 40 bytes (discriminator + first key field)
accounts_data_slice=[
    SubscribeRequestAccountsDataSlice(offset=0, length=40)
]
```

Multiple slices are supported — you get concatenated results.

## Slot Filters

```python
slots={
    "slot_updates": SubscribeRequestFilterSlots(
        filter_by_commitment=True,
    )
}
```

Slot status values: `PROCESSED`, `CONFIRMED`, `FINALIZED`, `FIRST_SHRED_RECEIVED`, `COMPLETED`, `CREATED_BANK`, `DEAD`.

## Block and Block Meta Filters

```python
# Full blocks (high bandwidth)
blocks={
    "full_blocks": SubscribeRequestFilterBlocks(
        account_include=["ProgramId..."],  # optional: only blocks with this program
        include_transactions=True,
        include_accounts=False,
        include_entries=False,
    )
}

# Block metadata only (low bandwidth)
blocks_meta={
    "block_meta": SubscribeRequestFilterBlocksMeta()
}
```

## Multiple Named Filters

Use different labels to multiplex subscriptions on one connection:

```python
request = SubscribeRequest(
    transactions={
        "pumpfun": SubscribeRequestFilterTransactions(
            account_include=["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"],
            vote=False, failed=False,
        ),
        "whales": SubscribeRequestFilterTransactions(
            account_include=["Whale1...", "Whale2..."],
            vote=False, failed=False,
        ),
    },
    accounts={
        "pools": SubscribeRequestFilterAccounts(
            account=["Pool1...", "Pool2..."],
        ),
    },
    commitment=CommitmentLevel.PROCESSED,
)

# In the response, update.filters tells you which matched: ["pumpfun"], ["whales"], ["pools"]
```

## Historical Replay

Resume from a specific slot (useful after disconnection):

```python
request = SubscribeRequest(
    transactions={...},
    from_slot=last_seen_slot - 32,  # subtract for reorg safety
)
```

Replay depth varies by provider: Shyft ~150 slots, QuickNode ~3000 slots, Helius ~24 hours.
