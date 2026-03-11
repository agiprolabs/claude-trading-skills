# Solana MEV Mechanics

## Solana Block Production

### Leader Schedule

Solana uses a rotating leader schedule. One validator is the "leader" for each slot (~400ms). The leader:
- Receives transactions from the network
- Orders them into a block
- Streams the block to the cluster via Turbine

The leader schedule is deterministic and known **2 epochs ahead** (~4 days). This means searchers know exactly which validator will produce each block, enabling targeted strategies.

### Slot Timing

- **Slot duration**: ~400ms (target)
- **Actual slot time**: 400-600ms depending on network load
- **Transactions per slot**: ~2,000-4,000 (theoretical max much higher)
- **Finality**: ~6.4 seconds (2/3 stake confirmation), but for MEV purposes, slot inclusion is what matters

### Transaction Flow (Standard)

```
User Wallet → RPC Node → TPU (Transaction Processing Unit) → Leader Validator → Block
                ↓
        (Forwarded to other validators for redundancy)
```

The TPU accepts transactions via UDP (QUIC since v1.15). There is no public mempool — transactions are forwarded directly to the current and upcoming leaders.

**However**, transactions are observable:
- RPC nodes forward to multiple leaders for reliability
- Jito block engine receives transactions from RPC infrastructure
- Validators can inspect incoming transactions before ordering

## Jito Block Engine

### Overview

Jito Labs operates a modified Solana validator client that adds an auction mechanism for transaction ordering. As of early 2025, approximately 85-90% of Solana validators run the Jito-modified client.

### How It Works

```
Searcher → Jito Block Engine → Jito-Modified Validator → Block

1. Searcher identifies MEV opportunity
2. Searcher constructs a "bundle" (ordered list of transactions)
3. Searcher submits bundle to Jito block engine with a SOL tip
4. Block engine validates the bundle (simulates execution)
5. Block engine forwards bundle to the current leader (if running Jito client)
6. Leader includes the bundle atomically in the block
7. Validator receives the tip
```

### Bundle Properties

- **Atomic execution**: All transactions in a bundle execute or none do
- **Ordered**: Transactions execute in the specified order within the bundle
- **Priority**: Higher tips get priority placement in the block
- **Size limit**: Up to 5 transactions per bundle
- **Simulation**: Block engine simulates before forwarding; reverted bundles are discarded

### Tip Mechanics

Tips are paid via a special Jito tip program. The tip transaction is included in the bundle:

```
Bundle = [
    tx_1 (front-run),
    tx_2 (victim's transaction),  # or reference to it
    tx_3 (back-run),
    tx_4 (tip to Jito: sendSOL to tip account)
]
```

**Tip distribution:**
- 100% of the tip goes to the validator producing the block
- Jito Labs charges no fee on tips (revenue from other services)

**Typical tip amounts (as of 2025):**
- Low priority: 1,000 - 10,000 lamports (0.000001 - 0.00001 SOL)
- Normal: 100,000 - 1,000,000 lamports (0.0001 - 0.001 SOL)
- High priority: 1,000,000 - 10,000,000 lamports (0.001 - 0.01 SOL)
- Competitive MEV: 10,000,000+ lamports (0.01+ SOL)

### Jito Endpoints

- **Mainnet block engine**: `https://mainnet.block-engine.jito.wtf`
- **Bundle submission**: `POST /api/v1/bundles` with `sendBundle` JSON-RPC method
- **Bundle status**: `POST /api/v1/bundles` with `getBundleStatuses` method
- **Tip accounts**: Rotate periodically; fetch via `getTipAccounts` method

## MEV Supply Chain on Solana

### Participants

1. **Users**: Submit swaps, provide liquidity, borrow/lend
2. **Searchers**: Identify and capture MEV opportunities. Run co-located infrastructure with sub-millisecond latency
3. **Block Engine (Jito)**: Auction platform connecting searchers to validators
4. **Validators**: Produce blocks, earn tips from MEV bundles
5. **Protocols**: DEXes, lending platforms — where MEV opportunities originate

### Value Flow

```
MEV Opportunity (user's swap creates arbitrage or sandwich opportunity)
    ↓
Searcher extracts value:
    gross_profit = extracted_value
    net_profit   = extracted_value - jito_tip - tx_fees - infrastructure_cost
    ↓
Jito tip to validator:
    validator_revenue = jito_tip
    ↓
Cost to user:
    user_cost = worse execution price (implicit cost, not a visible fee)
```

### MEV Extraction Economics

For a sandwich attack to be profitable:

```
sandwich_profit = victim_slippage_captured - (2 * tx_fee) - jito_tip - capital_cost

Where:
    victim_slippage_captured ≈ victim_trade_size * (slippage_bps / 10000) * capture_rate
    capture_rate ≈ 0.3 to 0.7 (depends on pool depth and attacker's capital)
    tx_fee ≈ 0.000005 SOL per transaction (5000 lamports base fee)
    jito_tip ≈ 0.0001 to 0.01 SOL (depends on competition)
    capital_cost ≈ minimal for atomic bundles (no holding risk)
```

**Minimum viable sandwich** (rough estimate):
- Trade size: > 0.5 SOL with > 100bps slippage in an illiquid pool
- Or: > 5 SOL with > 50bps slippage in a moderately liquid pool
- Below these thresholds, gas + tips exceed potential profit

## Transaction Flow Paths and MEV Visibility

### Path 1: Public RPC (Most Vulnerable)

```
User → Public RPC → Multiple Leaders (via QUIC)
                  → Jito Block Engine (intercepted)
```

Transactions are visible to the Jito block engine and any searcher connected to it. This is the most MEV-exposed path.

### Path 2: Private/Staked RPC (Less Visible)

```
User → Private RPC (Helius/QuickNode) → Current Leader Only
```

Staked connections can send directly to the leader. Fewer intermediaries see the transaction. Not immune to MEV but reduces the observation window.

### Path 3: Jito Bundle (User-Controlled Ordering)

```
User → Jito Block Engine → Leader
     (user IS the searcher, controlling tx order)
```

By submitting your own bundle, you control the ordering. A searcher cannot insert transactions into your bundle. This is the strongest MEV protection available.

### Path 4: Direct TPU (Requires Infrastructure)

```
User → Leader's TPU directly (UDP/QUIC)
```

Requires knowing the leader's TPU address and having network proximity. Used by professional trading firms. Minimizes intermediary visibility.

## Historical MEV on Solana

MEV on Solana has grown significantly:

- **2022-2023**: Early MEV, mostly arbitrage. Limited sandwich attacks due to lower DEX volume
- **2024**: Explosive growth with meme coin trading surge. Sandwich attacks became routine on Jupiter and Raydium swaps. Jito tips exceeded $1M/day during peak periods
- **2025**: MEV infrastructure matured. Protection mechanisms improved (Jupiter dynamic slippage, private RPCs). MEV remains significant but users have more tools to mitigate it

**Key metrics to track:**
- Jito bundle volume (indicates MEV activity level)
- Average Jito tip (indicates MEV competition/profitability)
- Sandwich attack frequency (via on-chain analysis)
- Protected vs unprotected transaction ratio
