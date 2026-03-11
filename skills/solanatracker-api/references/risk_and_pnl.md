# SolanaTracker — Risk Scoring & PnL Calculation

## Risk Score

SolanaTracker assigns each token a risk score from **1 (highest risk) to 10 (safest)**, evaluating multiple on-chain and metadata factors.

### Risk Factors Evaluated

| Factor | Level | Description |
|--------|-------|-------------|
| Mint authority enabled | `danger` | Token supply can be increased |
| Freeze authority enabled | `danger` | Tokens can be frozen in wallets |
| Top 10 holders own >50% | `warn` | High concentration risk |
| Top 10 holders own >80% | `danger` | Extreme concentration |
| Low holder count (<100) | `warn` | Limited distribution |
| No social media links | `warn` | Possible low-effort token |
| Incomplete metadata | `warn` | Missing name, symbol, or image |
| Bundler activity detected | `warn` | Coordinated buy patterns |
| High sniper concentration | `warn` | Early buyers hold large % |
| Developer holds >10% | `warn` | Creator retention risk |
| Low liquidity (<$10K) | `danger` | Difficult to exit |
| Not Jupiter verified | `info` | Not vetted by Jupiter |

### Risk Response Schema

```json
{
  "risk": {
    "score": 7,
    "rugged": false,
    "jupiterVerified": true,
    "risks": [
      {
        "name": "Top 10 holders own 45%",
        "description": "High holder concentration",
        "level": "warn",
        "score": -1
      },
      {
        "name": "Freeze authority enabled",
        "description": "Token accounts can be frozen",
        "level": "danger",
        "score": -2
      }
    ]
  }
}
```

### Using Risk Scores

```python
def assess_risk(token_data: dict) -> str:
    """Classify token risk level from SolanaTracker data."""
    risk = token_data.get("risk", {})
    score = risk.get("score", 0)
    rugged = risk.get("rugged", False)

    if rugged:
        return "RUGGED — avoid"
    if score >= 8:
        return "LOW RISK"
    if score >= 5:
        return "MODERATE RISK"
    if score >= 3:
        return "HIGH RISK"
    return "EXTREME RISK"

def has_danger_flags(token_data: dict) -> list[str]:
    """Extract danger-level risk flags."""
    risks = token_data.get("risk", {}).get("risks", [])
    return [r["name"] for r in risks if r.get("level") == "danger"]
```

## PnL Calculation

SolanaTracker tracks realized and unrealized PnL per wallet across all Solana tokens.

### PnL Summary Fields

| Field | Type | Description |
|-------|------|-------------|
| `realized` | float | Profit/loss from closed positions (SOL) |
| `unrealized` | float | Open position value vs. cost basis (SOL) |
| `total` | float | realized + unrealized |
| `totalInvested` | float | Total SOL spent on buys |
| `averageBuyAmount` | float | Mean buy transaction size |
| `totalWins` | int | Positions closed in profit |
| `totalLosses` | int | Positions closed at a loss |
| `winPercentage` | float | Win rate (0-100) |
| `lossPercentage` | float | Loss rate (0-100) |

### Token-Level PnL

Each token in the breakdown includes:

| Field | Type | Description |
|-------|------|-------------|
| `tokenAddress` | string | Token mint |
| `totalBought` | float | Total tokens bought |
| `totalSold` | float | Total tokens sold |
| `totalBuyValue` | float | Total SOL spent buying |
| `totalSellValue` | float | Total SOL received selling |
| `realized` | float | Sell value - buy value for sold tokens |
| `unrealized` | float | Current value of held tokens - cost basis |
| `holdingAmount` | float | Currently held tokens |
| `holdingValue` | float | Current value of holdings |

### PnL Analysis Patterns

```python
def classify_trader(pnl_summary: dict) -> str:
    """Classify trader skill level from PnL data."""
    win_pct = pnl_summary.get("winPercentage", 0)
    total = pnl_summary.get("total", 0)
    invested = pnl_summary.get("totalInvested", 0)
    trades = pnl_summary.get("totalWins", 0) + pnl_summary.get("totalLosses", 0)

    if trades < 10:
        return "INSUFFICIENT DATA"

    roi = total / invested if invested > 0 else 0

    if win_pct >= 60 and roi > 0.5:
        return "STRONG PERFORMER"
    if win_pct >= 50 and roi > 0:
        return "PROFITABLE"
    if win_pct >= 40:
        return "MARGINAL"
    return "UNPROFITABLE"
```

### Historical PnL

With `showHistoricPnL=true`, the response includes:
- `pnl_1d` — Last 24 hours
- `pnl_7d` — Last 7 days
- `pnl_30d` — Last 30 days

Each interval has the same summary structure, enabling trend analysis:

```python
def pnl_trend(pnl: dict) -> str:
    """Check if trader is improving or declining."""
    d1 = pnl.get("pnl_1d", {}).get("total", 0)
    d7 = pnl.get("pnl_7d", {}).get("total", 0)
    d30 = pnl.get("pnl_30d", {}).get("total", 0)

    if d1 > 0 and d7 > 0 and d30 > 0:
        return "CONSISTENTLY PROFITABLE"
    if d1 > 0 and d7 > 0:
        return "RECENTLY PROFITABLE"
    if d1 < 0 and d7 < 0:
        return "DECLINING"
    return "MIXED"
```

## First Buyers Analysis

The `/first-buyers/{token}` endpoint combines early entry detection with PnL:

```python
def analyze_first_buyers(token: str, api_key: str) -> dict:
    """Analyze first buyers and their outcomes."""
    resp = httpx.get(
        f"https://data.solanatracker.io/first-buyers/{token}",
        headers={"x-api-key": api_key},
    )
    buyers = resp.json()

    profitable = sum(1 for b in buyers if b.get("realized", 0) > 0)
    total = len(buyers)

    return {
        "total_first_buyers": total,
        "profitable_count": profitable,
        "profitable_pct": round(profitable / total * 100, 1) if total > 0 else 0,
        "still_holding": sum(1 for b in buyers if b.get("holdingAmount", 0) > 0),
        "total_realized": sum(b.get("realized", 0) for b in buyers),
    }
```

## Bundler Detection

Bundlers are wallets that use atomic bundles to execute coordinated buys (often at launch). The `/tokens/{token}/bundlers` endpoint identifies these:

```json
[
  {
    "wallet": "ADDR...",
    "bundleCount": 5,
    "totalBought": 15000000,
    "holdingAmount": 12000000,
    "holdingPercentage": 2.4
  }
]
```

High bundler concentration at launch is a risk signal — it suggests coordinated buying that may precede a dump.
