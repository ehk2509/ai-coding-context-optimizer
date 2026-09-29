"""Tests for provider cache-TTL learning from observed cache counters."""

import json

from acco.cache_ttl import (
    cache_ttl_report,
    learned_ttl_seconds,
    record_cache_observation,
)
from acco.efficiency.store import load_events
from acco.provider_usage import ProviderUsageObserver


def _root(tmp_path, monkeypatch):
    """Create an isolated project and state root."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_ttl_learning_requires_hit_lower_bound_and_exact_expiry_miss(
    tmp_path, monkeypatch
):
    """Qualified TTLs need repeated hits plus an exact-prefix post-hit miss."""
    root = _root(tmp_path, monkeypatch)

    record_cache_observation(
        root,
        provider="anthropic",
        model="claude-test",
        epoch_key="e1",
        reuse_mode="miss",
        cache_read_tokens=0,
        now=0,
    )
    record_cache_observation(
        root,
        provider="anthropic",
        model="claude-test",
        epoch_key="e1",
        reuse_mode="exact",
        cache_read_tokens=1000,
        now=100,
    )
    record_cache_observation(
        root,
        provider="anthropic",
        model="claude-test",
        epoch_key="e1",
        reuse_mode="exact",
        cache_read_tokens=1000,
        now=250,
    )
    record_cache_observation(
        root,
        provider="anthropic",
        model="claude-test",
        epoch_key="e1",
        reuse_mode="exact",
        cache_read_tokens=0,
        now=600,
    )

    report = cache_ttl_report(root)
    estimate = report["estimates"][0]

    assert estimate["qualified"] is True
    assert estimate["hit_lower_bound_seconds"] == 150
    assert estimate["expiry_upper_bound_seconds"] == 350
    assert estimate["learned_ttl_seconds"] == 350
    assert learned_ttl_seconds(root, "anthropic", "claude-test") == 350


def test_prefix_change_miss_never_qualifies_as_ttl_expiry(tmp_path, monkeypatch):
    """A changed prefix must not be mislabelled as provider-cache expiry."""
    root = _root(tmp_path, monkeypatch)

    record_cache_observation(
        root,
        provider="openai",
        model="gpt-test",
        epoch_key="e1",
        reuse_mode="exact",
        cache_read_tokens=900,
        now=100,
    )
    event = record_cache_observation(
        root,
        provider="openai",
        model="gpt-test",
        epoch_key="e1",
        reuse_mode="miss",
        cache_read_tokens=0,
        now=500,
    )

    assert event["reason"] == "prefix_change"
    estimate = cache_ttl_report(root)["estimates"][0]
    assert estimate["qualified"] is False
    assert estimate["expiry_upper_bound_seconds"] is None


def test_ttl_learning_is_isolated_by_provider_and_model(tmp_path, monkeypatch):
    """One provider/model's expiry evidence must not calibrate another model."""
    root = _root(tmp_path, monkeypatch)

    for now in (100, 200):
        record_cache_observation(
            root,
            provider="anthropic",
            model="model-a",
            epoch_key="e1",
            reuse_mode="exact",
            cache_read_tokens=500,
            now=now,
        )
    record_cache_observation(
        root,
        provider="anthropic",
        model="model-a",
        epoch_key="e1",
        reuse_mode="exact",
        cache_read_tokens=0,
        now=400,
    )
    record_cache_observation(
        root,
        provider="anthropic",
        model="model-b",
        epoch_key="e2",
        reuse_mode="exact",
        cache_read_tokens=500,
        now=100,
    )

    assert learned_ttl_seconds(root, "anthropic", "model-a") == 200
    assert learned_ttl_seconds(root, "anthropic", "model-b") is None


def test_missing_cache_counter_does_not_train_ttl(tmp_path, monkeypatch):
    """A missing cache counter must not be interpreted as an observed cache miss."""
    root = _root(tmp_path, monkeypatch)
    observer = ProviderUsageObserver(
        root,
        provider="openai",
        request_shape="openai-responses",
        streaming=False,
        content_type="application/json",
        cache_context={"epoch_key": "e1", "reuse_mode": "exact"},
        request_model="gpt-test",
    )
    observer.feed(
        json.dumps(
            {
                "model": "gpt-test",
                "usage": {"input_tokens": 100, "output_tokens": 20},
            }
        ).encode()
    )
    observer.finish()

    assert not any(
        event.get("kind") == "cache_ttl_observation"
        for event in load_events(root)
    )


def test_explicit_zero_cached_tokens_is_valid_miss_evidence(tmp_path, monkeypatch):
    """Provider-supplied cached_tokens=0 is evidence even though the value is zero."""
    root = _root(tmp_path, monkeypatch)
    observer = ProviderUsageObserver(
        root,
        provider="openai",
        request_shape="openai-responses",
        streaming=False,
        content_type="application/json",
        cache_context={"epoch_key": "e1", "reuse_mode": "exact"},
        request_model="gpt-test",
    )
    observer.feed(
        json.dumps(
            {
                "model": "gpt-test",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "input_tokens_details": {"cached_tokens": 0},
                },
            }
        ).encode()
    )
    observer.finish()

    observations = [
        event
        for event in load_events(root)
        if event.get("kind") == "cache_ttl_observation"
    ]
    assert len(observations) == 1
    assert observations[0]["cache_read_input_tokens"] == 0
