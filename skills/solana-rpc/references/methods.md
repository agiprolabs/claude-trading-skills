# Solana RPC — Method Reference

All methods use POST to the RPC endpoint with JSON-RPC 2.0 format.

## Request Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "METHOD_NAME",
  "params": [/* method-specific */]
}
```

## Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": { /* method-specific */ }
}
```

On error:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": { "code": -32600, "message": "Invalid request" }
}
```

---

## Account Methods

### getBalance
Returns SOL balance in lamports (1 SOL = 1,000,000,000 lamports).
- **Params**: `[pubkey, {commitment}]`
- **Result**: `{ context: { slot }, value: lamports }`

### getAccountInfo
Returns all account data including owner program, data, and executable flag.
- **Params**: `[pubkey, {encoding, commitment, dataSlice}]`
- **Encodings**: `base58` (slow), `base64`, `base64+zstd`, `jsonParsed`
- **Result**: `{ context, value: { data, executable, lamports, owner, rentEpoch } }`
- **Note**: `jsonParsed` only works for known programs (Token, System, etc.)

### getMultipleAccounts
Batch lookup for up to 100 accounts.
- **Params**: `[[pubkey1, pubkey2, ...], {encoding, commitment}]`
- **Result**: `{ context, value: [account1, account2, ...] }`

---

## Token Methods

### getTokenAccountsByOwner
All SPL token accounts owned by a wallet.
- **Params**: `[owner_pubkey, {mint | programId}, {encoding, commitment}]`
- **Filter by mint**: `{"mint": "TOKEN_MINT"}` — accounts for a specific token
- **Filter by program**: `{"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}` — all SPL tokens

### getTokenLargestAccounts
Top 20 largest holders of a token.
- **Params**: `[mint_pubkey, {commitment}]`
- **Result**: `{ value: [{ address, amount, decimals, uiAmount, uiAmountString }] }`

### getTokenSupply
Total supply of a token.
- **Params**: `[mint_pubkey, {commitment}]`
- **Result**: `{ value: { amount, decimals, uiAmount, uiAmountString } }`

### getTokenAccountBalance
Balance of a specific token account.
- **Params**: `[token_account_pubkey, {commitment}]`
- **Result**: `{ value: { amount, decimals, uiAmount } }`

---

## Transaction Methods

### getTransaction
Full transaction data by signature.
- **Params**: `[signature, {encoding, commitment, maxSupportedTransactionVersion}]`
- **Note**: Must set `maxSupportedTransactionVersion: 0` for versioned transactions.

### getSignaturesForAddress
Recent signatures involving an address.
- **Params**: `[pubkey, {limit, before, until, commitment}]`
- **Result**: `[{ signature, slot, err, memo, blockTime, confirmationStatus }]`
- **Limit**: Max 1000 per call. Use `before` for pagination.

### getSignatureStatuses
Check confirmation status of transactions.
- **Params**: `[[sig1, sig2, ...], {searchTransactionHistory}]`
- **Result**: `{ value: [{ slot, confirmations, err, confirmationStatus } | null] }`

### sendTransaction
Submit a signed transaction.
- **Params**: `[base64_tx, {encoding, skipPreflight, preflightCommitment, maxRetries, minContextSlot}]`
- **Result**: Transaction signature string
- **Note**: `skipPreflight: true` skips simulation (faster but riskier).

### simulateTransaction
Simulate without submitting.
- **Params**: `[base64_tx, {encoding, sigVerify, commitment, replaceRecentBlockhash}]`
- **Result**: `{ err, logs, accounts, unitsConsumed, returnData }`

---

## Block & Slot Methods

### getSlot
Current slot number.
- **Params**: `[{commitment}]`

### getBlock
Full block data.
- **Params**: `[slot, {encoding, transactionDetails, rewards, commitment, maxSupportedTransactionVersion}]`
- **transactionDetails**: `full`, `signatures`, `accounts`, `none`

### getLatestBlockhash
Current blockhash for transaction building.
- **Params**: `[{commitment}]`
- **Result**: `{ value: { blockhash, lastValidBlockHeight } }`

### isBlockhashValid
Check if a blockhash is still valid.
- **Params**: `[blockhash, {commitment}]`

### getBlockHeight
Current block height.
- **Params**: `[{commitment}]`

---

## Program Methods

### getProgramAccounts
All accounts owned by a program.
- **Params**: `[program_pubkey, {encoding, commitment, filters, dataSlice, withContext}]`
- **Filters**: `[{ dataSize: N }, { memcmp: { offset, bytes } }]`
- **Warning**: Without filters, this can return millions of accounts. Always filter.

### getRecentPrioritizationFees
Priority fee estimates from recent blocks.
- **Params**: `[[account_pubkey1, ...]]`
- **Result**: `[{ slot, prioritizationFee }]` — fee in micro-lamports per compute unit

### getMinimumBalanceForRentExemption
SOL needed to keep an account alive.
- **Params**: `[data_length_bytes]`
- **Result**: Lamports required

---

## Subscription Methods (WebSocket)

Connect via WebSocket (`wss://` version of RPC URL).

### accountSubscribe / accountUnsubscribe
Watch for account data changes.
- **Params**: `[pubkey, {encoding, commitment}]`

### logsSubscribe / logsUnsubscribe
Watch for transaction logs.
- **Params**: `[{mentions: [pubkey]} | "all" | "allWithVotes", {commitment}]`

### signatureSubscribe / signatureUnsubscribe
Watch for transaction confirmation.
- **Params**: `[signature, {commitment}]`

### slotSubscribe / slotUnsubscribe
Watch for slot changes.
- **Params**: `[]`

---

## Batch Requests

Send multiple calls in one HTTP request:

```json
[
  {"jsonrpc":"2.0","id":0,"method":"getBalance","params":["ADDR1"]},
  {"jsonrpc":"2.0","id":1,"method":"getBalance","params":["ADDR2"]},
  {"jsonrpc":"2.0","id":2,"method":"getBalance","params":["ADDR3"]}
]
```

Response is an array in the same order. Most providers support up to 100 calls per batch.
