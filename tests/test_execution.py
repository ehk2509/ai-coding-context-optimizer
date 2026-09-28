"""Tests for restricted out-of-context programmable execution."""

from __future__ import annotations

import json
import sys

import pytest

from acco.execution import (
    ExecutionLimits,
    ExecutionValidationError,
    _worker_command,
    execute_program,
)
from acco.recovery import RecoveryStore


def _repo(tmp_path, monkeypatch):
    """Create one isolated repository and recovery state."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_worker_command_reenters_frozen_standalone(monkeypatch):
    """Frozen builds must spawn ACCO's private worker instead of treating ACCO as Python."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert _worker_command() == [sys.executable, "__acco-execution-worker"]


def test_worker_command_uses_isolated_python_for_normal_install(monkeypatch):
    """Python installs should retain isolated startup for the analysis child."""
    monkeypatch.delattr(sys, "frozen", raising=False)

    command = _worker_command()

    assert command[:3] == [sys.executable, "-I", "-S"]
    assert command[3] == "-c"


def test_execute_aggregates_large_local_input_without_returning_source(
    tmp_path, monkeypatch
):
    """Programs should compute over local file bytes and return only the result."""
    root = _repo(tmp_path, monkeypatch)
    rows = "\n".join(
        ["INFO start", "ERROR db", "INFO retry", "ERROR db", "WARN slow"] * 400
    )
    (root / "app.log").write_text(rows, encoding="utf-8")

    result = execute_program(
        root,
        """
levels = [line.split()[0] for line in data["app.log"].splitlines()]
result = dict(Counter(levels))
""",
        ["app.log"],
    )

    assert result["result"] == {"INFO": 800, "ERROR": 800, "WARN": 400}
    assert result["input_bytes"] > result["result_bytes"] * 100
    assert result["out_of_context"] is True
    assert rows not in json.dumps(result)


def test_execute_supports_json_regex_and_statistics_helpers(tmp_path, monkeypatch):
    """The restricted surface should cover common data-analysis operations."""
    root = _repo(tmp_path, monkeypatch)
    (root / "events.json").write_text(
        json.dumps({"values": [3, 7, 11], "message": "errors=12 warnings=4"}),
        encoding="utf-8",
    )

    result = execute_program(
        root,
        """
payload = json_loads(data["events.json"])
numbers = [int(value) for value in regex_findall(r"\\d+", payload["message"])]
result = {
    "mean": mean(payload["values"]),
    "numbers": numbers,
}
""",
        ["events.json"],
    )

    assert result["result"] == {"mean": 7, "numbers": [12, 4]}


@pytest.mark.parametrize(
    "code,match",
    [
        ("import os\nresult = 1", "Import"),
        ("result = open('x')", "open"),
        ("result = data.__class__", "private attribute"),
        ("result = globals()", "globals"),
    ],
)
def test_execute_rejects_escape_surfaces(tmp_path, monkeypatch, code, match):
    """Imports, arbitrary file access, and introspection must fail before execution."""
    root = _repo(tmp_path, monkeypatch)
    (root / "input.txt").write_text("safe", encoding="utf-8")

    with pytest.raises(ExecutionValidationError, match=match):
        execute_program(root, code, ["input.txt"])


def test_execute_rejects_repository_path_escape(tmp_path, monkeypatch):
    """Execution inputs must remain under the configured repository root."""
    root = _repo(tmp_path, monkeypatch)
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")

    with pytest.raises(ExecutionValidationError, match="escapes repository root"):
        execute_program(root, "result = len(data)", ["../secret.txt"])


def test_execute_preserves_unicode_through_isolated_subprocess(tmp_path, monkeypatch):
    """Execution transport must remain UTF-8 deterministic on every host OS."""
    root = _repo(tmp_path, monkeypatch)
    (root / "unicode.txt").write_text("café\nمرحبا\n東京\n", encoding="utf-8")

    result = execute_program(
        root,
        'result = data["unicode.txt"].splitlines()',
        ["unicode.txt"],
    )

    assert result["result"] == ["café", "مرحبا", "東京"]


def test_execute_times_out_runaway_programs(tmp_path, monkeypatch):
    """A non-terminating analysis must be killed at the wall-clock limit."""
    root = _repo(tmp_path, monkeypatch)
    (root / "input.txt").write_text("safe", encoding="utf-8")

    with pytest.raises(TimeoutError, match="timed out"):
        execute_program(
            root,
            "while True:\n    pass\nresult = 1",
            ["input.txt"],
            limits=ExecutionLimits(timeout_seconds=1),
        )


def test_execute_requires_json_serializable_result(tmp_path, monkeypatch):
    """The model-visible boundary must be deterministic JSON, not Python objects."""
    root = _repo(tmp_path, monkeypatch)
    (root / "input.txt").write_text("safe", encoding="utf-8")

    with pytest.raises(RuntimeError, match="not JSON serializable"):
        execute_program(root, "result = {1, 2, 3}", ["input.txt"])


def test_oversized_execution_result_is_exactly_recoverable(tmp_path, monkeypatch):
    """Large computed results should stay out of context without becoming lossy."""
    root = _repo(tmp_path, monkeypatch)
    (root / "input.txt").write_text("x" * 10, encoding="utf-8")
    store = RecoveryStore(root)

    result = execute_program(
        root,
        'result = {"rows": ["value-" + str(i) for i in range(1000)]}',
        ["input.txt"],
        recovery=store,
        limits=ExecutionLimits(max_result_bytes=1024),
    )

    assert result["truncated"] is True
    assert result["result"] is None
    assert result["recovery_handle"].startswith("tsr_")
    recovered = store.get(result["recovery_handle"])
    payload = json.loads(recovered.payload.decode("utf-8"))
    assert payload["rows"][0] == "value-0"
    assert payload["rows"][-1] == "value-999"
    assert recovered.metadata["transform"] == "out-of-context-execution-result"
