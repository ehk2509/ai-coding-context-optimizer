from pathlib import Path
from types import SimpleNamespace

import acco.runtime_evidence as runtime_evidence
from acco.efficiency.store import append_event, update_snapshot
from acco.runtime_evidence import aggregate_runtime_activation


def test_aggregate_runtime_activation_reports_coverage_and_surfaces():
    runs = [
        {"condition": "baseline"},
        {
            "condition": "enabled",
            "runtime_activation": {
                "event_kinds": {"provider_request": 2, "cache_ttl_observation": 1},
                "acco_tool_calls": {"mcp__acco__execute": 1},
                "surface_activity": {
                    "provider_observability": True,
                    "cache_ttl_learning": True,
                    "out_of_context_execution": True,
                },
                "any_activity": True,
            },
        },
        {
            "condition": "enabled",
            "runtime_activation": {
                "event_kinds": {"provider_request": 1},
                "acco_tool_calls": {},
                "surface_activity": {
                    "provider_observability": True,
                    "cache_ttl_learning": False,
                    "out_of_context_execution": False,
                },
                "any_activity": True,
            },
        },
    ]

    report = aggregate_runtime_activation(runs)

    assert report["enabled_runs"] == 2
    assert report["runs_with_activation_evidence"] == 2
    assert report["coverage_complete"] is True
    assert report["runs_with_any_activity"] == 2
    assert report["event_kinds"]["provider_request"] == 3
    assert report["surface_runs"]["provider_observability"] == 2
    assert report["surface_runs"]["cache_ttl_learning"] == 1
    assert report["acco_tool_calls"]["mcp__acco__execute"] == 1


def test_aggregate_runtime_activation_exposes_missing_collection():
    report = aggregate_runtime_activation(
        [{"condition": "enabled"}, {"condition": "baseline"}]
    )

    assert report["enabled_runs"] == 1
    assert report["runs_with_activation_evidence"] == 0
    assert report["coverage_complete"] is False
    assert report["surface_runs"] == {}


def test_collect_runtime_activation_uses_child_project_identity(tmp_path, monkeypatch):
    state_root = tmp_path / "state"
    child_root = Path("/testbed")
    host_root = tmp_path / "host-worktree"
    host_root.mkdir()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")

    monkeypatch.setenv("ACCO_STATE_DIR", str(state_root))
    append_event(
        child_root,
        {"kind": "provider_request", "feature": "provider_boundary"},
    )

    def seed_contract(payload):
        payload["sessions"] = {
            "abc": {
                "contract": {"goal": "fix regression"},
            }
        }
        payload["last_session"] = "abc"

    update_snapshot(child_root, seed_contract)
    monkeypatch.setattr(
        runtime_evidence,
        "analyze",
        lambda *_args, **_kwargs: SimpleNamespace(calls=[]),
    )

    report = runtime_evidence.collect_runtime_activation(
        host_root,
        transcript,
        state_root=state_root,
        state_project_root=child_root,
    )

    assert report["event_kinds"]["provider_request"] == 1
    assert report["session_state"]["task_contract_sessions"] == 1
    assert report["surface_activity"]["task_contract"] is True
