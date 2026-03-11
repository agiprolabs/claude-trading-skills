#!/usr/bin/env python3
"""Monitor DEX pool metrics over time and detect liquidity events.

Tracks TVL changes, volume trends, and new pool creation for a Solana token.
In demo mode, simulates a pool lifecycle from creation through maturity,
including liquidity addition, removal events, and volume spikes.

Usage:
    python scripts/pool_monitor.py <TOKEN_MINT> --interval 60
    python scripts/pool_monitor.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    None required (DexScreener API is free and keyless).
"""

import argparse
import math
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────

DEXSCREENER_BASE = "https://api.dexscreener.com"
REQUEST_TIMEOUT = 15.0

# Alert thresholds
TVL_DROP_ALERT_PCT = -15.0       # Alert if TVL drops more than 15%
TVL_SPIKE_ALERT_PCT = 50.0       # Alert if TVL spikes more than 50%
VOLUME_SPIKE_MULT = 3.0          # Alert if volume > 3x average
NEW_POOL_ALERT = True            # Alert on new pool detection


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class PoolSnapshot:
    """A point-in-time snapshot of pool metrics."""

    timestamp: float
    pool_address: str
    dex_name: str
    tvl_usd: float
    volume_1h: float
    volume_24h: float
    price_usd: float
    buys_1h: int
    sells_1h: int


@dataclass
class PoolAlert:
    """An alert generated from pool monitoring."""

    timestamp: float
    pool_address: str
    dex_name: str
    alert_type: str  # "tvl_drop", "tvl_spike", "volume_spike", "new_pool", "dead_pool"
    severity: str    # "critical", "warning", "info"
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class MonitorState:
    """Tracking state for a monitored pool."""

    pool_address: str
    dex_name: str
    snapshots: list[PoolSnapshot] = field(default_factory=list)
    alerts: list[PoolAlert] = field(default_factory=list)
    first_seen: float = 0.0
    last_tvl: float = 0.0
    avg_volume_1h: float = 0.0


# ── Alert Detection ────────────────────────────────────────────────


def detect_alerts(
    state: MonitorState, current: PoolSnapshot
) -> list[PoolAlert]:
    """Compare current snapshot against state to detect alerts.

    Checks for:
    - TVL drops exceeding threshold
    - TVL spikes exceeding threshold
    - Volume spikes vs rolling average
    - Dead pools (zero activity)

    Args:
        state: Current monitoring state for this pool.
        current: Latest pool snapshot.

    Returns:
        List of new alerts detected.
    """
    alerts: list[PoolAlert] = []

    if state.last_tvl > 0:
        tvl_change_pct = ((current.tvl_usd - state.last_tvl) / state.last_tvl) * 100

        # TVL drop alert
        if tvl_change_pct < TVL_DROP_ALERT_PCT:
            severity = "critical" if tvl_change_pct < -50 else "warning"
            alerts.append(PoolAlert(
                timestamp=current.timestamp,
                pool_address=current.pool_address,
                dex_name=current.dex_name,
                alert_type="tvl_drop",
                severity=severity,
                message=f"TVL dropped {tvl_change_pct:.1f}% "
                        f"(${state.last_tvl:,.0f} -> ${current.tvl_usd:,.0f})",
                details={
                    "previous_tvl": state.last_tvl,
                    "current_tvl": current.tvl_usd,
                    "change_pct": tvl_change_pct,
                },
            ))

        # TVL spike alert
        if tvl_change_pct > TVL_SPIKE_ALERT_PCT:
            alerts.append(PoolAlert(
                timestamp=current.timestamp,
                pool_address=current.pool_address,
                dex_name=current.dex_name,
                alert_type="tvl_spike",
                severity="info",
                message=f"TVL increased {tvl_change_pct:.1f}% "
                        f"(${state.last_tvl:,.0f} -> ${current.tvl_usd:,.0f})",
                details={
                    "previous_tvl": state.last_tvl,
                    "current_tvl": current.tvl_usd,
                    "change_pct": tvl_change_pct,
                },
            ))

    # Volume spike vs average
    if state.avg_volume_1h > 0 and current.volume_1h > 0:
        volume_mult = current.volume_1h / state.avg_volume_1h
        if volume_mult > VOLUME_SPIKE_MULT:
            alerts.append(PoolAlert(
                timestamp=current.timestamp,
                pool_address=current.pool_address,
                dex_name=current.dex_name,
                alert_type="volume_spike",
                severity="warning",
                message=f"Volume spike: {volume_mult:.1f}x average "
                        f"(${current.volume_1h:,.0f} vs avg ${state.avg_volume_1h:,.0f})",
                details={
                    "current_volume_1h": current.volume_1h,
                    "avg_volume_1h": state.avg_volume_1h,
                    "multiplier": volume_mult,
                },
            ))

    # Dead pool detection
    if (
        len(state.snapshots) >= 3
        and all(s.volume_1h == 0 for s in state.snapshots[-3:])
        and current.volume_1h == 0
    ):
        alerts.append(PoolAlert(
            timestamp=current.timestamp,
            pool_address=current.pool_address,
            dex_name=current.dex_name,
            alert_type="dead_pool",
            severity="warning",
            message="Pool has had zero volume for 3+ consecutive checks",
            details={"consecutive_zero_checks": len(state.snapshots)},
        ))

    return alerts


def update_state(state: MonitorState, snapshot: PoolSnapshot) -> None:
    """Update monitoring state with a new snapshot.

    Args:
        state: Current monitoring state to update.
        snapshot: New snapshot to incorporate.
    """
    state.snapshots.append(snapshot)
    state.last_tvl = snapshot.tvl_usd

    # Rolling average of 1h volume (last 10 snapshots)
    recent = state.snapshots[-10:]
    volumes = [s.volume_1h for s in recent if s.volume_1h > 0]
    state.avg_volume_1h = sum(volumes) / len(volumes) if volumes else 0.0


# ── Data Fetching ───────────────────────────────────────────────────


def fetch_pool_snapshots(token_mint: str) -> list[PoolSnapshot]:
    """Fetch current pool data from DexScreener and create snapshots.

    Args:
        token_mint: Solana token mint address.

    Returns:
        List of PoolSnapshot objects, one per pool.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    url = f"{DEXSCREENER_BASE}/tokens/v1/solana/{token_mint}"
    now = time.time()

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.get(url)
        resp.raise_for_status()
        raw_pools = resp.json()

    if not isinstance(raw_pools, list):
        return []

    snapshots: list[PoolSnapshot] = []
    for p in raw_pools:
        if p.get("chainId", "") != "solana":
            continue

        volume = p.get("volume") or {}
        liquidity = p.get("liquidity") or {}
        txns = p.get("txns") or {}
        txns_1h = txns.get("h1") or {}

        snapshots.append(PoolSnapshot(
            timestamp=now,
            pool_address=p.get("pairAddress", ""),
            dex_name=p.get("dexId", "unknown"),
            tvl_usd=float(liquidity.get("usd", 0) or 0),
            volume_1h=float(volume.get("h1", 0) or 0),
            volume_24h=float(volume.get("h24", 0) or 0),
            price_usd=float(p.get("priceUsd", 0) or 0),
            buys_1h=int(txns_1h.get("buys", 0) or 0),
            sells_1h=int(txns_1h.get("sells", 0) or 0),
        ))

    return snapshots


# ── Demo Simulation ─────────────────────────────────────────────────


def simulate_pool_lifecycle() -> list[tuple[float, list[PoolSnapshot]]]:
    """Simulate a token's pool lifecycle for demo mode.

    Simulates 20 time steps covering:
    - T0-T2: Pool creation on Raydium V4 (PumpFun graduation)
    - T3-T5: Early trading with high volume, TVL growth
    - T6-T8: Orca Whirlpool pool created (new pool event)
    - T9-T12: Stable period, normal trading
    - T13-T15: Liquidity removal event on Raydium (rug warning)
    - T16-T18: Volume dies on Raydium, moves to Orca
    - T19: Final state

    Returns:
        List of (timestamp, snapshots) tuples representing time steps.
    """
    random.seed(42)  # Reproducible demo
    base_time = time.time()
    steps: list[tuple[float, list[PoolSnapshot]]] = []

    # Pool lifecycle parameters
    raydium_tvl_curve = [
        12_000, 18_000, 35_000, 55_000, 80_000,  # Growth phase
        95_000, 100_000, 105_000, 110_000, 108_000,  # Stable
        105_000, 100_000, 95_000, 40_000, 25_000,  # Rug event
        15_000, 8_000, 5_000, 3_000, 2_000,  # Decline
    ]

    # Orca pool appears at step 6
    orca_tvl_curve = [
        0, 0, 0, 0, 0, 0,
        50_000, 65_000, 75_000, 80_000,  # Creation + growth
        85_000, 90_000, 95_000, 100_000, 110_000,  # Absorbs volume
        120_000, 130_000, 135_000, 140_000, 145_000,  # Dominant
    ]

    for step in range(20):
        t = base_time + step * 3600  # 1 hour between steps
        snapshots: list[PoolSnapshot] = []

        # Raydium V4 pool
        ray_tvl = raydium_tvl_curve[step]
        ray_vol_base = ray_tvl * random.uniform(0.3, 1.5)
        if step >= 13:
            ray_vol_base *= 0.2  # Volume dies after rug

        snapshots.append(PoolSnapshot(
            timestamp=t,
            pool_address="RayPool1111111111111111111111111111111111111",
            dex_name="raydium",
            tvl_usd=ray_tvl * random.uniform(0.95, 1.05),
            volume_1h=ray_vol_base * random.uniform(0.02, 0.08),
            volume_24h=ray_vol_base,
            price_usd=0.00042 * (1 + step * 0.02 + random.uniform(-0.05, 0.05)),
            buys_1h=int(random.uniform(10, 80)),
            sells_1h=int(random.uniform(8, 70)),
        ))

        # Orca Whirlpool (appears at step 6)
        orca_tvl = orca_tvl_curve[step]
        if orca_tvl > 0:
            orca_vol_base = orca_tvl * random.uniform(0.5, 2.0)
            snapshots.append(PoolSnapshot(
                timestamp=t,
                pool_address="OrcaPool2222222222222222222222222222222222222",
                dex_name="orca_whirlpool",
                tvl_usd=orca_tvl * random.uniform(0.95, 1.05),
                volume_1h=orca_vol_base * random.uniform(0.03, 0.08),
                volume_24h=orca_vol_base,
                price_usd=0.00042 * (1 + step * 0.02 + random.uniform(-0.05, 0.05)),
                buys_1h=int(random.uniform(15, 90)),
                sells_1h=int(random.uniform(12, 85)),
            ))

        steps.append((t, snapshots))

    return steps


# ── Display ─────────────────────────────────────────────────────────


def format_timestamp(ts: float) -> str:
    """Format a Unix timestamp to a readable string.

    Args:
        ts: Unix timestamp.

    Returns:
        Formatted time string.
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def print_snapshot_report(
    snapshots: list[PoolSnapshot], states: dict[str, MonitorState], step: int
) -> None:
    """Print a monitoring report for the current time step.

    Args:
        snapshots: Current pool snapshots.
        states: Monitoring states keyed by pool address.
        step: Current step number.
    """
    if not snapshots:
        print(f"  Step {step}: No pool data available")
        return

    ts = snapshots[0].timestamp
    print(f"\n{'─'*60}")
    print(f"  Step {step} | {format_timestamp(ts)}")
    print(f"{'─'*60}")

    total_tvl = 0.0
    total_vol = 0.0

    for snap in snapshots:
        total_tvl += snap.tvl_usd
        total_vol += snap.volume_1h

        state = states.get(snap.pool_address)
        tvl_change = ""
        if state and state.last_tvl > 0 and len(state.snapshots) > 0:
            prev = state.last_tvl
            change_pct = ((snap.tvl_usd - prev) / prev) * 100
            tvl_change = f" ({change_pct:+.1f}%)"

        print(
            f"  {snap.dex_name:20s} | "
            f"TVL: ${snap.tvl_usd:>10,.0f}{tvl_change:>10s} | "
            f"Vol(1h): ${snap.volume_1h:>8,.0f} | "
            f"Txns: {snap.buys_1h + snap.sells_1h:>4d}"
        )

    print(f"  {'':20s} | Total TVL: ${total_tvl:>10,.0f} | Total Vol: ${total_vol:>8,.0f}")


def print_alert(alert: PoolAlert) -> None:
    """Print a formatted alert message.

    Args:
        alert: PoolAlert to display.
    """
    severity_prefix = {
        "critical": "!! CRITICAL",
        "warning": "!  WARNING ",
        "info": "i  INFO    ",
    }
    prefix = severity_prefix.get(alert.severity, "   UNKNOWN ")
    print(f"\n  [{prefix}] {format_timestamp(alert.timestamp)}")
    print(f"  Pool: {alert.dex_name} ({alert.pool_address[:16]}...)")
    print(f"  Type: {alert.alert_type}")
    print(f"  {alert.message}")


def print_monitoring_summary(states: dict[str, MonitorState]) -> None:
    """Print final monitoring summary with all alerts.

    Args:
        states: All monitoring states.
    """
    all_alerts: list[PoolAlert] = []
    for state in states.values():
        all_alerts.extend(state.alerts)

    print(f"\n{'='*60}")
    print(f"  MONITORING SUMMARY")
    print(f"{'='*60}")
    print(f"  Pools monitored: {len(states)}")
    print(f"  Total alerts: {len(all_alerts)}")

    # Count by severity
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for a in all_alerts:
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
        by_type[a.alert_type] = by_type.get(a.alert_type, 0) + 1

    if by_severity:
        print(f"\n  By severity:")
        for sev, count in sorted(by_severity.items()):
            print(f"    {sev}: {count}")

    if by_type:
        print(f"\n  By type:")
        for atype, count in sorted(by_type.items()):
            print(f"    {atype}: {count}")

    # Per-pool summary
    print(f"\n  Per-pool summary:")
    for addr, state in states.items():
        if state.snapshots:
            first = state.snapshots[0]
            last = state.snapshots[-1]
            tvl_change = (
                ((last.tvl_usd - first.tvl_usd) / first.tvl_usd * 100)
                if first.tvl_usd > 0 else 0
            )
            print(
                f"    {state.dex_name:20s} | "
                f"TVL: ${first.tvl_usd:>10,.0f} -> ${last.tvl_usd:>10,.0f} "
                f"({tvl_change:+.1f}%) | "
                f"Alerts: {len(state.alerts)}"
            )

    print(f"\n  Note: This monitoring report is for informational purposes only.")
    print(f"  It does not constitute financial advice.\n")


# ── Monitor Loop ────────────────────────────────────────────────────


def run_monitor(token_mint: str, interval_seconds: int, max_checks: int) -> None:
    """Run the pool monitor in live mode.

    Args:
        token_mint: Solana token mint address.
        interval_seconds: Seconds between checks.
        max_checks: Maximum number of checks before stopping.
    """
    states: dict[str, MonitorState] = {}
    known_pools: set[str] = set()

    print(f"Monitoring pools for {token_mint}")
    print(f"Interval: {interval_seconds}s | Max checks: {max_checks}")
    print(f"Press Ctrl+C to stop.\n")

    for check_num in range(1, max_checks + 1):
        try:
            snapshots = fetch_pool_snapshots(token_mint)
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"  Fetch error at check {check_num}: {e}")
            time.sleep(interval_seconds)
            continue

        # Detect new pools
        for snap in snapshots:
            if snap.pool_address not in known_pools:
                known_pools.add(snap.pool_address)
                if check_num > 1 and NEW_POOL_ALERT:
                    alert = PoolAlert(
                        timestamp=snap.timestamp,
                        pool_address=snap.pool_address,
                        dex_name=snap.dex_name,
                        alert_type="new_pool",
                        severity="info",
                        message=f"New pool detected on {snap.dex_name} "
                                f"with TVL ${snap.tvl_usd:,.0f}",
                    )
                    print_alert(alert)
                    if snap.pool_address in states:
                        states[snap.pool_address].alerts.append(alert)

            # Initialize state if needed
            if snap.pool_address not in states:
                states[snap.pool_address] = MonitorState(
                    pool_address=snap.pool_address,
                    dex_name=snap.dex_name,
                    first_seen=snap.timestamp,
                    last_tvl=snap.tvl_usd,
                )

        # Detect alerts and update states
        for snap in snapshots:
            state = states[snap.pool_address]
            alerts = detect_alerts(state, snap)
            for alert in alerts:
                print_alert(alert)
                state.alerts.append(alert)
            update_state(state, snap)

        # Print report
        print_snapshot_report(snapshots, states, check_num)

        if check_num < max_checks:
            try:
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                print("\n\nMonitoring stopped by user.")
                break

    print_monitoring_summary(states)


def run_demo() -> None:
    """Run the pool monitor with simulated lifecycle data.

    Simulates 20 hours of pool activity including pool creation,
    liquidity events, and volume shifts.
    """
    print("Running demo simulation: Token pool lifecycle over 20 time steps")
    print("Simulating: PumpFun graduation -> growth -> liquidity event -> decline\n")

    lifecycle = simulate_pool_lifecycle()
    states: dict[str, MonitorState] = {}
    known_pools: set[str] = set()

    for step, (ts, snapshots) in enumerate(lifecycle, 1):
        # Detect new pools
        for snap in snapshots:
            if snap.pool_address not in known_pools:
                known_pools.add(snap.pool_address)
                if step > 1:
                    alert = PoolAlert(
                        timestamp=snap.timestamp,
                        pool_address=snap.pool_address,
                        dex_name=snap.dex_name,
                        alert_type="new_pool",
                        severity="info",
                        message=f"New pool detected on {snap.dex_name} "
                                f"with TVL ${snap.tvl_usd:,.0f}",
                    )
                    print_alert(alert)
                    states.setdefault(snap.pool_address, MonitorState(
                        pool_address=snap.pool_address,
                        dex_name=snap.dex_name,
                        first_seen=snap.timestamp,
                    )).alerts.append(alert)

            if snap.pool_address not in states:
                states[snap.pool_address] = MonitorState(
                    pool_address=snap.pool_address,
                    dex_name=snap.dex_name,
                    first_seen=snap.timestamp,
                    last_tvl=snap.tvl_usd,
                )

        # Detect alerts
        for snap in snapshots:
            state = states[snap.pool_address]
            alerts = detect_alerts(state, snap)
            for alert in alerts:
                print_alert(alert)
                state.alerts.append(alert)
            update_state(state, snap)

        # Print step report
        print_snapshot_report(snapshots, states, step)

    print_monitoring_summary(states)


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point: parse arguments and run pool monitor."""
    parser = argparse.ArgumentParser(
        description="Monitor DEX pool metrics and detect liquidity events"
    )
    parser.add_argument(
        "token_mint",
        nargs="?",
        default=None,
        help="Solana token mint address to monitor",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with simulated lifecycle data (no API calls)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between checks in live mode (default: 60)",
    )
    parser.add_argument(
        "--max-checks",
        type=int,
        default=60,
        help="Maximum number of checks before stopping (default: 60)",
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.token_mint:
        run_monitor(args.token_mint, args.interval, args.max_checks)
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python scripts/pool_monitor.py --demo")
        print("  python scripts/pool_monitor.py <TOKEN_MINT> --interval 30")
        sys.exit(1)


if __name__ == "__main__":
    main()
