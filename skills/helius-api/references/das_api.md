# Helius DAS API — Field Reference

## Base URL

```
POST https://mainnet.helius-rpc.com/?api-key=YOUR_KEY
Content-Type: application/json
```

All DAS methods use JSON-RPC 2.0. Cost: 10 credits per call.

## Asset Object (Canonical Response)

Every DAS method returns assets in this structure:

```json
{
  "interface": "FungibleToken",
  "id": "So11111111111111111111111111111111111111112",
  "content": {
    "json_uri": "https://...",
    "files": [{"uri": "...", "cdn_uri": "...", "mime": "image/png"}],
    "metadata": {
      "name": "Wrapped SOL",
      "symbol": "SOL",
      "description": "...",
      "token_standard": "Fungible",
      "attributes": [{"trait_type": "...", "value": "..."}]
    },
    "links": {"image": "...", "external_url": "..."}
  },
  "authorities": [{"address": "...", "scopes": ["full"]}],
  "compression": {
    "compressed": false,
    "eligible": false,
    "data_hash": "", "creator_hash": "", "asset_hash": "",
    "tree": "", "seq": 0, "leaf_id": 0
  },
  "grouping": [{"group_key": "collection", "group_value": "..."}],
  "royalty": {
    "royalty_model": "creators",
    "percent": 0.0,
    "basis_points": 0,
    "primary_sale_happened": true,
    "locked": false
  },
  "creators": [{"address": "...", "share": 100, "verified": true}],
  "ownership": {
    "owner": "...",
    "frozen": false,
    "delegated": false,
    "delegate": null,
    "ownership_model": "single"
  },
  "supply": {
    "print_max_supply": 0,
    "print_current_supply": 0,
    "edition_nonce": null
  },
  "token_info": {
    "supply": 1000000000,
    "decimals": 9,
    "token_program": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "mint_authority": "...",
    "freeze_authority": "..."
  },
  "mutable": true,
  "burnt": false
}
```

## Interface Types

| Value | Description |
|-------|-------------|
| `FungibleToken` | SPL tokens |
| `FungibleAsset` | SPL tokens with metadata |
| `V1_NFT` | Metaplex v1 NFT |
| `V2_NFT` | Metaplex v2 NFT |
| `ProgrammableNFT` | pNFT (royalty-enforced) |
| `LEGACY_NFT` | Older format |
| `V1_PRINT` | Edition print |

## Method Details

### getAsset

```json
{
  "method": "getAsset",
  "params": {
    "id": "MINT_ADDRESS",
    "options": {
      "showFungible": true,
      "showCollectionMetadata": false,
      "showInscription": false,
      "showUnverifiedCollections": false
    }
  }
}
```

### getAssetsByOwner

```json
{
  "method": "getAssetsByOwner",
  "params": {
    "ownerAddress": "WALLET_ADDRESS",
    "page": 1,
    "limit": 100,
    "sortBy": {"sortBy": "recent_action", "sortDirection": "desc"},
    "displayOptions": {
      "showFungible": true,
      "showNativeBalance": true,
      "showZeroBalance": false
    }
  }
}
```

Response: `{ "total": 42, "limit": 100, "page": 1, "items": [Asset, ...] }`

### getAssetBatch

```json
{
  "method": "getAssetBatch",
  "params": {
    "ids": ["MINT1", "MINT2", "MINT3"]
  }
}
```

Up to 1,000 assets per call. Same cost as single getAsset (10 credits).

### searchAssets

```json
{
  "method": "searchAssets",
  "params": {
    "ownerAddress": "WALLET",
    "tokenType": "fungible",
    "compressed": false,
    "page": 1,
    "limit": 50
  }
}
```

Filter options: `tokenType` (fungible/nonFungible/all), `compressed`, `burnt`, `frozen`, `interface`, `grouping`.

### getTokenAccounts

```json
{
  "method": "getTokenAccounts",
  "params": {
    "owner": "WALLET_ADDRESS",
    "options": {"showZeroBalance": false}
  }
}
```

Or by mint: `{"mint": "TOKEN_MINT_ADDRESS"}` to find all holders.

## Pagination

Two modes:

**Offset-based** (simpler, max 1000 items):
```json
{"page": 1, "limit": 100}
```

**Cursor-based** (for large datasets):
```json
{"before": "cursor_string", "after": "cursor_string", "limit": 100}
```

Sort options: `created`, `recent_action`, `updated`, `none`.

## Important Notes

- Price data in `getAsset` is cached (600s TTL), only for top 10k tokens by volume
- `getAssetsByOwner` with `showFungible: true` is the fastest way to get a wallet's token portfolio
- `getTokenAccounts` with `mint` parameter is how you query all holders of a token
- Compressed NFT operations require `getAssetProof` for transfer/burn operations
- `getSignaturesForAsset` provides transaction history for compressed NFTs (not available via standard RPC)
