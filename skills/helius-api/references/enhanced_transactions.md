# Helius Enhanced Transactions API — Reference

## Base URL

```
https://api-mainnet.helius-rpc.com/v0/
```

Note: This is a REST API (not JSON-RPC). Cost: 100 credits per call.

## Parse Transactions (Batch)

```
POST /v0/transactions?api-key=YOUR_KEY
```

```json
{
  "transactions": ["sig1", "sig2"],
  "commitment": "finalized"
}
```

Max 100 signatures per batch.

## Get Parsed History by Address

```
GET /v0/addresses/{address}/transactions?api-key=YOUR_KEY
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | 1-100 results |
| `before-signature` | string | Paginate backward |
| `after-signature` | string | Paginate forward |
| `type` | string | Filter by TransactionType |
| `source` | string | Filter by TransactionSource |
| `commitment` | string | confirmed or finalized |
| `sort-order` | string | asc or desc |

## EnhancedTransaction Response

```json
{
  "signature": "5K2b...",
  "description": "User swapped 1 SOL for 150 USDC on Jupiter",
  "type": "SWAP",
  "source": "JUPITER",
  "fee": 5000,
  "feePayer": "WalletAddress...",
  "slot": 250000000,
  "timestamp": 1700000000,
  "nativeTransfers": [
    {"fromUserAccount": "A", "toUserAccount": "B", "amount": 1000000000}
  ],
  "tokenTransfers": [
    {
      "fromUserAccount": "A",
      "toUserAccount": "B",
      "fromTokenAccount": "ATA1",
      "toTokenAccount": "ATA2",
      "tokenAmount": 150.0,
      "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
      "tokenStandard": "Fungible"
    }
  ],
  "accountData": [
    {"account": "addr", "nativeBalanceChange": -1005000, "tokenBalanceChanges": [...]}
  ],
  "transactionError": null,
  "instructions": [...],
  "events": {
    "swap": {
      "nativeInput": {"account": "...", "amount": "1000000000"},
      "nativeOutput": null,
      "tokenInputs": [],
      "tokenOutputs": [{"userAccount": "...", "tokenAccount": "...", "mint": "...", "rawTokenAmount": {"tokenAmount": "150000000", "decimals": 6}}],
      "tokenFees": [],
      "nativeFees": [],
      "innerSwaps": [...]
    }
  }
}
```

## Transaction Types (Key Categories)

### DeFi / Trading
| Type | Description |
|------|-------------|
| `SWAP` | DEX swap (any aggregator or AMM) |
| `ADD_LIQUIDITY` | Add to LP pool |
| `REMOVE_LIQUIDITY` | Remove from LP pool |
| `DEPOSIT` | Deposit to protocol |
| `WITHDRAW` | Withdraw from protocol |
| `BORROW_FOX` | Borrow operations |
| `REPAY_LOAN` | Loan repayment |
| `LIQUIDATE` | Liquidation |
| `CREATE_ORDER` | Limit order creation |
| `CANCEL_ORDER` | Limit order cancellation |
| `FILL_ORDER` | Limit order filled |

### Token Operations
| Type | Description |
|------|-------------|
| `TRANSFER` | Token or SOL transfer |
| `MINT_TO` | Token minting |
| `BURN` | Token burning |
| `APPROVE` | Token delegation |
| `REVOKE` | Revoke delegation |

### NFT
| Type | Description |
|------|-------------|
| `NFT_SALE` | NFT sold on marketplace |
| `NFT_MINT` | NFT minted |
| `NFT_LISTING` | NFT listed for sale |
| `NFT_BID` | Bid placed on NFT |
| `NFT_CANCEL_LISTING` | Listing cancelled |
| `COMPRESSED_NFT_MINT` | Compressed NFT minted |
| `COMPRESSED_NFT_TRANSFER` | Compressed NFT transferred |

### Staking
| Type | Description |
|------|-------------|
| `STAKE_SOL` | Stake SOL |
| `UNSTAKE_SOL` | Unstake SOL |
| `CLAIM_REWARDS` | Claim staking rewards |

### System
| Type | Description |
|------|-------------|
| `UNKNOWN` | Unrecognized transaction type |
| `UPGRADE_PROGRAM_INSTRUCTION` | Program upgrade |

## Transaction Sources

### DEXes & DeFi
`JUPITER`, `RAYDIUM`, `ORCA`, `METEORA`, `SABER`, `MERCURIAL`, `MARINADE`, `ALDRIN`, `CREMA`, `LIFINITY`, `CYKURA`, `ORCA_WHIRLPOOLS`, `PHOENIX`

### NFT Marketplaces
`MAGIC_EDEN`, `TENSOR`, `HYPERSPACE`, `SOLANART`, `EXCHANGE_ART`, `DIGITAL_EYES`, `FORM_FUNCTION`, `HADESWAP`, `CORAL_CUBE`

### Protocols & Programs
`METAPLEX`, `CANDY_MACHINE_V1`, `CANDY_MACHINE_V2`, `CANDY_MACHINE_V3`, `BUBBLEGUM`, `ANCHOR`, `SYSTEM_PROGRAM`, `STAKE_PROGRAM`

### Ecosystem
`PHANTOM`, `COINBASE`, `OPENSEA`, `STEPN`, `SHARKY_FI`, `SQUADS`

`UNKNOWN` for unrecognized sources.

## Using Enhanced Transactions for Wallet Profiling

Common patterns for analyzing a wallet:

```python
# 1. Get all swaps for a wallet
swaps = get_transactions(wallet, type="SWAP")
# Analyze: DEX preference, token diversity, trade sizes, frequency

# 2. Get all transfers
transfers = get_transactions(wallet, type="TRANSFER")
# Analyze: fund flows, counterparties, deposit/withdrawal patterns

# 3. Compute PnL per token from tokenTransfers
# Group tokenTransfers by mint, sum inflows and outflows

# 4. Identify trading style from timing
# Frequency, hold times (time between buy and sell of same token)
```

## Events Object

The `events` field provides structured data for specific transaction types:

### Swap Event
```json
{
  "swap": {
    "nativeInput": {"account": "...", "amount": "1000000000"},
    "nativeOutput": null,
    "tokenInputs": [],
    "tokenOutputs": [{"mint": "...", "rawTokenAmount": {"tokenAmount": "150", "decimals": 6}}],
    "innerSwaps": [{"tokenInputs": [...], "tokenOutputs": [...], "programInfo": {...}}]
  }
}
```

### NFT Event
```json
{
  "nft": {
    "description": "...",
    "type": "NFT_SALE",
    "source": "MAGIC_EDEN",
    "amount": 5000000000,
    "fee": 250000000,
    "buyer": "...",
    "seller": "...",
    "nfts": [{"mint": "...", "tokenStandard": "NonFungible"}]
  }
}
```
