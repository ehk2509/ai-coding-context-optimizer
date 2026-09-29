"""Tests for local learned structured tool-field importance."""

from __future__ import annotations

import json

from acco.context_router import compact_json_value, route_context
from acco.recovery import RecoveryStore
from acco.sdk import AccoEngine
from acco.tool_field_learning import (
    field_hints,
    field_learning_path,
    normalize_tool_key,
    observe_tool_json,
    record_field_retrieval,
)


def _root(tmp_path, monkeypatch):
    """Create an isolated project and ACCO state root."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def _payload(secret: str = "never-store-this-value"):
    """Return a large structured payload with one retrievable detail field."""
    return {
        "items": [
            {
                **{f"noise_{index}": f"value-{row}-{index}" for index in range(20)},
                "detail": f"detail-{row}",
                "secret_value": secret,
            }
            for row in range(24)
        ]
    }


def test_field_learning_stores_paths_and_counts_not_values(tmp_path, monkeypatch):
    """The learner must never persist JSON field values."""
    root = _root(tmp_path, monkeypatch)
    payload = _payload()

    observe_tool_json(root, "search_tool", payload)
    raw = field_learning_path(root).read_bytes()

    assert b"never-store-this-value" not in raw
    assert b"detail-0" not in raw
    assert b"search_tool" in raw
    assert b"detail" in raw


def test_retrieval_threshold_produces_learned_field_hint(tmp_path, monkeypatch):
    """Repeated selective recovery should promote only evidence-backed fields."""
    root = _root(tmp_path, monkeypatch)
    payload = _payload()
    for _ in range(3):
        observe_tool_json(root, "search_tool", payload)

    assert field_hints(root, "search_tool") == []

    record_field_retrieval(root, "search_tool", "/items/0/detail")
    record_field_retrieval(root, "search_tool", "/items/1/detail")
    hints = field_hints(root, "search_tool")

    assert any(item["field_path"] == "$/items/*/detail" for item in hints)
    assert any(item["retrievals"] == 2 for item in hints)


def test_selective_sdk_recovery_feeds_learning_loop(tmp_path, monkeypatch):
    """Typed recovery usage should become field importance evidence."""
    root = _root(tmp_path, monkeypatch)
    engine = AccoEngine(root)
    text = json.dumps(_payload())

    typed = None
    for _ in range(3):
        result = engine.optimize_context(
            text,
            tool_key="search_tool",
            min_reduction=0.0,
        )
        typed = result["metadata"].get("typed_recovery_handle")
        assert typed is not None

    engine.recover(typed, pointer="/items/0/detail")
    engine.recover(typed, pointer="/items/1/detail")

    hints = field_hints(root, "search_tool")
    assert any(item["field_path"] == "$/items/*/detail" for item in hints)


def test_learned_field_survives_wide_object_compaction(tmp_path, monkeypatch):
    """Evidence-backed fields should survive structural pruning, not bypass recovery."""
    root = _root(tmp_path, monkeypatch)
    payload = _payload()
    for _ in range(3):
        observe_tool_json(root, "search_tool", payload)
    record_field_retrieval(root, "search_tool", "/items/0/detail")
    record_field_retrieval(root, "search_tool", "/items/1/detail")

    important = {"detail"}
    compact = compact_json_value(payload, important_fields=important)
    rendered = json.dumps(compact)

    assert "detail" in rendered
    assert "_acco_omitted_fields" in rendered


def test_unsafe_tool_identity_is_hashed():
    """Arbitrary tool labels should not become persisted identifier text."""
    key = normalize_tool_key("tool password=super-secret with spaces")

    assert key.startswith("tool-")
    assert "super-secret" not in key
