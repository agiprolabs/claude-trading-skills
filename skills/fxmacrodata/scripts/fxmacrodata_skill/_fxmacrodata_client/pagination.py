"""Complete, resumable reads of FXMacroData's offset-paginated responses."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Callable, Iterator, Mapping


class IncompleteHistoryError(RuntimeError):
    """A complete history could not be verified; no partial list is returned."""

    def __init__(self, message: str, *, resume: dict | None = None):
        self.resume = resume or {}
        super().__init__(message)


class DatasetChangedError(IncompleteHistoryError):
    """The dataset changed between pages. Restart the download."""


def iter_pages(fetch: Callable[[dict], Mapping[str, Any]], params=None, *,
               max_pages: int = 10000, resume: dict | None = None, request_id: str = "",
               require_pagination: bool = False) -> Iterator[dict]:
    """Yield original page envelopes, with an additive credential-free checkpoint.

    Persist each page before its ``client_resume`` checkpoint. Resuming returns
    remaining pages; combine with the already persisted pages. A content version
    is verified and pinned whenever the endpoint supplies one.
    """
    query = {k: v for k, v in (params or {}).items() if v is not None}
    if "page" in query:
        raise ValueError("Complete history uses offset, not page; use a page request for one page.")
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    query.setdefault("limit", 100)
    query.setdefault("offset", 0)
    identity = {k: v for k, v in query.items() if k not in {"offset", "dataset_version", "api_key", "access_token"}}
    request_hash = hashlib.sha256(json.dumps([request_id, identity], sort_keys=True, default=str).encode()).hexdigest()
    if resume and resume.get("request_hash") != request_hash:
        raise IncompleteHistoryError("Resume checkpoint belongs to a different history request.")
    if resume and resume.get("complete"):
        return
    version = (resume or {}).get("dataset_version") or query.get("dataset_version")
    if resume:
        query["offset"] = resume["next_offset"]
    if version:
        query["dataset_version"] = version
    seen = set()
    total = (resume or {}).get("total_count")
    checkpoint = {"next_offset": query["offset"], "dataset_version": version, "complete": False,
                  "request_hash": request_hash, "total_count": total}
    for _ in range(max_pages):
        try:
            payload = deepcopy(dict(fetch(dict(query))))
        except IncompleteHistoryError:
            raise
        except Exception as exc:
            if hasattr(exc, "status_code"):
                exc.resume = dict(checkpoint)
                raise
            raise IncompleteHistoryError("History download failed; resume from the last saved page.", resume=checkpoint) from None
        data = payload.get("data")
        if not isinstance(data, list):
            raise IncompleteHistoryError("History response has no data array.", resume=checkpoint)
        if query.get("value_mode") == "source" and (payload.get("value_mode") != "source"
            or (payload.get("value_metadata") or {}).get("normalization_applied") is not False):
            raise IncompleteHistoryError("Research history did not confirm value_mode=source; the API must support source-unit replay.", resume=checkpoint)
        page = payload.get("pagination")
        current_version = (payload.get("replay") or {}).get("dataset_version") or payload.get("dataset_version")
        if version and current_version != version:
            raise DatasetChangedError("History content version changed or disappeared; restart the download.")
        if current_version:
            version = current_version
            query["dataset_version"] = version
        if page is None:
            if require_pagination:
                raise IncompleteHistoryError("History response omitted required pagination metadata.", resume=checkpoint)
            checkpoint = {"next_offset": None, "dataset_version": version, "complete": True,
                          "request_hash": request_hash, "total_count": len(data)}
            payload["client_resume"] = checkpoint
            yield payload
            return
        if not isinstance(page, dict) or not isinstance(page.get("has_more"), bool):
            raise IncompleteHistoryError("History pagination metadata is invalid.", resume=checkpoint)
        if page.get("offset", query["offset"]) != query["offset"]:
            raise IncompleteHistoryError("Server returned an unexpected page offset.", resume=checkpoint)
        if page.get("returned_count", len(data)) != len(data):
            raise IncompleteHistoryError("Page row count does not match its metadata.", resume=checkpoint)
        if total is not None and page.get("total_count") != total:
            raise DatasetChangedError("History row count changed between pages; restart the download.")
        total = page.get("total_count")
        signature = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        if data and signature in seen:
            raise IncompleteHistoryError("Server repeated a page; history is incomplete.", resume=checkpoint)
        seen.add(signature)
        more = page["has_more"]
        next_offset = page.get("next_offset")
        if more and (not data or not isinstance(next_offset, int) or next_offset != query["offset"] + len(data)):
            raise IncompleteHistoryError("Pagination did not advance contiguously.", resume=checkpoint)
        if not more and total is not None and query["offset"] + len(data) != total:
            raise IncompleteHistoryError("Final page does not complete the reported history.", resume=checkpoint)
        checkpoint = {"next_offset": next_offset if more else None,
                      "dataset_version": version, "complete": not more,
                      "request_hash": request_hash, "total_count": total}
        payload["client_resume"] = dict(checkpoint)
        yield payload
        if not more:
            return
        query["offset"] = next_offset
    raise IncompleteHistoryError("History exceeded max_pages; increase the explicit budget or resume.", resume=checkpoint)


def paginated_history_path(path: str) -> bool:
    """Routes whose contract requires a pagination envelope."""
    if path.endswith("/latest") or path.endswith("/changes"):
        return False
    return any(path.startswith(prefix) for prefix in (
        "/v1/announcements/", "/v1/forex/", "/v1/cot/", "/v1/commodities/",
        "/v1/predictions/", "/v1/news/", "/v1/press-releases/", "/v1/financial_prices/",
        "/v1/rate_differentials/", "/v1/factors/", "/v1/fx/reference-rates/"))


def collect_history(fetch, params=None, **kwargs) -> dict:
    """Return all rows in chronological order and retain every page's metadata."""
    pages = list(iter_pages(fetch, params, **kwargs))
    rows = [row for page in pages for row in page["data"]]
    def order(row):
        stamp = next((row[k] for k in ("date", "reference_date", "timestamp", "issue_date", "announcement_datetime") if row.get(k) is not None), "")
        return str(stamp), json.dumps(row, sort_keys=True, default=str)
    rows.sort(key=order)
    return {"data": rows, "complete": True,
            "pages": [{k: v for k, v in page.items() if k != "data"} for page in pages],
            "client_resume": pages[-1]["client_resume"] if pages else dict(kwargs.get("resume") or {})}
