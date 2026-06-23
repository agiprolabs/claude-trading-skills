# Polymarket — Settlement, Operations & Constraints

---

## Settlement source — weather markets

Polymarket weather markets resolve via **Weather Underground** ("History" tab).

Key differences from Kalshi:
- **Clock:** local clock **with DST**, midnight-to-midnight (Kalshi uses LST, no DST)
- **Station:** Polymarket uses WU's metro mapping (e.g. KLGA for NYC); Kalshi uses KNYC
- These diverge by hours and occasionally by the resolved high/low — do not assume cross-venue settlement equivalence

For cross-venue settlement details see `kalshi-weather-markets`.

---

## Truth-source priority (scoring/backtesting)

When settling or scoring Polymarket weather outcomes:

1. **IEM METAR** (0.0–0.3°C MAE) — most accurate, use as ground truth when available
2. **Weather Underground API** — official resolution source for Polymarket, but has data quality issues
3. **Open-Meteo** — fallback only; not suitable as primary settlement source

---

## Known-bad WU dates

WU history has returned wrong or missing data on specific dates. Maintain a hardcoded bad-date set and a manual-override path:

```python
WU_BAD_DATES = {
    "2026-03-08",
    "2026-03-19",
    "2026-04-18",
}
# Check before trusting a WU response; fall back to IEM on hit
```

Add to this set as new bad dates are discovered. The per-city station mapping for Polymarket is **unconfirmed** — verify against each market's contract spec before trusting settlement fidelity.

---

## UMA optimistic oracle (dispute resolution)

After market close, the proposed resolution is published on-chain. During the challenge window, UMA token holders can dispute. If disputed:

1. Resolution goes to a **UMA token-holder vote** (the optimistic oracle)
2. Resolution can diverge from what Polymarket's operator would have settled
3. Settlement timeline extends by days to weeks during a dispute

This is a real risk when hedging cross-venue (Kalshi settles under CFTC/CCP rules with no token-holder vote).

---

## On-chain redemption

Winning tokens are **not auto-swept**. After a market resolves YES:

```python
# Option A: use py-clob-client if it exposes redemption
client.redeem_positions(condition_id=..., amounts=[...])

# Option B: direct CTF contract call via web3.py
from web3 import Web3
w3 = Web3(Web3.HTTPProvider(os.environ["POLYGON_RPC_URL"]))
ctf = w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)
ctf.functions.redeemPositions(
    collateral_token,   # USDC.e address
    parent_collection_id,
    condition_id,
    index_sets,         # [1] for YES, [2] for NO
).transact({"from": wallet_address})
```

Check live SDK docs — `redeemPositions` signature and index set encoding must match the CTF contract version Polymarket uses.

---

## Geo / KYC constraint

US persons are **blocked** from Polymarket by ToS and geo-IP.

- API calls from US IP addresses typically require a **SOCKS5 proxy** from an allowed jurisdiction
- Use an env-var toggle pattern:

```python
proxies = None
if os.environ.get("USE_PROXY"):
    proxies = {"https://": os.environ["SOCKS5_PROXY_URL"]}
# Pass proxies= to httpx.Client or configure in py-clob-client
```

- Never hardcode proxy addresses
- This constraint — combined with on-chain capital lockup and USDC/USD friction — is the primary reason Kalshi↔Polymarket arbitrage is not executable at retail scale by a single US legal entity

---

## Two-exchange host segregation

Polymarket (international, on-chain Polygon) and Kalshi (US regulated CFTC-CCP) are **legally and operationally separate**:

- Different collateral (USDC on-chain vs. USD at Kalshi's clearing partner)
- Different auth (EIP-712 wallet vs. RSA-PSS key)
- Different settlement (WU local-clock+DST vs. NWS CLI LST)
- Different dispute paths (UMA vs. CFTC)

Any system touching both must segment credentials, capital, and settlement logic cleanly. Do not share a single order-management layer across venues without explicit venue tagging on every object.

---

## Cross-references

- `kalshi-api` — Kalshi auth, REST host, order schema, WebSocket
- `kalshi-weather-markets` — WU vs NWS/CLI DST/LST divergence, station mapping, settlement rounding
- `prediction-market-strategy` — Strategy, sizing, and backtesting methodology across venues
