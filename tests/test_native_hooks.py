"""Tests for native coding-host hook protocol adapters."""

from __future__ import annotations

import json

from acco.native_hooks import (
    adapt_response,
    normalize_payload,
    run_native_hook,
)


def _large_output() -> str:
    """Return repetitive output large enough to cross ACCO compression gates."""
    return "\n".join(
        f"progress {index} " + "x" * 80
        for index in range(240)
    )


def test_copilot_pretool_guard_blocks_large_full_read(tmp_path, monkeypatch):
    """Copilot PreToolUse should reuse ACCO's source-read guard."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    source = tmp_path / "large.py"
    source.write_text(
        "\n".join(f"def f{index}(): return {index}" for index in range(260)),
        encoding="utf-8",
    )

    result = run_native_hook(
        "copilot",
        "PreToolUse",
        {
            "cwd": str(tmp_path),
            "session_id": "s1",
            "tool_name": "Read",
            "tool_input": {"file_path": str(source)},
        },
    )

    assert result["permissionDecision"] == "deny"
    assert "full Read" in result["permissionDecisionReason"]


def test_copilot_posttool_replaces_large_shell_result(tmp_path, monkeypatch):
    """Copilot's documented modifiedResult path should receive compact output."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    original = _large_output()

    result = run_native_hook(
        "copilot",
        "PostToolUse",
        {
            "cwd": str(tmp_path),
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "custom-build"},
            "tool_result": {
                "result_type": "success",
                "text_result_for_llm": original,
            },
        },
    )

    replacement = result["modifiedResult"]["textResultForLlm"]
    assert len(replacement) < len(original)
    assert "acco recovery:" in replacement
    assert original not in replacement


def test_gemini_aftertool_hides_original_and_returns_compact_reason(
    tmp_path, monkeypatch
):
    """Gemini AfterTool deny should use ACCO's compact result as replacement."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    original = _large_output()

    result = run_native_hook(
        "gemini",
        "AfterTool",
        {
            "cwd": str(tmp_path),
            "session_id": "s1",
            "tool_name": "run_shell_command",
            "tool_input": {"command": "custom-build"},
            "tool_response": {
                "llmContent": original,
                "returnDisplay": original,
            },
        },
    )

    assert result["decision"] == "deny"
    assert len(result["reason"]) < len(original)
    assert "acco recovery:" in result["reason"]


def test_cursor_translates_guard_denial_to_native_permission_schema():
    """Cursor preToolUse should receive permission/user/agent message fields."""
    result = adapt_response(
        "cursor",
        "preToolUse",
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "use a bounded read",
            }
        },
    )

    assert result == {
        "permission": "deny",
        "user_message": "use a bounded read",
        "agent_message": "use a bounded read",
    }


def test_cursor_prompt_ingress_block_maps_to_continue_false():
    """Cursor beforeSubmitPrompt can enforce lossless prompt staging."""
    result = adapt_response(
        "cursor",
        "beforeSubmitPrompt",
        {
            "decision": "block",
            "reason": "staged oversized prompt",
            "suppressOriginalPrompt": True,
        },
    )

    assert result == {
        "continue": False,
        "user_message": "staged oversized prompt",
    }


def test_qwen_normalization_maps_runtime_tool_ids_to_acco_tools(tmp_path):
    """Qwen's run_shell_command id should enter HookRuntime as Bash."""
    payload = normalize_payload(
        "qwen",
        "PreToolUse",
        {
            "cwd": str(tmp_path),
            "session_id": "s1",
            "tool_name": "run_shell_command",
            "tool_input": {"command": "pytest -q"},
        },
    )

    assert payload["hook_event_name"] == "PreToolUse"
    assert payload["tool_name"] == "Bash"
    assert payload["tool_input"]["command"] == "pytest -q"


def test_qwen_ignores_non_user_prompt_continuations(tmp_path):
    """Qwen tool-result continuations must not masquerade as new user prompts."""
    payload = normalize_payload(
        "qwen",
        "UserPromptSubmit",
        {
            "cwd": str(tmp_path),
            "prompt": "tool continuation text",
        },
    )

    assert payload["prompt"] == ""


def test_qwen_keeps_explicit_submitted_prompt(tmp_path):
    """Qwen explicit submitted_prompt remains eligible for ingress/policy hooks."""
    payload = normalize_payload(
        "qwen",
        "UserPromptSubmit",
        {
            "cwd": str(tmp_path),
            "prompt": "expanded runtime prompt",
            "submitted_prompt": "fix the parser",
        },
    )

    assert payload["prompt"] == "fix the parser"


def test_copilot_normalizes_pascalcase_posttool_payload(tmp_path):
    """Copilot's VS Code-compatible shape should become one canonical result."""
    payload = normalize_payload(
        "copilot",
        "PostToolUse",
        {
            "cwd": str(tmp_path),
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
            "tool_result": {
                "result_type": "success",
                "text_result_for_llm": "ok",
            },
        },
    )

    assert payload["tool_response"] == {
        "stdout": "ok",
        "stderr": "",
        "interrupted": False,
        "isImage": False,
        "exit_code": 0,
    }


def test_gemini_beforeagent_preserves_generation_context():
    """Gemini prompt hooks should receive ACCO's additional context natively."""
    result = adapt_response(
        "gemini",
        "BeforeAgent",
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "bounded response policy",
            },
            "systemMessage": "lifecycle note",
        },
    )

    assert result["hookSpecificOutput"] == {
        "hookEventName": "BeforeAgent",
        "additionalContext": "bounded response policy",
    }
    assert result["systemMessage"] == "lifecycle note"


def test_native_hook_results_are_json_serializable():
    """Every adapter result must remain strict JSON for host hook parsers."""
    result = adapt_response(
        "copilot",
        "PostToolUse",
        {
            "hookSpecificOutput": {
                "updatedToolOutput": {"stdout": "compact"},
                "additionalContext": "note",
            }
        },
    )

    assert json.loads(json.dumps(result)) == result


def test_codex_normalizes_bash_and_string_tool_response(tmp_path):
    """Codex local-tool payloads should enter the shared runtime without loss."""
    payload = normalize_payload(
        "codex",
        "PostToolUse",
        {
            "cwd": str(tmp_path),
            "session_id": "thr_1",
            "model": "gpt-6-codex",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q"},
            "tool_response": "all tests passed",
        },
    )

    assert payload["hook_event_name"] == "PostToolUse"
    assert payload["tool_name"] == "Bash"
    assert payload["tool_response"] == {
        "stdout": "all tests passed",
        "stderr": "",
        "interrupted": False,
        "isImage": False,
        "exit_code": 0,
    }


def test_codex_pretool_guard_blocks_large_cat(tmp_path, monkeypatch):
    """Codex PreToolUse should reuse ACCO's existing large-source Bash guard."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    source = tmp_path / "large.py"
    source.write_text(
        "\n".join(f"value_{index} = {index}" for index in range(300)),
        encoding="utf-8",
    )

    result = run_native_hook(
        "codex",
        "PreToolUse",
        {
            "cwd": str(tmp_path),
            "session_id": "thr_1",
            "tool_name": "Bash",
            "tool_input": {"command": f"cat {source.name}"},
        },
    )

    specific = result["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert specific["permissionDecision"] == "deny"
    assert "acco blocked" in specific["permissionDecisionReason"]


def test_codex_posttool_replaces_large_result_without_rejecting_code_mode(
    tmp_path, monkeypatch
):
    """Codex should suppress the original result and deliver recoverable compact context."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    original = _large_output()

    result = run_native_hook(
        "codex",
        "PostToolUse",
        {
            "cwd": str(tmp_path),
            "session_id": "thr_1",
            "tool_name": "Bash",
            "tool_input": {"command": "custom-build"},
            "tool_response": original,
        },
    )

    assert result["continue"] is False
    compact = result["hookSpecificOutput"]["additionalContext"]
    assert len(compact) < len(original)
    assert "acco recovery:" in compact
    assert original not in compact
    assert "decision" not in result


def test_codex_prompt_ingress_and_policy_use_native_context_fields():
    """Codex UserPromptSubmit should map both block and developer-context outputs."""
    blocked = adapt_response(
        "codex",
        "UserPromptSubmit",
        {
            "decision": "block",
            "reason": "stage this oversized prompt",
        },
    )
    assert blocked == {
        "decision": "block",
        "reason": "stage this oversized prompt",
    }

    allowed = adapt_response(
        "codex",
        "UserPromptSubmit",
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "bounded ACCO policy",
            },
            "systemMessage": "lifecycle note",
        },
    )
    assert allowed == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "bounded ACCO policy",
        },
        "systemMessage": "lifecycle note",
    }


def test_codex_session_start_maps_continuity_to_developer_context():
    """Codex SessionStart should receive ACCO's bounded continuity checkpoint."""
    result = adapt_response(
        "codex",
        "SessionStart",
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "continue from tests/test_parser.py",
            }
        },
    )

    assert result == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "continue from tests/test_parser.py",
        }
    }
