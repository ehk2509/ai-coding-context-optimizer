"""Recovery v2 integrity, typed-object, and capacity tests."""

from __future__ import annotations

import sqlite3

import pytest

from acco.recovery import (
    RecoveryCapacityError,
    RecoveryIntegrityError,
    RecoveryStore,
)


def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_typed_recovery_supports_exact_json_pointer_subtrees(tmp_path, monkeypatch):
    """Typed recovery should fetch only the requested JSON subtree."""
    root = _root(tmp_path, monkeypatch)
    store = RecoveryStore(root)
    value = {
        "failures": [
            {"name": "alpha", "message": "first"},
            {"name": "beta", "message": "second"},
        ],
        "summary": {"passed": 8, "failed": 2},
    }

    handle = store.put_object(value, object_type="analysis-result")
    selected = store.select(f"tsr://{handle}/failures/1")

    assert handle.startswith("tsr_obj_")
    assert selected["value"] == {"name": "beta", "message": "second"}
    assert selected["object_type"] == "analysis-result"
    assert store.get_object(handle).value == value


def test_recovery_dependencies_must_exist_and_are_reported(tmp_path, monkeypatch):
    """Typed records may depend on earlier exact recovery without dangling refs."""
    root = _root(tmp_path, monkeypatch)
    store = RecoveryStore(root)
    source = store.put("exact source")
    typed = store.put_object(
        {"answer": 42},
        dependencies=[source],
    )

    assert store.dependencies(typed) == [source]
    assert store.info(typed)["dependencies"] == [source]

    with pytest.raises(KeyError):
        store.put_object({"other": True}, dependencies=["tsr_" + "0" * 32])


def test_recovery_capacity_never_evicts_existing_handles(tmp_path, monkeypatch):
    """Capacity refusal must preserve previously issued exact handles."""
    root = _root(tmp_path, monkeypatch)
    store = RecoveryStore(root, capacity_bytes=32)
    first = store.put(b"a" * 20)

    with pytest.raises(RecoveryCapacityError):
        store.put(b"b" * 20)

    assert store.get(first).payload == b"a" * 20
    assert store.stats()["records"] == 1


def test_recovery_detects_tampered_exact_payload(tmp_path, monkeypatch):
    """Digest verification must fail instead of returning corrupted source bytes."""
    root = _root(tmp_path, monkeypatch)
    store = RecoveryStore(root)
    handle = store.put(b"original")

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE recovery SET payload = ? WHERE handle = ?",
            (sqlite3.Binary(b"tampered"), handle),
        )
        connection.commit()

    with pytest.raises(RecoveryIntegrityError, match="integrity"):
        store.get(handle)
