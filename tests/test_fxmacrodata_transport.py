"""Synthetic offline fixtures test the public client, never real account data."""
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/fxmacrodata/scripts"))

from fxmacrodata_skill._fxmacrodata_client import FXMacroDataClient, FXMacroDataError, Result, list_operations


class Response:
    def __init__(self, payload=None, status=200, headers=None, lines=None):
        self.status_code = status
        self.headers = headers or {"Content-Type": "application/json"}
        self.content = json.dumps(payload).encode()
        self.lines = lines
        self.closed = False

    def iter_content(self, chunk_size):
        if self.lines is not None:
            yield b"\n".join(self.lines) + b"\n"
        else:
            yield self.content

    def iter_lines(self, chunk_size):
        yield from self.lines or []

    def close(self):
        self.closed = True


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_inventory_is_complete_and_credentials_are_not_model_arguments():
    operations = list_operations()
    assert len(operations) == 91
    assert len({op.name for op in operations}) == 91
    assert sum(op.method == "GET" for op in operations) == 36
    assert sum(op.method == "POST" for op in operations) == 1
    assert sum(op.method == "MCP" for op in operations) == 54
    assert "mcp_seasonality" in {op.name for op in operations}
    assert all("api_key" not in op.input_schema.get("properties", {}) for op in operations)


@pytest.mark.parametrize("op", [op for op in list_operations(False) if op.name != "stream_events"], ids=lambda op: op.name)
def test_every_rest_operation_routes_to_fixed_origin_and_preserves_payload(op):
    # These are explicit synthetic transport records, not economic observations.
    payload = {"data": [{"fixture": "transport-test", "announcement_datetime": 1, "date": "1970-01-01", "val": None}], "metadata": {"release_time_assumed": True}}
    response = Response(payload)
    transport = Session(response)
    client = FXMacroDataClient(api_key="unit-test-credential", session=transport)
    args = {name: {"currency": "usd", "base": "eur", "quote": "usd", "indicator": "inflation", "factor": "monetary_stance", "archive_event_id": "fixture-event", "as_of": "2000-01-01T00:00:00Z", "contract_id": "usd_cpi_yoy", "body": {"series": [{"currency": "usd", "indicator": "policy_rate"}], "decision_times": ["2026-09-01T00:00:00Z"], "start_date": "2026-08-01", "end_date": "2026-09-01"}}.get(name, "sample") for name in op.input_schema.get("required", [])}
    result = client.execute(op.name, args)
    method, url, options = transport.calls[0]
    assert method == op.method and url.startswith("https://api.fxmacrodata.com/v1/")
    assert "{" not in url and "?" not in url
    assert options["params"]["api_key"] == "unit-test-credential"
    assert options["allow_redirects"] is False
    assert options["json"] == args.get("body")
    assert "body" not in options["params"]
    assert result.payload == payload and result.records() == payload["data"]
    assert "unit-test-credential" not in repr(result)
    assert response.closed


@pytest.mark.parametrize("arguments", [{"currency": "../users"}, {"currency": "usd", "api_key": "secret"}, {"currency": "usd", "url": "https://example.com"}, {"currency": "usd", "unknown": True}])
def test_path_and_credential_injection_fails_before_network(arguments):
    transport = Session()
    with pytest.raises(FXMacroDataError):
        FXMacroDataClient(api_key="", session=transport).execute("release_calendar", arguments)
    assert not transport.calls


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500])
def test_errors_cannot_echo_credentials_or_remote_error_body(status):
    response = Response({"detail": "secret-from-server"}, status=status)
    with pytest.raises(FXMacroDataError) as error:
        FXMacroDataClient(api_key="secret-from-server", session=Session(response)).execute("ping")
    assert "secret-from-server" not in str(error.value)
    assert "https://" not in str(error.value)
    assert response.closed


def test_network_error_is_sanitized():
    transport = Session(requests.ConnectionError("https://api.fxmacrodata.com?api_key=private"))
    with pytest.raises(FXMacroDataError) as error:
        FXMacroDataClient(api_key="private", session=transport).execute("ping")
    assert "private" not in str(error.value)


def test_mcp_handshake_auth_session_and_original_content():
    payload = {"structuredContent": {"data": [{"fixture": "mcp-test"}]}, "content": [{"type": "text", "text": "sample"}], "isError": False}
    transport = Session(Response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}}, headers={"Content-Type": "application/json", "Mcp-Session-Id": "synthetic-session"}), Response(status=202), Response({"jsonrpc": "2.0", "id": 2, "result": payload}))
    result = FXMacroDataClient(api_key="unit-test-credential", session=transport).execute("mcp_ping")
    assert [c[2]["json"]["method"] for c in transport.calls] == ["initialize", "notifications/initialized", "tools/call"]
    assert transport.calls[2][2]["headers"]["Mcp-Session-Id"] == "synthetic-session"
    assert all(c[2]["params"] == {"api_key": "unit-test-credential"} for c in transport.calls)
    assert result.payload == payload and result.records() == [{"fixture": "mcp-test"}]


def test_discovery_paginates_and_registers_new_tools():
    tool = lambda name: {"name": name, "inputSchema": {"type": "object", "properties": {}}}
    transport = Session(Response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}}), Response(status=202), Response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [tool("test_a")], "nextCursor": "page2"}}), Response({"jsonrpc": "2.0", "id": 3, "result": {"tools": [tool("test_b")]}}))
    client = FXMacroDataClient(api_key="", session=transport)
    assert [op.name for op in client.discover_mcp_tools()] == ["mcp_test_a", "mcp_test_b"]
    assert transport.calls[-1][2]["json"]["params"] == {"cursor": "page2"}
    assert "mcp_test_b" in {op.name for op in client.list_operations()}


def test_sse_preserves_event_id_multiline_data_and_reconnect_cursor():
    response = Response(headers={"Content-Type": "text/event-stream"}, lines=[b": heartbeat", b"", b"id: event1", b"event: release", b'data: {"fixture":', b'data: "stream-test"}', b"", b"id: event2", b"data: {}", b""])
    transport = Session(response)
    result = FXMacroDataClient(api_key="", session=transport).execute("stream_events", {"Last-Event-ID": "prior-event", "max_events": 1})
    assert result.payload["events"] == [{"id": "event1", "event": "release", "data": {"fixture": "stream-test"}}]
    assert transport.calls[0][2]["headers"]["Last-Event-ID"] == "prior-event"
    assert "max_events" not in transport.calls[0][2]["params"]
    assert result.payload["capture_complete"] and response.closed


def test_empty_and_presentations_do_not_mutate_original():
    assert Result("sample", {"data": []}).records() == []
    payload = {"data": [{"fixture": "original", "val": None}], "metadata": {"units": "fixture"}}
    result = Result("sample", payload)
    view = result.as_dict()
    view["records"][0]["val"] = 100
    view["data"]["metadata"]["units"] = "modified"
    assert payload["data"][0]["val"] is None and payload["metadata"]["units"] == "fixture"


def test_credentials_are_redacted_even_if_echoed_by_service():
    transport = Session(Response({"data": [{"api_key": "synthetic"}, {"detail": "token=synthetic api_key=other"}]}))
    result = FXMacroDataClient(api_key="synthetic", session=transport).execute("ping")
    assert "synthetic" not in json.dumps(result.as_dict())
    assert "api_key=other" not in json.dumps(result.as_dict())


def test_native_urllib3_request_diagnostics_redact_before_log_handlers(caplog):
    import logging
    from unittest.mock import Mock
    from urllib.parse import quote_plus
    from urllib3.connectionpool import HTTPConnectionPool
    from urllib3.response import HTTPResponse

    credential = "synthetic diagnostic+/ credential"

    class DiagnosticSession(Session):
        def request(self, method, url, **kwargs):
            # Exercise urllib3's actual request log without opening a socket.
            pool = HTTPConnectionPool("api.fxmacrodata.com")
            connection = Mock(is_closed=True)
            connection.getresponse.return_value = HTTPResponse(body=b"{}", status=200)
            pool._make_request(connection, method, "/v1/ping?api_key=" + quote_plus(credential))
            return Response({"status": "ok"})

    with caplog.at_level(logging.DEBUG, logger="urllib3.connectionpool"):
        assert FXMacroDataClient(api_key=credential, session=DiagnosticSession()).execute("ping").payload == {"status": "ok"}
        logging.getLogger("urllib3.connectionpool").debug("unrelated client diagnostic")
    assert "GET /v1/ping?api_key=[redacted]" in caplog.text
    assert credential not in caplog.text and quote_plus(credential) not in caplog.text
    assert "unrelated client diagnostic" in caplog.text
    assert all(not record.args for record in caplog.records if "api_key" in record.getMessage())


def test_transport_exception_and_body_diagnostics_are_redacted(caplog):
    import logging
    credential = "synthetic diagnostic secret"

    class DiagnosticResponse(Response):
        def iter_content(self, chunk_size):
            try:
                raise ValueError(credential)
            except ValueError:
                logging.getLogger("urllib3.connectionpool").exception("body diagnostic %s", credential)
            yield self.content

    with caplog.at_level(logging.DEBUG, logger="urllib3.connectionpool"):
        FXMacroDataClient(api_key=credential, session=Session(DiagnosticResponse({}))).execute("ping")
    assert "body diagnostic [redacted]" in caplog.text and credential not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_request_diagnostic_context_restores_after_failure(caplog):
    import logging
    from fxmacrodata_skill._fxmacrodata_client.transport import protected_diagnostics

    with caplog.at_level(logging.DEBUG, logger="urllib3.connectionpool"):
        with pytest.raises(RuntimeError):
            with protected_diagnostics("synthetic-context"):
                logging.getLogger("urllib3.connectionpool").debug("synthetic-context")
                raise RuntimeError("fixture")
        logging.getLogger("urllib3.connectionpool").debug("synthetic-context")
    assert [record.getMessage() for record in caplog.records] == ["[redacted]", "synthetic-context"]


def test_owned_https_connections_ignore_global_wire_debug_flags(monkeypatch):
    import http.client
    from urllib3.connection import HTTPSConnection

    monkeypatch.setattr(http.client.HTTPConnection, "debuglevel", 1)
    monkeypatch.setattr(HTTPSConnection, "debuglevel", 1)
    with FXMacroDataClient(api_key="synthetic-wire-key") as client:
        for origin in ("https://api.fxmacrodata.com/v1/ping", "https://mcp.fxmacrodata.com/mcp"):
            adapter = client._session.get_adapter(origin)
            pool = adapter.poolmanager.connection_from_url(origin)
            connection = pool._new_conn()
            assert connection.debuglevel == 0
            connection.close()
            proxy = adapter.proxy_manager_for("http://proxy.example:8080")
            assert proxy.pool_classes_by_scheme["https"].ConnectionCls.debuglevel == 0
        assert client._session.get_adapter("https://example.org").poolmanager.pool_classes_by_scheme["https"].ConnectionCls is HTTPSConnection
    assert HTTPSConnection.debuglevel == 1  # no global transport mutation


def test_successful_responses_redact_encoded_keys_and_sensitive_field_variants():
    from urllib.parse import quote, quote_plus
    credential = "synthetic echo+/ credential"
    payload = {"apiKey": "other-secret", "access-token": "another-secret", "details": [credential, quote(credential, safe=""), quote_plus(credential)]}
    result = FXMacroDataClient(api_key=credential, session=Session(Response(payload))).execute("ping")
    assert result.payload == {"apiKey": "[redacted]", "access-token": "[redacted]", "details": ["[redacted]"] * 3}


def test_response_redaction_covers_nested_json_text_dictionary_keys_and_authorization():
    credential = "synthetic-response-key"
    payload = {credential: {"content": [{"text": '{"api_key": "other-secret"} Authorization: Bearer another-secret'}], "client_secret": "third-secret"}}
    result = FXMacroDataClient(api_key=credential, session=Session(Response(payload))).execute("ping")
    assert result.payload == {"[redacted]": {"content": [{"text": '{"api_key": "[redacted]"} Authorization: [redacted]'}], "client_secret": "[redacted]"}}


def test_no_key_is_explicit_and_no_silent_auth_required():
    transport = Session(Response({"data": []}))
    FXMacroDataClient(api_key="", session=transport).execute("release_calendar", {"currency": "usd"})
    assert "api_key" not in transport.calls[0][2]["params"]


def initialized_session(*responses):
    return Session(Response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}}), Response(status=202), *responses)


def test_mcp_sse_returns_matching_response_before_stream_closes():
    class PersistentSSE(Response):
        def iter_content(self, chunk_size):
            yield b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\r\n\r\n'
            yield b'data: {"jsonrpc":"2.0","id":99,"result":{}}\n\n'
            yield b'data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"ready"}]}}\n\n'
            raise AssertionError("The client waited beyond its completed response")
    response = PersistentSSE(headers={"Content-Type": "text/event-stream; charset=utf-8"})
    result = FXMacroDataClient(api_key="", session=initialized_session(response)).execute("mcp_ping")
    assert result.records() == [{"text": "ready"}]
    assert response.closed


@pytest.mark.parametrize("result", [None, [], {}, {"protocolVersion": None}, {"protocolVersion": "unsupported"}, {"protocolVersion": "2025-03-26\r\nprivate"}])
def test_malformed_initialization_is_safe_and_does_not_cache_session(result):
    response = Response({"jsonrpc": "2.0", "id": 1, "result": result})
    transport = Session(response)
    client = FXMacroDataClient(api_key="private", session=transport)
    with pytest.raises(FXMacroDataError) as error:
        client.execute("mcp_ping")
    assert "private" not in str(error.value)
    assert client._mcp_headers is None and len(transport.calls) == 1
    assert response.closed


@pytest.mark.parametrize("body", [
    {},
    {"series": [], "decision_times": [], "start_date": "2026-08-01", "end_date": "2026-09-01"},
    {"series": [{"currency": "usd", "indicator": "policy_rate", "api_key": "fixture"}], "decision_times": ["2026-09-01"], "start_date": "2026-08-01", "end_date": "2026-09-01"},
    {"series": [{"currency": "usd", "indicator": "policy_rate"}], "decision_times": ["2026-09-01"], "start_date": "2026-08-01", "end_date": "2026-09-01", "url": "https://example.com"},
])
def test_research_panel_rejects_invalid_nested_input_without_network(body):
    transport = Session()
    with pytest.raises(FXMacroDataError, match="input schema"):
        FXMacroDataClient(api_key="", session=transport).execute("research_panel", {"body": body})
    assert transport.calls == []


def test_public_operation_schemas_are_valid_and_need_no_remote_references():
    from jsonschema import Draft202012Validator

    for operation in list_operations():
        Draft202012Validator.check_schema(operation.input_schema)
        assert '"$ref"' not in json.dumps(operation.input_schema)


@pytest.mark.parametrize("envelope", [
    {"result": {}}, {"jsonrpc": "2.0", "id": 99, "result": {}},
    {"jsonrpc": "2.0", "id": True, "result": {}},
    {"jsonrpc": "2.0", "id": 2},
    {"jsonrpc": "2.0", "id": 2, "error": {"message": "private"}},
])
def test_invalid_rpc_envelope_never_exposes_remote_details(envelope):
    response = Response(envelope)
    with pytest.raises(FXMacroDataError) as error:
        FXMacroDataClient(api_key="private", session=initialized_session(response)).execute("mcp_ping")
    assert "private" not in str(error.value) and response.closed


def test_invalid_session_header_is_rejected_before_notification():
    response = Response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
                        headers={"Content-Type": "application/json", "Mcp-Session-Id": "private\r\nheader"})
    transport = Session(response)
    with pytest.raises(FXMacroDataError, match="invalid session header"):
        FXMacroDataClient(api_key="private", session=transport).execute("mcp_ping")
    assert len(transport.calls) == 1


@pytest.mark.parametrize("operation", ["mcp_ping", "stream_events"])
def test_invalid_stream_encoding_raises_only_safe_client_error(operation):
    response = Response(headers={"Content-Type": "text/event-stream"}, lines=[b"data: \xffprivate", b""])
    transport = initialized_session(response) if operation == "mcp_ping" else Session(response)
    with pytest.raises(FXMacroDataError) as error:
        FXMacroDataClient(api_key="private", session=transport).execute(operation)
    assert "private" not in str(error.value) and response.closed


def test_undelimited_sse_frame_is_bounded_before_line_parsing(monkeypatch):
    import fxmacrodata_skill._fxmacrodata_client.client as module
    monkeypatch.setattr(module, "MAX_RESPONSE_BYTES", 10)
    response = Response(headers={"Content-Type": "text/event-stream"})
    response.content = b"data: " + b"x" * 11
    with pytest.raises(FXMacroDataError, match="bounded response budget"):
        FXMacroDataClient(api_key="", session=Session(response)).execute("stream_events")
    assert response.closed


def test_truncated_frame_never_becomes_a_completed_release():
    response = Response(headers={"Content-Type": "text/event-stream"})
    response.content = b'data: {"fixture":"incomplete"}\n'
    result = FXMacroDataClient(api_key="", session=Session(response)).execute("stream_events")
    assert result.payload["events"] == [] and not result.payload["capture_complete"]
    assert response.closed


def test_parallel_tools_share_one_handshake_and_unique_ids():
    from concurrent.futures import ThreadPoolExecutor
    import time

    class ConcurrentSession:
        def __init__(self):
            self.calls = []

        def request(self, method, url, **kwargs):
            body = kwargs["json"]
            self.calls.append(body)
            time.sleep(0.005)
            if body["method"] == "notifications/initialized":
                return Response(status=202)
            result = {"protocolVersion": "2025-03-26"} if body["method"] == "initialize" else {"content": []}
            return Response({"jsonrpc": "2.0", "id": body["id"], "result": result})

    session = ConcurrentSession()
    client = FXMacroDataClient(api_key="", session=session)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: client.execute("mcp_ping"), range(8)))
    assert len(results) == 8
    assert sum(call["method"] == "initialize" for call in session.calls) == 1
    ids = [call["id"] for call in session.calls if "id" in call]
    assert ids == list(range(1, 10))


@pytest.mark.parametrize("page", [None, {}, {"tools": [None]}, {"tools": [{"name": "sample", "inputSchema": {"type": "invalid"}}]}])
def test_malformed_discovery_leaves_existing_operation_inventory_intact(page):
    response = Response({"jsonrpc": "2.0", "id": 2, "result": page})
    client = FXMacroDataClient(api_key="", session=initialized_session(response))
    before = client.list_operations()
    with pytest.raises(FXMacroDataError):
        client.discover_mcp_tools()
    assert client.list_operations() == before and response.closed


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), None, "invalid"])
def test_nonfinite_or_invalid_timeout_is_rejected(timeout):
    with pytest.raises(FXMacroDataError, match="finite number"):
        FXMacroDataClient(api_key="", timeout=timeout)


@pytest.mark.parametrize("arguments", [[], 1, "private", {1: "private"}])
def test_invalid_argument_container_fails_safely_without_network(arguments):
    session = Session()
    with pytest.raises(FXMacroDataError) as error:
        FXMacroDataClient(api_key="private", session=session).execute("ping", arguments)
    assert not session.calls and "private" not in str(error.value)


def test_close_releases_allocated_mcp_session_once_at_fixed_origin():
    handshake = Response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
                         headers={"Content-Type": "application/json", "Mcp-Session-Id": "fixture-session"})
    deleted = Response(status=204)
    session = Session(handshake, Response(status=202), Response({"jsonrpc": "2.0", "id": 2, "result": {"content": []}}), deleted)
    client = FXMacroDataClient(api_key="fixture-key", session=session)
    client.execute("mcp_ping")
    client.close()
    client.close()
    method, url, kwargs = session.calls[-1]
    assert method == "DELETE" and url == "https://mcp.fxmacrodata.com/mcp"
    assert kwargs["params"] == {"api_key": "fixture-key"}
    assert kwargs["headers"]["Mcp-Session-Id"] == "fixture-session"
    assert kwargs["timeout"] <= 2 and kwargs["allow_redirects"] is False
    assert deleted.closed and len(session.calls) == 4


def test_close_of_stateless_session_has_no_network_request():
    session = initialized_session(Response({"jsonrpc": "2.0", "id": 2, "result": {"content": []}}))
    client = FXMacroDataClient(api_key="", session=session)
    client.execute("mcp_ping")
    client.close()
    assert len(session.calls) == 3


def test_failed_session_cleanup_is_silent_and_idempotent():
    session = Session(requests.ConnectionError("private transport detail"))
    client = FXMacroDataClient(api_key="private", session=session)
    client._mcp_headers = {"Mcp-Session-Id": "fixture-session"}
    client.close()
    client.close()
    assert len(session.calls) == 1


def test_discovered_schema_cannot_trigger_remote_reference_fetch():
    tool = {"name": "remote_ref", "inputSchema": {"type": "object", "properties": {
        "value": {"$ref": "https://example.org/private-schema"}
    }}}
    session = initialized_session(Response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [tool]}}))
    client = FXMacroDataClient(api_key="", session=session)
    client.discover_mcp_tools()
    before = len(session.calls)
    with pytest.raises(FXMacroDataError, match="Invalid FXMacroData arguments"):
        client.execute("mcp_remote_ref", {"value": "fixture"})
    assert len(session.calls) == before


def test_stream_deadline_interrupts_idle_read_after_late_heartbeat():
    import socket
    import threading
    import time
    from types import SimpleNamespace

    reader, writer = socket.socketpair()
    reader.settimeout(10)

    class BlockingResponse(Response):
        def __init__(self):
            super().__init__(headers={"Content-Type": "text/event-stream"})
            self.raw = SimpleNamespace(connection=SimpleNamespace(sock=reader))

        def iter_content(self, chunk_size):
            while chunk := reader.recv(chunk_size):
                yield chunk

        def close(self):
            self.closed = True
            reader.close()

    def send_fixture():
        writer.sendall(b'data: {"fixture":"complete-before-deadline"}\n\n')
        time.sleep(0.8)
        writer.sendall(b": late heartbeat\n\n")

    sender = threading.Thread(target=send_fixture)
    sender.start()
    response = BlockingResponse()
    start = time.monotonic()
    try:
        result = FXMacroDataClient(api_key="", session=Session(response)).execute(
            "stream_events", {"max_seconds": 1, "max_events": 10})
        elapsed = time.monotonic() - start
        assert elapsed < 2.5  # the underlying read timeout is 10 seconds
        assert result.payload["events"] == [{"data": {"fixture": "complete-before-deadline"}}]
        assert result.payload["reason"] == "timeout"
        assert not result.payload["capture_complete"] and response.closed
    finally:
        sender.join(timeout=2)
        reader.close()
        writer.close()


def test_json_response_body_deadline_interrupts_partial_idle_body():
    import socket
    import time
    from types import SimpleNamespace

    reader, writer = socket.socketpair()
    reader.settimeout(10)
    writer.sendall(b'{"partial":')

    class BlockingResponse(Response):
        def __init__(self):
            super().__init__()
            self.raw = SimpleNamespace(connection=SimpleNamespace(sock=reader))

        def iter_content(self, chunk_size):
            while chunk := reader.recv(chunk_size):
                yield chunk

        def close(self):
            self.closed = True
            reader.close()

    response = BlockingResponse()
    started = time.monotonic()
    try:
        with pytest.raises(FXMacroDataError):
            FXMacroDataClient(api_key="", timeout=1, session=Session(response)).execute("ping")
        assert time.monotonic() - started < 2.5
        assert response.closed
    finally:
        reader.close()
        writer.close()


def schema_fixture(schema, root=None):
    """Construct transport-only inputs from a public tool schema."""
    root = root or schema
    if "$ref" in schema:
        node = root
        for key in schema["$ref"][2:].split("/"):
            node = node[key]
        return schema_fixture(node, root)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "default" in schema:
        return schema["default"]
    if "examples" in schema and schema["examples"]:
        return schema["examples"][0]
    for union in ("anyOf", "oneOf"):
        if union in schema:
            choice = next((s for s in schema[union] if s.get("type") != "null"), schema[union][0])
            return schema_fixture(choice, root)
    kind = schema.get("type", "object" if "properties" in schema else "string")
    if kind == "object":
        return {name: schema_fixture(schema["properties"][name], root) for name in schema.get("required", [])}
    if kind == "array":
        return [schema_fixture(schema.get("items", {}), root) for _ in range(max(1, schema.get("minItems", 0)))]
    if kind in {"integer", "number"}:
        return schema.get("minimum", 1)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "usd"


@pytest.mark.parametrize("operation", [o for o in list_operations() if o.method == "MCP"], ids=lambda op: op.name)
def test_each_mcp_tool_validates_and_routes_with_original_result(operation):
    payload = {"structuredContent": {"data": [{"fixture": "mcp-schema-test", "val": None}]}, "content": [], "isError": False}
    transport = initialized_session(Response({"jsonrpc": "2.0", "id": 2, "result": payload}))
    client = FXMacroDataClient(api_key="", session=transport)
    args = schema_fixture(operation.input_schema)
    result = client.execute(operation.name, args)
    assert transport.calls[-1][2]["json"]["params"] == {"name": operation.name[4:], "arguments": args}
    assert result.payload == payload
    assert result.records() == [{"fixture": "mcp-schema-test", "val": None}]
