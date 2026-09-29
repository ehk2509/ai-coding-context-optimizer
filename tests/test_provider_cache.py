"""Provider cache planning and multi-conversation prefix epoch tests."""

from acco.prefix_cache import PrefixPlan, observe_prefix, prefix_status
from acco.provider_cache import (
    apply_provider_cache_plan,
    observed_cache_evidence,
    plan_provider_cache,
)


def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_prefix_epochs_do_not_poison_interleaved_conversations(tmp_path, monkeypatch):
    """Distinct system/tool surfaces should keep independent reuse anchors."""
    root = _root(tmp_path, monkeypatch)
    main = {
        "system": "main-agent",
        "tools": [{"name": "read"}],
        "messages": [{"role": "user", "content": "one"}],
    }
    subagent = {
        "system": "review-agent",
        "tools": [{"name": "grep"}],
        "messages": [{"role": "user", "content": "review"}],
    }

    first = observe_prefix(root, "anthropic", main)
    other = observe_prefix(root, "anthropic", subagent)
    main_again = observe_prefix(
        root,
        "anthropic",
        {
            **main,
            "messages": [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ],
        },
    )

    assert first.epoch_key != other.epoch_key
    assert main_again.epoch_key == first.epoch_key
    assert main_again.previous_fingerprint == first.fingerprint
    assert prefix_status(root)["epoch_counts"]["anthropic"] == 2


def test_cache_planner_separates_economics_from_observation():
    """A favorable plan is not provider-observed cache evidence."""
    prefix = PrefixPlan(
        fingerprint="abc",
        stable_tokens=20_000,
        stable_bytes=80_000,
        components=("system", "tools"),
        previous_fingerprint=None,
        reused=False,
        epoch_key="conversation-a",
    )

    plan = plan_provider_cache("anthropic", prefix, expected_reuses=2)
    evidence = observed_cache_evidence(
        "anthropic",
        {"cache_read_input_tokens": 12_000},
    )

    assert plan.eligible is True
    assert plan.evidence_basis == "planned"
    assert plan.relative_savings is not None and plan.relative_savings > 0
    assert evidence["cache_observed"] is True
    assert evidence["evidence_basis"] == "provider-observed"


def test_anthropic_cache_application_preserves_existing_controls():
    """Cache application should add at most one safe breakpoint."""
    prefix = PrefixPlan(
        fingerprint="abc",
        stable_tokens=20_000,
        stable_bytes=80_000,
        components=("system", "tools"),
        previous_fingerprint=None,
        reused=False,
        epoch_key="conversation-a",
    )
    plan = plan_provider_cache("anthropic", prefix, expected_reuses=2)
    body = {
        "model": "claude-test",
        "system": [{"type": "text", "text": "stable instructions"}],
        "tools": [
            {"name": "read", "description": "read a file", "input_schema": {"type": "object"}}
        ],
        "messages": [{"role": "user", "content": "fix it"}],
    }

    transformed, applied, reason = apply_provider_cache_plan(body, plan)

    assert applied is True
    assert reason == "anthropic_tool_breakpoint"
    assert transformed["tools"][-1]["cache_control"] == {"type": "ephemeral"}

    again, applied_again, reason_again = apply_provider_cache_plan(transformed, plan)
    assert applied_again is False
    assert reason_again == "existing_cache_control_preserved"


def test_openai_cache_plan_is_observational_only():
    """Automatic provider caching should not cause request-shape mutation."""
    prefix = PrefixPlan(
        fingerprint="abc",
        stable_tokens=10_000,
        stable_bytes=40_000,
        components=("instructions", "tools"),
        previous_fingerprint=None,
        reused=False,
        epoch_key="conversation-a",
    )
    plan = plan_provider_cache("openai", prefix, expected_reuses=2)
    body = {"model": "gpt-test", "input": "hello"}

    transformed, applied, reason = apply_provider_cache_plan(body, plan)

    assert transformed == body
    assert applied is False
    assert reason == "automatic_requires_no_inline_mutation"
