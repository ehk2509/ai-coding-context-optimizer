"""Tests for adaptive whole-context budget planning and integration."""

from __future__ import annotations

import json

import pytest

from acco.context_budget import CONTEXT_COMPONENTS, plan_context_budget
from acco.packing.contracts import ContextPack
from acco.repository_service import RepositoryContextService
from acco.runtime_config import settings_for
from acco.command_handlers.budget import context_budget_main


def test_context_budget_conserves_total_and_exposes_all_components():
    """Integer allocation must conserve the exact caller-owned context limit."""
    plan = plan_context_budget(
        "Implement a new authentication handler and update its tests.",
        total_tokens=12000,
        task="coding",
    )

    assert set(plan.allocations) == set(CONTEXT_COMPONENTS)
    assert sum(plan.allocations.values()) == 12000
    assert plan.allocations["source"] > plan.allocations["schemas"]
    assert plan.task == "coding"


def test_debugging_allocates_more_tool_result_budget_than_coding():
    """Task shape should materially change the whole-envelope allocation."""
    coding = plan_context_budget(
        "Implement the request handler.",
        total_tokens=10000,
        task="coding",
    )
    debugging = plan_context_budget(
        "Debug the request handler failure.",
        total_tokens=10000,
        task="debugging",
    )

    assert debugging.allocations["tool_results"] > coding.allocations["tool_results"]
    assert coding.allocations["source"] > debugging.allocations["source"]


def test_high_risk_context_increases_reserve():
    """Risk vocabulary should keep more unused headroom rather than spending it all."""
    ordinary = plan_context_budget(
        "Implement a small request helper.",
        total_tokens=10000,
        task="coding",
    )
    risky = plan_context_budget(
        "Implement a production authentication security migration.",
        total_tokens=10000,
        task="coding",
    )

    assert risky.risk_level == "high"
    assert risky.allocations["reserve"] > ordinary.allocations["reserve"]


def test_observed_small_components_return_unused_budget_to_source():
    """Known small demands should not strand tokens in empty context categories."""
    baseline = plan_context_budget(
        "Plan a multi-module refactor.",
        total_tokens=10000,
        task="planning",
    )
    observed = plan_context_budget(
        "Plan a multi-module refactor.",
        total_tokens=10000,
        task="planning",
        observed_tokens={
            "memory": 50,
            "history": 100,
            "tool_results": 0,
            "schemas": 0,
        },
    )

    assert observed.allocations["memory"] == 50
    assert observed.allocations["history"] == 100
    assert observed.allocations["tool_results"] == 0
    assert observed.allocations["schemas"] == 0
    assert observed.allocations["source"] > baseline.allocations["source"]
    assert sum(observed.allocations.values()) == 10000


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"total_tokens": 999}, "at least 1000"),
        (
            {"total_tokens": 10000, "observed_tokens": {"unknown": 1}},
            "unknown observed context component",
        ),
        (
            {"total_tokens": 10000, "observed_tokens": {"memory": -1}},
            "must be nonnegative",
        ),
    ],
)
def test_context_budget_rejects_invalid_contracts(kwargs, message):
    """Invalid budgets should fail before influencing retrieval/provider behavior."""
    with pytest.raises(ValueError, match=message):
        plan_context_budget("task", **kwargs)


def test_runtime_config_context_budget_is_opt_in(tmp_path, monkeypatch):
    """Existing projects stay unchanged unless the new planner is enabled."""
    monkeypatch.delenv("ACCO_CONTEXT_BUDGET", raising=False)
    monkeypatch.delenv("ACCO_CONTEXT_BUDGET_TOTAL_TOKENS", raising=False)

    assert settings_for(tmp_path).context_budget_enabled is False
    assert settings_for(tmp_path).context_budget_total_tokens == 12000

    (tmp_path / ".acco.toml").write_text(
        "[context_budget]\n"
        "enabled = true\n"
        "total_tokens = 9000\n",
        encoding="utf-8",
    )
    configured = settings_for(tmp_path)
    assert configured.context_budget_enabled is True
    assert configured.context_budget_total_tokens == 9000


def test_repository_service_uses_only_source_slice_when_enabled(
    tmp_path, monkeypatch
):
    """Whole-context planning should constrain source packing, not rename max_tokens."""
    (tmp_path / ".acco.toml").write_text(
        "[context_budget]\n"
        "enabled = true\n"
        "total_tokens = 10000\n",
        encoding="utf-8",
    )
    captured = {}

    class FakeIndex:
        records = {}
        reparsed = 0
        reused = 0

    def fake_build(*args, **kwargs):
        captured["max_tokens"] = kwargs["max_tokens"]
        return ContextPack(
            text="source",
            estimated_tokens=1,
            scanned_files=0,
            selected_files=[],
            ranked=[],
        )

    service = RepositoryContextService(tmp_path, index=FakeIndex())
    monkeypatch.setattr("acco.repository_service.build_context_pack", fake_build)
    pack = service.build_context(
        "Implement the handler.",
        max_tokens=9000,
    )

    expected = plan_context_budget(
        "Implement the handler.",
        total_tokens=10000,
    )
    assert captured["max_tokens"] == expected.allocations["source"]
    assert pack.context_budget_plan == expected.to_dict()


def test_repository_service_default_keeps_explicit_source_budget(
    tmp_path, monkeypatch
):
    """Disabled whole-context planning must preserve the historical source cap."""
    captured = {}

    class FakeIndex:
        records = {}
        reparsed = 0
        reused = 0

    def fake_build(*args, **kwargs):
        captured["max_tokens"] = kwargs["max_tokens"]
        return ContextPack(
            text="source",
            estimated_tokens=1,
            scanned_files=0,
            selected_files=[],
            ranked=[],
        )

    service = RepositoryContextService(tmp_path, index=FakeIndex())
    monkeypatch.setattr("acco.repository_service.build_context_pack", fake_build)
    pack = service.build_context("Implement the handler.", max_tokens=4321)

    assert captured["max_tokens"] == 4321
    assert pack.context_budget_plan is None


def test_context_budget_cli_json(capsys):
    """CLI should expose the same deterministic planner used by runtime paths."""
    assert (
        context_budget_main(
            [
                "Debug the failing parser.",
                "--total-tokens",
                "8000",
                "--observed-tool-results",
                "2500",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_tokens"] == 8000
    assert payload["task"] == "debugging"
    assert sum(payload["allocations"].values()) == 8000
    assert payload["observed_tokens"]["tool_results"] == 2500
