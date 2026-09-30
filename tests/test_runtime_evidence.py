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
