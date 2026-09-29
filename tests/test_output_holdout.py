"""Tests for measured conversation-stable output shaping holdouts."""

from __future__ import annotations

from acco.output_holdout import (
    apply_output_holdout,
    holdout_epoch_key,
    output_holdout_report,
    record_output_holdout_observation,
)
from acco.provider_boundary import ProviderRequestProfile


def _root(tmp_path, monkeypatch):
    """Create an isolated project and state root."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def _profile():
    """Return a minimal Anthropic provider profile."""
    return ProviderRequestProfile("anthropic", "anthropic-messages", False)


def _body(session_id: str):
    """Return an eligible provider request for output shaping."""
    return {
        "model": "claude-test",
        "max_tokens": 3000,
        "metadata": {"session_id": session_id},
        "messages": [{"role": "user", "content": "Fix the failing auth test."}],
    }


def _decision_for_arm(root, arm: str):
    """Find one deterministic conversation assignment for the requested arm."""
    profile = _profile()
    for index in range(500):
        body = _body(f"session-{index}")
        epoch = holdout_epoch_key(body, profile)
        decision = apply_output_holdout(
            root,
            body,
            profile,
            prompt="Fix the failing auth test.",
            epoch_key=epoch,
            enabled=True,
            control_rate=0.5,
        )
        if decision.arm == arm:
            return body, decision
    raise AssertionError(f"could not find {arm} assignment")


def test_holdout_assignment_is_stable_and_control_is_unchanged(tmp_path, monkeypatch):
    """The same conversation must stay in one arm and control must be byte-semantic."""
    root = _root(tmp_path, monkeypatch)
    body, first = _decision_for_arm(root, "control")
    original = dict(body)
    epoch = first.epoch_key

    second_body = _body(body["metadata"]["session_id"])
    second = apply_output_holdout(
        root,
        second_body,
        _profile(),
        prompt="Fix the failing auth test.",
        epoch_key=epoch,
        enabled=True,
        control_rate=0.5,
    )

    assert first.arm == second.arm == "control"
    assert first.eligible is True
    assert first.applied is False
    assert body["max_tokens"] == original["max_tokens"]
    assert second_body["max_tokens"] == 3000


def test_treatment_clamps_only_existing_output_limit(tmp_path, monkeypatch):
    """Treatment should clamp an existing provider limit and never invent one."""
    root = _root(tmp_path, monkeypatch)
    body, decision = _decision_for_arm(root, "treatment")

    assert decision.eligible is True
    assert decision.applied is True
    assert body["max_tokens"] == decision.budget_tokens
    assert decision.budget_tokens < 3000

    no_limit = {
        "model": "claude-test",
        "metadata": {"session_id": "without-limit"},
        "messages": [{"role": "user", "content": "Fix this bug."}],
    }
    epoch = holdout_epoch_key(no_limit, _profile())
    missing = apply_output_holdout(
        root,
        no_limit,
        _profile(),
        prompt="Fix this bug.",
        epoch_key=epoch,
        enabled=True,
        control_rate=0.5,
    )
    assert missing.eligible is False
    assert missing.applied is False
    assert "max_tokens" not in no_limit


def test_measured_report_uses_conversation_level_matched_strata(tmp_path, monkeypatch):
    """Only eligible randomized observations should produce measured reduction."""
    root = _root(tmp_path, monkeypatch)

    for index, tokens in enumerate((1000, 1100, 900, 1050), start=1):
        record_output_holdout_observation(
            root,
            provider="anthropic",
            model="claude-test",
            output_tokens=tokens,
            decision={
                "experiment": "output-holdout-v1",
                "enabled": True,
                "eligible": True,
                "arm": "control",
                "epoch_key": f"c-{index}",
                "task": "coding",
                "mode": "normal",
                "applied": False,
                "budget_tokens": 600,
            },
        )
    for index, tokens in enumerate((600, 650, 550, 620), start=1):
        record_output_holdout_observation(
            root,
            provider="anthropic",
            model="claude-test",
            output_tokens=tokens,
            decision={
                "experiment": "output-holdout-v1",
                "enabled": True,
                "eligible": True,
                "arm": "treatment",
                "epoch_key": f"t-{index}",
                "task": "coding",
                "mode": "normal",
                "applied": True,
                "budget_tokens": 600,
            },
        )

    report = output_holdout_report(root, bootstrap_samples=200)

    reduction = report["measured_output_token_reduction"]
    assert reduction is not None
    assert 0.35 < reduction < 0.45
    assert report["matched_epoch_weight"] == 4
    assert report["ci95"] is not None


def test_disabled_or_ineligible_observation_is_not_measurement(tmp_path, monkeypatch):
    """Disabled/ineligible requests must not contaminate randomized evidence."""
    root = _root(tmp_path, monkeypatch)

    record_output_holdout_observation(
        root,
        provider="anthropic",
        model="claude-test",
        output_tokens=1,
        decision={
            "experiment": "output-holdout-v1",
            "enabled": False,
            "eligible": True,
            "arm": "control",
            "epoch_key": "disabled",
            "task": "coding",
            "mode": "normal",
            "applied": False,
            "budget_tokens": 600,
        },
    )
    record_output_holdout_observation(
        root,
        provider="anthropic",
        model="claude-test",
        output_tokens=1,
        decision={
            "experiment": "output-holdout-v1",
            "enabled": True,
            "eligible": False,
            "arm": "treatment",
            "epoch_key": "ineligible",
            "task": "coding",
            "mode": "normal",
            "applied": False,
            "budget_tokens": 600,
        },
    )

    report = output_holdout_report(root, bootstrap_samples=20)
    assert report["measured_output_token_reduction"] is None
    assert report["strata"] == []
