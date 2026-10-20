"""Synthetic fixtures exercise research context without production requests."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/fxmacrodata/scripts"))

from fxmacrodata_skill import build_context, read_requests
from fxmacrodata_skill._fxmacrodata_client import FXMacroDataError, Result, list_operations


class Client:
    def __init__(self, payload=None, error=None):
        self.payload = payload if payload is not None else {"data": [{
            "fixture": "synthetic", "val": None, "unit": "fixture-unit",
            "date": "2000-01-01", "available_at": "2000-01-02T00:00:00Z",
            "prediction_class": "model", "source_url": "https://example.org/fixture",
        }], "metadata": {"pagination": {"has_more": False}}}
        self.error = error
        self.calls = []

    def execute(self, name, args):
        self.calls.append((name, args))
        if self.error:
            raise self.error
        return Result(name, deepcopy(self.payload), "https://example.org/fixture")

    def history(self, name, args, max_pages):
        self.calls.append(("history", max_pages))
        return Result(name, deepcopy(self.payload))


@pytest.mark.parametrize("operation", [op.name for op in list_operations()])
def test_every_advertised_operation_has_a_context_consumer(operation):
    client = Client()
    macro = build_context([{"operation": operation}], client=client)
    assert macro.results[0].operation == operation
    assert "fixture-unit" in macro.text and "prediction_class" in macro.text
    assert macro.results[0].payload == client.payload
    assert client.calls == [(operation, {})]


def test_preserves_originals_and_labels_preview_truncation(tmp_path):
    payload = {"data": [{"fixture": "x" * 500, "n": i} for i in range(20)], "meta": {"unit": "unaltered"}}
    macro = build_context([{"operation": "indicator_history"}], client=Client(payload), max_records=2, max_chars=1000)
    assert len(macro.text) <= 1000 and "truncated" in macro.text
    target = tmp_path / "result.json"
    macro.write(target)
    assert json.loads(target.read_text())["results"][0]["data"] == payload


def test_empty_is_explicit_and_never_fabricated():
    macro = build_context([{"operation": "release_calendar"}], client=Client({"data": []}))
    assert "No records returned" in macro.text
    assert macro.results[0].records() == []


@pytest.mark.parametrize("error", [FXMacroDataError("Unauthorized"), FXMacroDataError("Rate limited")])
def test_failure_is_not_silently_treated_as_no_data(error):
    with pytest.raises(FXMacroDataError):
        build_context([{"operation": "release_calendar"}], client=Client(error=error))


def test_history_is_explicit_and_bounded():
    client = Client()
    result = build_context([{"operation": "indicator_history", "history": True, "max_pages": 3}], client=client)
    assert client.calls == [("history", 3)]
    assert "collected history" in result.text


@pytest.mark.parametrize("descriptor", [
    [], [{"operation": "missing"}], [{"operation": "data_catalogue", "api_key": "fixture"}],
    [{"operation": "data_catalogue", "arguments": []}],
    [{"operation": "data_catalogue", "history": "yes"}],
    [{"operation": "data_catalogue", "history": True, "max_pages": True}],
    [{"operation": "data_catalogue", "max_pages": 3}],
])
def test_invalid_descriptors_fail_before_any_call(descriptor):
    client = Client()
    with pytest.raises(ValueError):
        build_context(descriptor, client=client)
    assert not client.calls


def test_multiple_request_files_preserve_order(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({"operation": "data_catalogue"}))
    b.write_text(json.dumps([{"operation": "release_calendar"}]))
    assert [r["operation"] for r in read_requests([a, b])] == ["data_catalogue", "release_calendar"]


def test_injected_credentials_rejected_by_real_client_without_transport():
    from fxmacrodata_skill._fxmacrodata_client import FXMacroDataClient
    class NoNetwork:
        def request(self, *args, **kwargs):
            pytest.fail("Invalid credentials reached transport")
    with pytest.raises(FXMacroDataError):
        build_context([{"operation": "data_catalogue", "arguments": {"currency": "usd", "api_key": "fixture"}}], client=FXMacroDataClient(session=NoNetwork()))
