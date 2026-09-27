"""Tests for broader provider-boundary interception and usage evidence."""

from __future__ import annotations

import json

from acco.efficiency.store import load_events
from acco.prefix_cache import observe_prefix
from acco.provider_boundary import detect_provider_request
from acco.provider_proxy import ProviderProxyConfig, transform_request_bytes
from acco.provider_transform import transform_provider_request
from acco.provider_usage import ProviderUsageObserver, normalize_provider_usage
from acco.recovery import RecoveryStore
from acco.tool_schema import compress_tool_catalog


def _noise(prefix: str, rows: int = 180) -> str:
    """Return a large deterministic tool payload."""
    return "\n".join(
        f"{prefix} {index} " + "x" * 80 for index in range(rows)
    )


def test_provider_auto_detection_distinguishes_common_api_shapes():
    """Auto mode should recognize Anthropic, OpenAI, and Gemini boundaries."""
    assert detect_provider_request(
        "auto",
        {"messages": []},
        path="/v1/chat/completions",
    ).shape == "openai-chat"
    assert detect_provider_request(
        "auto",
        {"input": "hello"},
        path="/v1/responses",
    ).shape == "openai-responses"
    assert detect_provider_request(
        "auto",
        {"messages": [], "max_tokens": 100, "system": "x"},
        path="/v1/messages",
    ).provider == "anthropic"
    assert detect_provider_request(
        "auto",
        {"contents": []},
        path="/v1beta/models/gemini:streamGenerateContent",
    ).streaming is True


def test_openai_responses_compresses_only_historical_function_output(
    tmp_path, monkeypatch
):
    """OpenAI Responses current user input must remain byte-for-byte unchanged."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    current = "Please debug the authentication failure without changing scope."
    historical = _noise("pytest")
    body = {
        "model": "gpt-test",
        "input": [
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": historical,
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": current}],
            },
        ],
    }

    result = transform_provider_request(
        root,
        "auto",
        body,
        request_path="/v1/responses",
        tool_result_min_tokens=100,
        compress_schemas=False,
        prefix_tracking=False,
    )

    assert result.profile.provider == "openai"
    assert result.profile.shape == "openai-responses"
    assert result.changed is True
    assert result.transformed_segments == 1
    assert result.body["input"][1] == body["input"][1]
    handle = result.recovery_handles[0]
    assert RecoveryStore(root).get(handle).payload.decode() == historical
    assert result.metadata()["policy"] == "retrieval-first-historical-only"


def test_gemini_function_response_preserves_structure_and_user_prompt(
    tmp_path, monkeypatch
):
    """Gemini nested functionResponse strings may shrink without rewriting structure."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    current = "Find the exact failing handler."
    historical = _noise("browser")
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": "browser_snapshot",
                            "response": {
                                "status": "ok",
                                "output": historical,
                            },
                        }
                    }
                ],
            },
            {
                "role": "user",
                "parts": [{"text": current}],
            },
        ]
    }

    result = transform_provider_request(
        root,
        "auto",
        body,
        request_path="/v1beta/models/gemini-2:generateContent",
        tool_result_min_tokens=100,
        compress_schemas=False,
        prefix_tracking=False,
    )

    response = result.body["contents"][0]["parts"][0]["functionResponse"]["response"]
    assert result.profile.provider == "gemini"
    assert result.changed is True
    assert isinstance(response, dict)
    assert response["status"] == "ok"
    assert response["output"] != historical
    assert result.body["contents"][1]["parts"][0]["text"] == current
    assert RecoveryStore(root).get(result.recovery_handles[0]).payload.decode() == historical


def test_nested_openai_and_gemini_tool_schemas_compress_with_exact_recovery(
    tmp_path, monkeypatch
):
    """Provider wrapper shapes should reuse the same conservative schema compressor."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    store = RecoveryStore(root)
    verbose = (
        "Search repository evidence for the requested symbol. " * 18
        + "The path must be absolute. Exactly one query is required."
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_repo",
                "description": verbose,
                "parameters": {
                    "type": "object",
                    "title": "drop",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": verbose,
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "functionDeclarations": [
                {
                    "name": "read_repo",
                    "description": verbose,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": verbose}
                        },
                        "required": ["path"],
                    },
                }
            ]
        },
    ]

    result = compress_tool_catalog(tools, recovery=store, min_reduction=0.0)

    assert result.changed is True
    assert result.recovery_handle
    openai = result.value[0]["function"]
    gemini = result.value[1]["functionDeclarations"][0]
    assert len(openai["description"]) < len(verbose)
    assert "title" not in openai["parameters"]
    assert len(gemini["description"]) < len(verbose)
    assert json.loads(store.get(result.recovery_handle).payload) == tools


def test_proxy_transform_auto_detects_provider_from_request_path(
    tmp_path, monkeypatch
):
    """Transparent proxy mode should not require duplicating provider config."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    config = ProviderProxyConfig(
        root=root,
        upstream="https://api.openai.example",
        provider="auto",
        prefix_tracking=False,
    )
    raw = json.dumps(
        {
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": _noise("tool"),
                }
            ]
        }
    ).encode()

    result = transform_request_bytes(
        config,
        raw,
        content_type="application/json",
        request_path="/v1/responses",
    )

    assert result.metadata["request"]["provider"] == "openai"
    assert result.metadata["request"]["shape"] == "openai-responses"


def test_proxy_noop_preserves_exact_json_request_bytes(tmp_path, monkeypatch):
    """No accepted transform means the upstream receives the original bytes."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    config = ProviderProxyConfig(
        root=root,
        upstream="https://api.openai.example",
        provider="auto",
        prefix_tracking=False,
    )
    raw = b'{\n  "messages": [{"role": "user", "content": "hello"}],\n  "temperature": 0\n}\n'

    result = transform_request_bytes(
        config,
        raw,
        content_type="application/json",
        request_path="/v1/chat/completions",
    )

    assert result.metadata["changed"] is False
    assert result.body == raw


def test_provider_usage_normalization_covers_all_three_providers():
    """Provider-specific counters should map into one content-free schema."""
    assert normalize_provider_usage(
        "anthropic",
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_read_input_tokens": 40,
            }
        },
    ) == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_input_tokens": 40,
    }
    assert normalize_provider_usage(
        "openai",
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "prompt_tokens_details": {"cached_tokens": 40},
            }
        },
    ) == {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "cache_read_input_tokens": 40,
    }
    assert normalize_provider_usage(
        "gemini",
        {
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 20,
                "cachedContentTokenCount": 40,
                "totalTokenCount": 120,
            }
        },
    ) == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_input_tokens": 40,
        "total_tokens": 120,
    }


def test_streaming_usage_observer_forwards_no_content_into_event_store(
    tmp_path, monkeypatch
):
    """SSE observation should persist counters/model only, never response text."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    observer = ProviderUsageObserver(
        root,
        provider="openai",
        request_shape="openai-responses",
        streaming=True,
        content_type="text/event-stream",
    )
    observer.feed(
        b'data: {"type":"response.output_text.delta","delta":"SECRET RESPONSE"}\n'
    )
    observer.feed(
        b'data: {"type":"response.completed","response":{"model":"gpt-test",'
        b'"usage":{"input_tokens":120,"output_tokens":30,"total_tokens":150}}}\n\n'
    )
    event = observer.finish()

    assert event["input_tokens"] == 120
    assert event["output_tokens"] == 30
    assert event["model"] == "gpt-test"
    stored = load_events(root)[-1]
    assert stored["kind"] == "provider_usage"
    assert "SECRET RESPONSE" not in json.dumps(stored)


def test_json_usage_observer_handles_gemini_array_response(tmp_path, monkeypatch):
    """Gemini streamed JSON arrays should yield the largest cumulative usage."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    observer = ProviderUsageObserver(
        root,
        provider="gemini",
        request_shape="gemini-generate-content",
        streaming=False,
        content_type="application/json",
    )
    observer.feed(
        json.dumps(
            [
                {"usageMetadata": {"promptTokenCount": 90, "candidatesTokenCount": 5}},
                {
                    "modelVersion": "gemini-test",
                    "usageMetadata": {
                        "promptTokenCount": 90,
                        "candidatesTokenCount": 12,
                        "totalTokenCount": 102,
                    },
                },
            ]
        ).encode()
    )

    event = observer.finish()

    assert event["input_tokens"] == 90
    assert event["output_tokens"] == 12
    assert event["total_tokens"] == 102
    assert event["model"] == "gemini-test"


def test_provider_history_dedup_is_exact_recoverable_and_keeps_current_prompt(
    tmp_path, monkeypatch
):
    """Repeated historical tool bytes should be sent once, never summarized twice."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    repeated = _noise("pytest", rows=220)
    current = "Fix the failing parser without changing public behavior."
    body = {
        "model": "gpt-test",
        "input": [
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": repeated,
            },
            {
                "type": "function_call_output",
                "call_id": "c2",
                "output": repeated,
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": current}],
            },
        ],
    }

    result = transform_provider_request(
        root,
        "auto",
        body,
        request_path="/v1/responses",
        compress_schemas=False,
        compress_tool_results=False,
        deduplicate_history=True,
        tool_result_min_tokens=100,
        prefix_tracking=False,
    )

    assert result.changed is True
    assert result.deduplicated_segments == 1
    assert result.estimated_duplicate_tokens_saved > 0
    assert result.body["input"][0]["output"] == repeated
    duplicate = result.body["input"][1]["output"]
    assert "exact duplicate tool result omitted" in duplicate
    assert result.body["input"][2] == body["input"][2]
    handle = result.recovery_handles[0]
    assert handle in duplicate
    assert RecoveryStore(root).get(handle).payload.decode() == repeated
    saving = [
        event
        for event in load_events(root)
        if event.get("kind") == "saving"
        and event.get("feature") == "provider_history_dedup"
    ]
    assert saving[-1]["estimated_tokens_saved"] == result.estimated_duplicate_tokens_saved
    assert saving[-1]["segments"] == 1


def _safe_routing_calibration() -> dict:
    """Return one runtime-valid exact bucket for Sonnet -> Haiku debugging."""
    return {
        "schema": 1,
        "source_sha256": "test-calibration",
        "recommendations": [
            {
                "task": "debugging",
                "complexity_tier": "simple",
                "risk_level": "normal",
                "baseline_model": "claude-sonnet-5",
                "candidate_model": "claude-haiku-4-5",
                "pairs": 10,
                "tasks": 5,
                "baseline_success_rate": 1.0,
                "candidate_success_rate": 1.0,
                "regressions": 0,
                "success_preserved": True,
                "quality_preserved": True,
                "actual_models_verified": True,
                "blinded_quality": True,
                "independent_verification": True,
                "baseline_matches_static_policy": True,
                "candidate_strictly_cheaper": True,
                "mean_weighted_quality_delta": 0.0,
                "mean_correctness_delta": 0.0,
                "mean_safety_delta": 0.0,
            }
        ],
    }


def test_provider_model_downgrade_requires_quality_gated_calibration(
    tmp_path, monkeypatch
):
    """Calibrated provider mode may apply an admitted cheaper exact bucket."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    calibration = root / ".acco.routing-calibration.json"
    calibration.write_text(json.dumps(_safe_routing_calibration()), encoding="utf-8")
    prompt = "Debug the failing request handler case 101."
    body = {
        "model": "claude-sonnet-5",
        "max_tokens": 800,
        "system": "You are a coding agent.",
        "messages": [{"role": "user", "content": prompt}],
    }

    result = transform_provider_request(
        root,
        "auto",
        body,
        request_path="/v1/messages",
        compress_schemas=False,
        compress_tool_results=False,
        deduplicate_history=False,
        prefix_tracking=False,
        model_routing_mode="calibrated",
    )

    assert result.changed is True
    assert result.body["model"] == "claude-haiku-4-5"
    assert result.model_routing["applied"] is True
    assert result.model_routing["calibration_applied"] is True
    assert result.model_routing["from_model"] == "claude-sonnet-5"
    assert result.model_routing["to_model"] == "claude-haiku-4-5"


def test_provider_model_downgrade_never_applies_static_heuristic_alone(
    tmp_path, monkeypatch
):
    """Missing calibration must leave the caller's model unchanged."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    prompt = "Debug the failing request handler case 102."
    body = {
        "model": "claude-sonnet-5",
        "max_tokens": 800,
        "system": "You are a coding agent.",
        "messages": [{"role": "user", "content": prompt}],
    }

    result = transform_provider_request(
        root,
        "auto",
        body,
        request_path="/v1/messages",
        compress_schemas=False,
        compress_tool_results=False,
        deduplicate_history=False,
        prefix_tracking=False,
        model_routing_mode="calibrated",
    )

    assert result.body["model"] == "claude-sonnet-5"
    assert result.model_routing["applied"] is False
    assert result.model_routing["calibration_applied"] is False


def test_prefix_tracking_recognizes_append_only_conversation_extension(
    tmp_path, monkeypatch
):
    """Appending turns should preserve cache-prefix reuse without storing content."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    first = {
        "system": "stable",
        "messages": [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "answer one"},
            {"role": "user", "content": "two"},
        ],
    }
    second = {
        "system": "stable",
        "messages": [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "answer one"},
            {"role": "user", "content": "two"},
            {"role": "assistant", "content": "answer two"},
            {"role": "user", "content": "three"},
        ],
    }

    initial = observe_prefix(root, "anthropic", first)
    extended = observe_prefix(root, "anthropic", second)

    assert initial.reused is False
    assert extended.reused is True
    assert extended.reuse_mode == "extended"
    assert extended.element_count > initial.element_count



def test_provider_context_budget_skips_schema_compression_when_slice_fits(
    tmp_path, monkeypatch
):
    """Budget mode should not compress schemas merely because compression is available."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    description = "Search exact repository evidence. " * 20
    tools = [
        {
            "name": "search_repo",
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": description}
                },
                "required": ["query"],
            },
        }
    ]
    body = {
        "system": "coding",
        "messages": [{"role": "user", "content": "Explain this helper."}],
        "tools": tools,
    }

    result = transform_provider_request(
        root,
        "anthropic",
        body,
        compress_tool_results=False,
        deduplicate_history=False,
        prefix_tracking=False,
        context_budget_total_tokens=100000,
    )

    assert result.body == body
    assert result.changed is False
    assert result.schema_recovery_handle is None
    assert result.context_budget is not None
    assert result.context_budget["observed_tokens"]["schemas"] > 0


def test_provider_context_budget_compresses_schema_when_slice_is_over_budget(
    tmp_path, monkeypatch
):
    """An over-budget schema slice should activate the existing recoverable compressor."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    description = "Search exact repository evidence. " * 80
    tools = [
        {
            "name": "search_repo",
            "description": description,
            "input_schema": {
                "type": "object",
                "title": "drop",
                "properties": {
                    "query": {"type": "string", "description": description}
                },
                "required": ["query"],
            },
        }
    ]
    body = {
        "system": "coding",
        "messages": [{"role": "user", "content": "Implement this tool integration."}],
        "tools": tools,
    }

    result = transform_provider_request(
        root,
        "anthropic",
        body,
        compress_tool_results=False,
        deduplicate_history=False,
        prefix_tracking=False,
        context_budget_total_tokens=2000,
    )

    assert result.changed is True
    assert result.schema_recovery_handle
    assert result.body["tools"] != tools
    assert (
        result.context_budget["observed_tokens"]["schemas"]
        > result.context_budget["allocations"]["schemas"]
    )


def test_provider_context_budget_only_compresses_tool_history_when_over_slice(
    tmp_path, monkeypatch
):
    """Historical tool compression pressure should come from observed demand vs slice."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    historical = _noise("pytest", rows=260)
    body = {
        "messages": [
            {"role": "tool", "content": historical},
            {"role": "user", "content": "Debug the failing parser."},
        ]
    }

    roomy = transform_provider_request(
        root,
        "openai",
        body,
        compress_schemas=False,
        deduplicate_history=False,
        prefix_tracking=False,
        tool_result_min_tokens=100,
        context_budget_total_tokens=100000,
    )
    assert roomy.changed is False
    assert roomy.body == body

    constrained = transform_provider_request(
        root,
        "openai",
        body,
        compress_schemas=False,
        deduplicate_history=False,
        prefix_tracking=False,
        tool_result_min_tokens=100,
        context_budget_total_tokens=2000,
    )
    assert constrained.changed is True
    assert constrained.transformed_segments == 1
    assert constrained.recovery_handles
    assert (
        constrained.context_budget["observed_tokens"]["tool_results"]
        > constrained.context_budget["allocations"]["tool_results"]
    )


def test_provider_default_has_no_whole_context_budget_metadata(
    tmp_path, monkeypatch
):
    """Existing provider behavior stays unbudgeted until explicitly enabled."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    result = transform_provider_request(
        root,
        "openai",
        {"messages": [{"role": "user", "content": "hello"}]},
        compress_schemas=False,
        compress_tool_results=False,
        deduplicate_history=False,
        prefix_tracking=False,
    )

    assert result.context_budget is None
    assert result.metadata()["context_budget"] is None
