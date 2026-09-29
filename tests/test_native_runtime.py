"""Tests for the warm project-scoped native hook runtime."""

from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
import threading

from acco import hook
from acco.native_runtime import (
    RuntimePool,
    _handler_factory,
    _write_manifest,
    request_native_event,
)


def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_runtime_pool_reuses_runtime_until_config_changes(tmp_path, monkeypatch):
    """Warm hook runtime should avoid rebuilding services on every event."""
    root = _root(tmp_path, monkeypatch)
    built = []

    def fake_build(project_root):
        value = object()
        built.append((project_root, value))
        return value

    monkeypatch.setattr(hook, "build_hook_runtime", fake_build)
    pool = RuntimePool()

    first = pool.get(root)
    second = pool.get(root)
    assert first is second
    assert len(built) == 1

    config = root / ".acco.toml"
    config.write_text("[general]\ndisabled = false\n", encoding="utf-8")
    third = pool.get(root)

    assert third is not first
    assert len(built) == 2


def test_authenticated_runtime_serves_claude_event_without_payload_logging(
    tmp_path, monkeypatch
):
    """Loopback runtime should reuse its pool and return strict JSON."""
    root = _root(tmp_path, monkeypatch)
    calls = []

    class FakeRuntime:
        def run(self, payload):
            calls.append(payload)
            return 0, {"hookSpecificOutput": {"additionalContext": "warm"}}

    class FakePool:
        def get(self, project_root):
            assert project_root == root
            return FakeRuntime()

    token = "a" * 64
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _handler_factory(root, token, FakePool()),
    )
    _write_manifest(root, server, token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, response = request_native_event(
            root,
            "claude",
            "SessionStart",
            {
                "cwd": str(root),
                "hook_event_name": "SessionStart",
                "source": "resume",
                "secret_body": "do-not-log",
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == "ok"
    assert response == {"hookSpecificOutput": {"additionalContext": "warm"}}
    assert calls[0]["secret_body"] == "do-not-log"


def test_runtime_rejects_manifest_for_another_project(tmp_path, monkeypatch):
    """A copied endpoint manifest must not be accepted by another checkout."""
    one = _root(tmp_path, monkeypatch)
    two = tmp_path / "repo-two"
    two.mkdir()

    class FakeRuntime:
        def run(self, payload):
            return 0, {}

    class FakePool:
        def get(self, _project_root):
            return FakeRuntime()

    token = "b" * 64
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _handler_factory(one, token, FakePool()),
    )
    first_manifest = _write_manifest(one, server, token)
    second_manifest = first_manifest.parent / (
        __import__("hashlib").sha256(str(two.resolve()).encode()).hexdigest()[:24]
        + ".json"
    )
    payload = json.loads(first_manifest.read_text(encoding="utf-8"))
    second_manifest.write_text(json.dumps(payload), encoding="utf-8")
    try:
        status, response = request_native_event(two, "claude", "SessionStart", {})
    finally:
        server.server_close()

    assert status == "unavailable"
    assert response is None
