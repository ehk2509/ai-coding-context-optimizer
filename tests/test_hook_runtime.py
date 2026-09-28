"""Tests for the host-neutral hook runtime boundary."""

from pathlib import Path

from acco.hook_runtime import HookConfig, HookRuntime, HookServices
from acco.output import OutputResult


class _PassthroughPipeline:
    """Minimal output pipeline used by runtime unit tests."""

    def process(self, text, command="", *, exit_code=None, policy=None):
        """Return the original text as an uncompressed output result."""

        return OutputResult(text, "test", False, bool(exit_code))


def _services(**overrides):
    """Return inert hook services with explicit overrides for one test."""

    defaults = {
        "guard": lambda payload: (0, None),
        "output_pipeline": _PassthroughPipeline(),
        "apply_delta": (
            lambda root, command, original, fallback, **kwargs: (fallback, {})
        ),
        "store_output": lambda response: "stored",
        "user_nudge": lambda root, prompt: None,
        "generation_policy": lambda root, prompt, **kwargs: None,
        "reset_session": lambda root, **kwargs: None,
        "record_read": lambda root, path, digest, **kwargs: None,
        "digest": lambda text: "digest",
        "estimate_tokens": lambda text: len(text),
        "telemetry_start": lambda root, **kwargs: None,
        "telemetry_finish": lambda root, **kwargs: None,
    }
    defaults.update(overrides)
    return HookServices(**defaults)


def _bash_payload(stdout: str) -> dict:
    """Build a normalized Claude-style Bash post-tool payload."""

    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "cwd": ".",
        "tool_input": {"command": "custom build"},
        "tool_response": {
            "stdout": stdout,
            "stderr": "",
            "interrupted": False,
            "isImage": False,
            "exit_code": 0,
        },
    }


def test_runtime_routes_pretool_events_to_injected_guard():
    """Pre-tool routing should depend on the guard contract, not a concrete module."""

    seen = []

    def guard(payload):
        """Capture the normalized payload passed to the injected guard."""

        seen.append(payload)
        return 0, {"guarded": True}

    runtime = HookRuntime(_services(guard=guard))
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "large.py"},
    }

    assert runtime.run(payload) == (0, {"guarded": True})
    assert seen == [payload]


def test_runtime_uses_injected_output_pipeline_and_store():
    """Post-tool output should flow through injected optimization and persistence."""

    filtered = []
    stored = []

    class CompactPipeline:
        """Pipeline test double that returns a deterministic compact candidate."""

        def process(self, text, command="", *, exit_code=None, policy=None):
            """Capture pipeline inputs and return a compact result."""

            filtered.append(
                (
                    text,
                    {
                        "command": command,
                        "exit_code": exit_code,
                        "policy": policy,
                    },
                )
            )
            return OutputResult("summary\n", "custom", True, bool(exit_code))

    def store_output(response):
        """Capture the original response before returning its recovery identifier."""

        stored.append(response)
        return "abc123"

    original = "\n".join(f"long build output {i:03d} " + "x" * 60 for i in range(80))
    runtime = HookRuntime(
        _services(output_pipeline=CompactPipeline(), store_output=store_output),
        HookConfig(min_lines=1, min_net_tokens=0, max_lines=10),
    )

    code, response = runtime.run(_bash_payload(original))

    assert code == 0
    assert response is not None
    updated = response["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert updated.startswith("summary\n")
    assert "abc123" in updated
    assert filtered[0][1]["policy"].max_lines == 10
    assert stored and stored[0]["stdout"] == original


def test_runtime_injects_session_and_prompt_services(tmp_path):
    """Session reset and prompt nudges should be supplied by application services."""

    reset_calls = []
    prompt_calls = []

    def reset_session(root, **kwargs):
        """Capture session reset calls."""

        reset_calls.append((root, kwargs))

    def user_nudge(root, prompt):
        """Capture prompt calls and return a deterministic nudge."""

        prompt_calls.append((root, prompt))
        return "use bounded context"

    runtime = HookRuntime(
        _services(reset_session=reset_session, user_nudge=user_nudge)
    )
    assert runtime.run(
        {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
            "source": "resume",
            "session_id": "session",
        }
    ) == (0, None)
    assert reset_calls == [
        (
            Path(tmp_path),
            {"reads": False, "reminder": True, "session_id": "session"},
        )
    ]

    code, response = runtime.run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "fix the bug",
        }
    )
    assert code == 0
    assert response == {"systemMessage": "use bounded context"}
    assert prompt_calls == [(Path(tmp_path), "fix the bug")]


def test_runtime_injects_generation_policy_with_session_config(tmp_path):
    """Prompt hooks should pass session and policy config to the generator."""
    calls = []

    def generation_policy(root, prompt, **kwargs):
        """Capture automatic generation-policy calls."""
        calls.append((root, prompt, kwargs))
        return "generation contract"

    runtime = HookRuntime(
        _services(generation_policy=generation_policy),
        HookConfig(
            output_policy_enabled=True,
            output_policy_mode="terse",
            output_policy_task="coding",
        ),
    )

    code, response = runtime.run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "continue",
            "session_id": "session-1",
        }
    )

    assert code == 0
    assert response == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "generation contract",
        }
    }
    assert calls == [
        (
            Path(tmp_path),
            "continue",
            {
                "session_id": "session-1",
                "mode": "terse",
                "task": "coding",
                "adaptive": True,
                "min_tokens": None,
                "max_tokens": None,
                "calibration_file": ".acco.output-calibration.json",
            },
        )
    ]


def test_runtime_can_disable_generation_policy_without_disabling_other_nudges(tmp_path):
    """Output-policy opt-out should leave existing lifecycle advice untouched."""
    generation_calls = []

    runtime = HookRuntime(
        _services(
            generation_policy=lambda *args, **kwargs: generation_calls.append(
                (args, kwargs)
            ),
            user_nudge=lambda root, prompt: "lifecycle nudge",
        ),
        HookConfig(output_policy_enabled=False),
    )

    code, response = runtime.run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "implement this",
        }
    )

    assert code == 0
    assert response == {"systemMessage": "lifecycle nudge"}
    assert generation_calls == []


def test_runtime_routes_prompt_and_stop_telemetry_without_model_context(tmp_path):
    """Turn telemetry should checkpoint on prompt and finish silently on Stop."""
    starts = []
    finishes = []
    runtime = HookRuntime(
        _services(
            telemetry_start=lambda root, **kwargs: starts.append((root, kwargs)),
            telemetry_finish=lambda root, **kwargs: finishes.append((root, kwargs)),
        )
    )

    prompt = {
        "hook_event_name": "UserPromptSubmit",
        "cwd": str(tmp_path),
        "session_id": "s1",
        "prompt_id": "p1",
        "transcript_path": str(tmp_path / "session.jsonl"),
        "prompt": "continue",
    }
    assert runtime.run(prompt) == (0, None)
    assert starts == [
        (
            Path(tmp_path),
            {
                "transcript_path": str(tmp_path / "session.jsonl"),
                "session_id": "s1",
                "prompt_id": "p1",
            },
        )
    ]

    stop = {
        "hook_event_name": "Stop",
        "cwd": str(tmp_path),
        "session_id": "s1",
        "transcript_path": str(tmp_path / "session.jsonl"),
        "last_assistant_message": "content must not be forwarded",
    }
    assert runtime.run(stop) == (0, None)
    assert finishes == [
        (
            Path(tmp_path),
            {
                "transcript_path": str(tmp_path / "session.jsonl"),
                "session_id": "s1",
                "status": "completed",
                "error": None,
            },
        )
    ]


def test_runtime_routes_stop_failure_as_api_failure(tmp_path):
    """StopFailure should record API failure without calling it task failure."""
    finishes = []
    runtime = HookRuntime(
        _services(
            telemetry_finish=lambda root, **kwargs: finishes.append((root, kwargs))
        )
    )

    assert runtime.run(
        {
            "hook_event_name": "StopFailure",
            "cwd": str(tmp_path),
            "session_id": "s1",
            "transcript_path": str(tmp_path / "session.jsonl"),
            "error": "rate_limit",
        }
    ) == (0, None)
    assert finishes[0][1]["status"] == "api_failure"
    assert finishes[0][1]["error"] == "rate_limit"


def test_runtime_records_verified_full_read_with_injected_state_services(tmp_path):
    """Full-read tracking should depend only on digest and record-read contracts."""

    source = tmp_path / "module.py"
    source.write_text("value = 1\n", encoding="utf-8")
    recorded = []

    def record_read(root, path, digest, **kwargs):
        """Capture read-state writes."""

        recorded.append((root, path, digest, kwargs))

    runtime = HookRuntime(
        _services(
            digest=lambda text: f"digest:{len(text)}",
            record_read=record_read,
        )
    )
    runtime.run(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "cwd": str(tmp_path),
            "session_id": "s1",
            "tool_input": {"file_path": str(source)},
            "tool_response": {"file": {"content": "value = 1\n"}},
        }
    )

    assert recorded == [
        (
            Path(tmp_path),
            source,
            "digest:10",
            {"session_id": "s1"},
        )
    ]


def test_runtime_disabled_short_circuits_all_services():
    """The kill switch should stop routing before any injected service is called."""

    called = []

    def guard(payload):
        """Fail the test if a disabled runtime still reaches the guard."""

        called.append(payload)
        return 0, {"unexpected": True}

    runtime = HookRuntime(_services(guard=guard), HookConfig(disabled=True))
    assert runtime.run({"hook_event_name": "PreToolUse", "tool_name": "Read"}) == (
        0,
        None,
    )
    assert called == []



def test_runtime_restores_structured_continuity_on_resume(tmp_path):
    """Resume should inject continuity through SessionStart additionalContext."""
    starts = []
    runtime = HookRuntime(
        _services(
            continuity_context=lambda root, **kwargs: "checkpoint context",
            efficiency_session_start=lambda root, **kwargs: starts.append(
                (root, kwargs)
            ),
        )
    )

    code, response = runtime.run(
        {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
            "source": "resume",
            "session_id": "session-1",
        }
    )

    assert code == 0
    assert response == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "checkpoint context",
        }
    }
    assert starts == [
        (
            Path(tmp_path),
            {
                "session_id": "session-1",
                "source": "resume",
                "enabled": True,
            },
        )
    ]


def test_runtime_exact_dedup_bypasses_normal_output_processor(tmp_path):
    """Exact cross-turn duplicate output should skip ordinary compression."""
    calls = []

    class UnexpectedPipeline:
        """Fail if normal compression runs after exact dedup matched."""

        def process(self, text, command="", *, exit_code=None, policy=None):
            """Record an unexpected call before returning passthrough."""
            calls.append((text, command, exit_code, policy))
            return OutputResult(text, "unexpected", False, False)

    observed = []
    original = "\n".join("same output " + "x" * 80 for _ in range(80))
    runtime = HookRuntime(
        _services(
            output_pipeline=UnexpectedPipeline(),
            deduplicate_output=lambda *args, **kwargs: "[duplicate]\n",
            observe_tool=lambda *args, **kwargs: observed.append(kwargs) or None,
        ),
        HookConfig(min_lines=1, min_net_tokens=0),
    )
    payload = _bash_payload(original)
    payload["cwd"] = str(tmp_path)

    code, response = runtime.run(payload)

    assert code == 0
    assert calls == []
    assert response is not None
    delivered = response["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert delivered.startswith("[duplicate]")
    assert observed[-1]["original_text"] == original
    assert observed[-1]["delivered_text"].startswith("[duplicate]")


def test_runtime_behavior_signal_can_surface_without_output_rewrite(tmp_path):
    """Behavior detection should be able to nudge without changing tool output."""
    runtime = HookRuntime(
        _services(
            observe_tool=lambda *args, **kwargs: "reassess repeated retries",
        ),
        HookConfig(min_lines=1000),
    )
    payload = _bash_payload("short output\n")
    payload["cwd"] = str(tmp_path)

    code, response = runtime.run(payload)

    assert code == 0
    assert response == {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "reassess repeated retries",
        }
    }


def test_runtime_records_prompt_task_state_without_changing_prompt_response(tmp_path):
    """Efficiency prompt observation should coexist with no generation policy."""
    calls = []
    runtime = HookRuntime(
        _services(
            efficiency_prompt=lambda root, prompt, **kwargs: calls.append(
                (root, prompt, kwargs)
            )
        ),
        HookConfig(output_policy_enabled=False, output_telemetry_enabled=False),
    )

    result = runtime.run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "session_id": "s1",
            "prompt": "implement the feature",
        }
    )

    assert result == (0, None)
    assert calls == [
        (
            Path(tmp_path),
            "implement the feature",
            {"session_id": "s1", "enabled": True},
        )
    ]


def test_runtime_observes_edit_without_rewriting_tool_result(tmp_path):
    """Edit/Write post events should feed continuity state only."""
    calls = []
    runtime = HookRuntime(
        _services(
            observe_tool=lambda root, payload, **kwargs: calls.append(
                (root, payload["tool_name"], kwargs)
            )
            or None
        )
    )
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "cwd": str(tmp_path),
        "session_id": "s1",
        "tool_input": {"file_path": "src/app.py"},
        "tool_response": {"ok": True},
    }

    assert runtime.run(payload) == (0, None)
    assert calls[0][0] == Path(tmp_path)
    assert calls[0][1] == "Edit"



def test_runtime_stages_oversized_prompt_before_other_prompt_services(tmp_path):
    """Ingress intervention should block before policy, telemetry, or prompt-state work."""
    from types import SimpleNamespace

    calls = []
    runtime = HookRuntime(
        _services(
            ingress_optimizer=lambda root, prompt, **kwargs: SimpleNamespace(
                id="stage1234",
                original_tokens=15000,
                packet_tokens=1400,
            ),
            efficiency_prompt=lambda *args, **kwargs: calls.append("efficiency"),
            generation_policy=lambda *args, **kwargs: calls.append("policy"),
            telemetry_start=lambda *args, **kwargs: calls.append("telemetry"),
            user_nudge=lambda *args, **kwargs: calls.append("nudge"),
        ),
        HookConfig(
            ingress_enabled=True,
            ingress_threshold_tokens=12000,
            ingress_packet_tokens=1600,
        ),
    )

    code, response = runtime.run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "very large prompt",
        }
    )

    assert code == 0
    assert response is not None
    assert response["decision"] == "block"
    assert response["suppressOriginalPrompt"] is True
    assert "stage1234" in response["reason"]
    assert "ingress-show" in response["reason"]
    assert calls == []


def test_runtime_passes_ingress_threshold_configuration(tmp_path):
    """Prompt ingress service should receive explicit runtime limits even on passthrough."""
    calls = []

    def ingress(root, prompt, **kwargs):
        """Capture ingress policy arguments and allow the prompt."""
        calls.append((root, prompt, kwargs))
        return None

    runtime = HookRuntime(
        _services(ingress_optimizer=ingress),
        HookConfig(
            ingress_enabled=True,
            ingress_threshold_tokens=9000,
            ingress_packet_tokens=1200,
            output_policy_enabled=False,
            output_telemetry_enabled=False,
        ),
    )

    assert runtime.run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "ordinary prompt",
        }
    ) == (0, None)
    assert calls == [
        (
            Path(tmp_path),
            "ordinary prompt",
            {
                "enabled": True,
                "threshold_tokens": 9000,
                "packet_tokens": 1200,
            },
        )
    ]


def test_runtime_can_replace_verified_full_read_with_smart_proxy(tmp_path):
    """PostToolUse should replace only the delivered Read content, not read-state evidence."""
    source = tmp_path / "module.py"
    original = "value = 1\n" * 300
    source.write_text(original, encoding="utf-8")
    recorded = []
    proxy_calls = []

    def record_read(root, path, digest, **kwargs):
        """Capture the original read fingerprint."""
        recorded.append((root, path, digest, kwargs))

    def smart_read_proxy(root, path, content, **kwargs):
        """Return a deterministic compact packet while capturing proxy inputs."""
        proxy_calls.append((root, path, content, kwargs))
        return "ACCO SMART READ\nEXACT SOURCE LINES 1-1\nvalue = 1\n"

    runtime = HookRuntime(
        _services(
            record_read=record_read,
            digest=lambda text: "original-digest",
            smart_read_proxy=smart_read_proxy,
        ),
        HookConfig(tool_proxy_enabled=True),
    )

    code, response = runtime.run(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "cwd": str(tmp_path),
            "session_id": "s1",
            "transcript_path": str(tmp_path / "session.jsonl"),
            "tool_input": {"file_path": str(source)},
            "tool_response": {"file": {"content": original, "filePath": str(source)}},
        }
    )

    assert code == 0
    assert response is not None
    updated = response["hookSpecificOutput"]["updatedToolOutput"]
    assert updated["file"]["content"].startswith("ACCO SMART READ")
    assert recorded == [
        (
            Path(tmp_path),
            source,
            "original-digest",
            {"session_id": "s1"},
        )
    ]
    assert proxy_calls[0][2] == original
    assert proxy_calls[0][3]["enabled"] is True


def test_runtime_never_proxies_bounded_read(tmp_path):
    """A bounded Read is already exact minimal evidence and must remain untouched."""
    source = tmp_path / "module.py"
    original = "value = 1\n" * 20
    source.write_text(original, encoding="utf-8")
    calls = []
    runtime = HookRuntime(
        _services(
            smart_read_proxy=lambda *args, **kwargs: calls.append((args, kwargs))
            or "unexpected",
        ),
        HookConfig(tool_proxy_enabled=True),
    )

    result = runtime.run(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": str(source), "offset": 1, "limit": 20},
            "tool_response": {"file": {"content": original}},
        }
    )

    assert result == (0, None)
    assert calls == []


def test_runtime_appends_task_checklist_after_generation_policy(tmp_path):
    """Prompt-specific checklists ride along with the output policy."""
    prompts = []
    runtime = HookRuntime(
        _services(
            generation_policy=lambda root, prompt, **kwargs: "generation contract",
            task_checklist=lambda prompt: prompts.append(prompt) or "task checklist",
        ),
        HookConfig(output_policy_enabled=True),
    )

    code, response = runtime.run(
        {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": "fix it"}
    )

    assert code == 0
    assert response["hookSpecificOutput"]["additionalContext"] == (
        "generation contract\n\ntask checklist"
    )
    assert prompts == ["fix it"]


def test_runtime_skips_task_checklist_when_output_policy_disabled(tmp_path):
    """Disabling the output policy also disables the prompt checklist."""
    calls = []
    runtime = HookRuntime(
        _services(task_checklist=lambda prompt: calls.append(prompt) or "task checklist"),
        HookConfig(output_policy_enabled=False),
    )

    runtime.run(
        {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": "fix it"}
    )

    assert calls == []


def test_runtime_task_checklist_switch_keeps_policy(tmp_path):
    """task_checklist_enabled=False drops only the checklist, not the policy."""
    calls = []
    runtime = HookRuntime(
        _services(
            generation_policy=lambda root, prompt, **kwargs: "generation contract",
            task_checklist=lambda prompt: calls.append(prompt) or "task checklist",
        ),
        HookConfig(output_policy_enabled=True, task_checklist_enabled=False),
    )

    code, response = runtime.run(
        {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": "fix it"}
    )

    assert code == 0
    assert response["hookSpecificOutput"]["additionalContext"] == "generation contract"
    assert calls == []
