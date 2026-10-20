"""Publication-time alignment for customer research, independent of any backend."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import math
import re
from typing import Iterable

UTC = timezone.utc
_IDENTITY = ("date", "currency", "indicator", "unit", "source", "source_url",
             "frequency", "seasonality", "annualization", "basis")
_VINTAGE = {"val", "epoch", "announcement_datetime", "vintage_status",
            "publication_time_status", "publication_time_precision", "publication_at_ns",
            "release_time_assumed", "observed_at_ns", "source_observed_at_ns",
            "committed_at_ns", "source_url", "announcement_source_url", "vintage_source_url",
            "source_document_id", "source_document_sha256", "revision_classification",
            "selected_vintage_known_at_ns", "replay_vintage_verified", "availability"}
_PROOF = ("vintage_status", "publication_time_status", "publication_time_precision",
          "publication_at_ns", "release_time_assumed")


class PointInTimeError(ValueError):
    """Publication or vintage evidence is insufficient for this research input."""


def timestamp_ns(value) -> int:
    """Parse a UTC epoch or ISO instant without rounding nanoseconds through float."""
    if isinstance(value, bool):
        raise PointInTimeError("A timestamp cannot be boolean.")
    if isinstance(value, (int, float, Decimal)):
        return int(Decimal(str(value)) * 1_000_000_000)
    text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += "T00:00:00Z"
    match = re.fullmatch(r"(.{19})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})", text)
    if not match:
        raise PointInTimeError("Decision timestamps require an explicit timezone.")
    dt = datetime.fromisoformat(match[1] + match[3].replace("Z", "+00:00"))
    return int(dt.timestamp()) * 1_000_000_000 + int((match[2] or "").ljust(9, "0"))


def _boundary(row: dict, availability: str) -> int | None:
    known = _evidence_boundary(row, availability)
    if row.get("replay_vintage_verified") is True:
        try:
            stamp = row["selected_vintage_known_at_ns"]
            if (row.get("availability") == availability and not isinstance(stamp, bool)
                and int(stamp) > 0 and int(stamp) == known):
                return known
        except (ValueError, KeyError, TypeError):
            pass
        return None
    return known


def _evidence_boundary(row: dict, availability: str) -> int | None:
    if availability == "captured":
        stamp = row.get("observed_at_ns")
        return int(stamp) if isinstance(stamp, (int, str)) and str(stamp).isdigit() and int(stamp) > 0 else None
    if (row.get("vintage_status") != "source_vintage" or
        row.get("publication_time_status") != "confirmed" or row.get("release_time_assumed") is True):
        return None
    precision = row.get("publication_time_precision")
    epoch = row.get("epoch", row.get("announcement_datetime"))
    if epoch is None or isinstance(epoch, bool):
        return None
    if precision in {"second", "minute"}:
        try:
            return timestamp_ns(epoch) + ({"second": 1, "minute": 60}[precision] * 1_000_000_000 - 1)
        except (ValueError, TypeError):
            return None
    if precision in {"microsecond", "nanosecond"}:
        stamp = row.get("publication_at_ns")
        try:
            if int(stamp) // 1_000_000_000 == int(epoch):
                return int(stamp) + (999 if precision == "microsecond" else 0)
        except (TypeError, ValueError):
            pass
    return None


def prepare_events(rows: Iterable[dict], *, availability: str = "public") -> dict:
    """Expand only evidenced value vintages; never use an observation date as availability.

    Dates remain economic reference periods. A replay response already narrowed
    at one cutoff cannot recover earlier omitted vintages; download revisions=all
    for a multi-date backtest. Unknown and date-only publication clocks are
    counted and excluded from this strict mode.
    """
    if availability not in {"public", "captured"}:
        raise ValueError("availability must be public or captured")
    events = {}
    excluded = 0
    for raw in rows:
        # Realized announcement rows may retain legacy prediction sidecars.
        # Only an evidenced val is eligible; predicted_value is never promoted.
        head = {k: v for k, v in raw.items() if k != "revisions"}
        ledger = [deepcopy(v) for v in raw.get("revisions") or [] if isinstance(v, dict)]
        # A mutable public head must name a value/epoch already in its ledger.
        # A later value cannot be assigned an intermediate or original release time.
        head_epoch = head.get("epoch", head.get("announcement_datetime"))
        vintages = ledger
        if availability == "captured" or not ledger:
            vintages.append(head)
        elif _boundary(head, "public") is not None:
            for vintage in vintages:
                if (vintage.get("epoch", vintage.get("announcement_datetime")) == head_epoch
                    and vintage.get("val") == head.get("val")
                    and _boundary(vintage, "public") is None):
                    # A matching legacy entry may acquire missing proof, never
                    # the current head's ancillary values or series identity.
                    for field in _PROOF:
                        if vintage.get(field) is None and field in head:
                            vintage[field] = deepcopy(head[field])
        for vintage in vintages:
            if not isinstance(vintage, dict):
                continue
            known = _boundary(vintage, availability)
            value = vintage.get("val")
            try:
                usable = value is not None and not isinstance(value, bool) and math.isfinite(float(value))
            except (ValueError, TypeError):
                usable = False
            if known is None or not usable or not raw.get("date"):
                excluded += 1
                continue
            item = {k: deepcopy(raw[k]) for k in _IDENTITY if k in raw}
            # Only identity/provenance belongs to the parent; value-specific clocks
            # always come from the selected vintage.
            for field in ("announcement_datetime", "publication_at_ns", "observed_at_ns",
                          "release_time_assumed", "publication_time_status", "publication_time_precision"):
                item.pop(field, None)
            item.update({k: deepcopy(v) for k, v in vintage.items()
                         if k in _VINTAGE or k in _IDENTITY or k == "effective_date"})
            change = vintage.get("change")
            if isinstance(change, (int, float)) and not isinstance(change, bool) and math.isfinite(change):
                item["change"] = change
            item["val"] = float(value)
            item["known_at_ns"] = str(known)
            item["availability"] = availability
            if "epoch" in vintage:
                item["announcement_datetime"] = vintage["epoch"]
            key = (str(raw.get("currency", "")), str(raw.get("indicator", "")), str(raw["date"]), known)
            if key in events and (events[key].get("ambiguous_vintage") or events[key]["val"] != item["val"]):
                item["val"] = None
                item["ambiguous_vintage"] = True
            elif key in events:
                # The ledger owns equal-clock/value ties. A captured head can
                # still become a later event through its own observation clock.
                continue
            events[key] = item
    return {"data": sorted(events.values(), key=lambda e: (int(e["known_at_ns"]), str(e["date"]))),
            "excluded_vintages": excluded, "availability": availability,
            "source": "FXMacroData", "strict_publication_timing": True}


def macro_events(rows: Iterable[dict], **kwargs) -> list[dict]:
    """Return evidenced events, raising when no historical value can be selected."""
    events = prepare_events(rows, **kwargs)["data"]
    if not events:
        raise PointInTimeError("No eligible value vintages; request revisions=all and inspect publication/vintage coverage.")
    return events


def macro_updates(rows: Iterable[dict], **kwargs) -> list[dict]:
    """Latest-period feature updates for event-driven backtesting engines."""
    events = macro_events(rows, **kwargs)
    state = {}
    updates = []
    for event in events:
        identity = (event.get("currency"), event.get("indicator"))
        periods = state.setdefault(identity, {})
        periods[str(event["date"])] = event
        if str(event["date"]) == max(periods):
            updates.append(event)
    return updates


def align_macro(rows: Iterable[dict], decisions: Iterable, *, availability="public",
                delay_seconds: float = 0, max_age_days: float | None = None) -> list[dict | None]:
    """Select the latest reference period and eligible vintage strictly before each decision.

    A late revision to an older reference period does not replace a newer period.
    Missing values remain missing. No back-fill from future observations occurs.
    """
    if delay_seconds < 0 or (max_age_days is not None and max_age_days < 0):
        raise ValueError("Delay and maximum age must be non-negative")
    events = macro_events(rows, availability=availability)
    identities = {(e.get("currency"), e.get("indicator")) for e in events}
    if len(identities) > 1:
        raise ValueError("Align one currency/indicator series at a time")
    indexed = sorted((timestamp_ns(t), i) for i, t in enumerate(decisions))
    answer = [None] * len(indexed)
    state = {}
    position = 0
    delay_ns = int(Decimal(str(delay_seconds)) * 1_000_000_000)
    for cutoff, index in indexed:
        while position < len(events) and int(events[position]["known_at_ns"]) + delay_ns < cutoff:
            event = events[position]
            state[str(event["date"])] = event
            position += 1
        if state:
            selected = state[max(state)]
            age = cutoff - int(selected["known_at_ns"])
            if selected["val"] is not None and (max_age_days is None or age <= max_age_days * 86400e9):
                answer[index] = deepcopy(selected)
    return answer
