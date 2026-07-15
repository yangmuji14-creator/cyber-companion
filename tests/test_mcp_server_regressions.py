"""Regression tests for local MCP server framing and dispatch errors."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


SERVER_SCRIPTS = ("system_tools.py", "weather.py", "web_fetch.py")


def frame(message: dict) -> bytes:
    body = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def parse_frames(data: bytes) -> list[dict]:
    messages = []
    remaining = data
    while remaining:
        header, separator, framed = remaining.partition(b"\r\n\r\n")
        assert separator, f"missing frame separator in {remaining!r}"
        content_length = next(
            int(line.split(b":", 1)[1].strip())
            for line in header.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        )
        body = framed[:content_length]
        messages.append(json.loads(body.decode("utf-8")))
        remaining = framed[content_length:]
    return messages


@pytest.mark.parametrize("script_name", SERVER_SCRIPTS)
def test_server_handles_concatenated_frames(
    script_name: str,
) -> None:
    # Given
    server_path = Path(__file__).parent.parent / "mcp_servers" / script_name
    requests = b"".join((
        frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
    ))

    # When
    completed = subprocess.run(
        [sys.executable, str(server_path)],
        input=requests,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
    )
    responses = parse_frames(completed.stdout)

    # Then
    assert [response.get("id") for response in responses] == [1, 2]


@pytest.mark.parametrize("script_name", SERVER_SCRIPTS)
def test_server_reports_internal_error_for_malformed_tool_call(
    script_name: str,
) -> None:
    # Given
    server_path = Path(__file__).parent.parent / "mcp_servers" / script_name
    request = frame({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {},
    })

    # When
    completed = subprocess.run(
        [sys.executable, str(server_path)],
        input=request,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
    )
    responses = parse_frames(completed.stdout)

    # Then
    assert responses == [{
        "jsonrpc": "2.0",
        "id": 3,
        "error": {"code": -32603, "message": "Internal error"},
    }]


def test_system_tools_rejects_config_paths_and_symlink_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    from mcp_servers import system_tools

    # When / Then
    escaped_target = str(Path(__file__).parent.parent / "[private].txt")
    monkeypatch.setattr(system_tools.os.path, "realpath", lambda _path: escaped_target)
    assert system_tools._is_path_safe("[linked].txt") is False
    assert system_tools._is_path_safe(str(Path(__file__).parent.parent / "config" / "settings.json")) is False


def test_web_fetch_rejects_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    from mcp_servers import web_fetch

    class RedirectOpener:
        def open(self, _request: object, timeout: int) -> object:
            raise web_fetch.urllib.error.HTTPError(
                "https://example.com/",
                302,
                "Found",
                {},
                None,
            )

    monkeypatch.setattr(web_fetch.urllib.request, "build_opener", lambda _handler: RedirectOpener())
    monkeypatch.setattr(web_fetch, "_is_internal_url", lambda _url: False)

    # When
    result = web_fetch.fetch({"url": "https://example.com/"})

    # Then
    assert result == "HTTP 302: Found"
