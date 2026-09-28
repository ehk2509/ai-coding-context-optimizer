"""Native coding-host hook adapters over ACCO's host-neutral HookRuntime.

Each supported host has its own event names and response schema. This module
normalizes those payloads into ACCO's existing hook contract, delegates all
policy to :mod:`acco.hook`, then translates only the resulting control fields
back to the host's documented protocol.

The adapters deliberately expose only behavior the host can enforce. In
particular, Cursor and Qwen command hooks do not claim general post-tool output
replacement, while Gemini and Copilot can replace/hide a successful tool result.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

SUPPORTED_NATIVE_HOOK_HOSTS = ("cursor", "gemini", "qwen", "copilot")

_EVENT_MAP = {
    "cursor": {
        "preToolUse": "PreToolUse",
        "beforeSubmitPrompt": "UserPromptSubmit",
        "sessionStart": "SessionStart",
        "preCompact": "PreCompact",
        "stop": "Stop",
    },
    "gemini": {
        "BeforeTool": "PreToolUse",
        "AfterTool": "PostToolUse",
        "BeforeAgent": "UserPromptSubmit",
        "SessionStart": "SessionStart",
        "PreCompress": "PreCompact",
        "AfterAgent": "Stop",
    },
    "qwen": {
        "PreToolUse": "PreToolUse",
        "UserPromptSubmit": "UserPromptSubmit",
        "SessionStart": "SessionStart",
        "PreCompact": "PreCompact",
        "Stop": "Stop",
        "StopFailure": "StopFailure",
    },
    "copilot": {
        "PreToolUse": "PreToolUse",
        "PostToolUse": "PostToolUse",
        "SessionStart": "SessionStart",
        "PreCompact": "PreCompact",
        "Stop": "Stop",
    },
}

_TOOL_MAP = {
    "cursor": {
        "Shell": "Bash",
        "Read": "Read",
        "Write": "Write",
        "Grep": "Grep",
    },
    "gemini": {
        "run_shell_command": "Bash",
        "read_file": "Read",
        "write_file": "Write",
        "replace": "Edit",
    },
    "qwen": {
        "run_shell_command": "Bash",
        "read_file": "Read",
        "write_file": "Write",
        "replace": "Edit",
    },
    # ACCO configures Copilot with PascalCase event names. Copilot then emits
    # VS Code-compatible snake_case payloads and Claude-compatible tool names.
    "copilot": {},
}


def _project_root(payload: dict) -> str:
    """Return the host project root without persisting hook input."""
    raw = payload.get("cwd") or payload.get("cwd_path")
    if raw:
        return str(raw)
    for name in (
        "CURSOR_PROJECT_DIR",
        "GEMINI_PROJECT_DIR",
        "QWEN_PROJECT_DIR",
        "CLAUDE_PROJECT_DIR",
    ):
        value = os.environ.get(name)
        if value:
            return value
    return str(Path.cwd())


def _session_id(payload: dict) -> object:
    """Return a session identifier across camelCase and snake_case hosts."""
    return payload.get("session_id") or payload.get("sessionId")


def _transcript_path(payload: dict) -> object:
    """Return a transcript path when a host exposes one."""
    return (
        payload.get("transcript_path")
        or payload.get("transcriptPath")
        or os.environ.get("CURSOR_TRANSCRIPT_PATH")
    )


def _parse_mapping(value: object) -> dict:
    """Return a JSON object from an object or JSON-encoded object string."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _text(value: object) -> str:
    """Extract model-visible text from common structured tool-result shapes."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for item in value if (part := _text(item)))
    if not isinstance(value, dict):
        return ""
    for key in (
        "stdout",
        "textResultForLlm",
        "text_result_for_llm",
        "llmContent",
        "response_parts",
        "output",
        "result_display",
        "returnDisplay",
        "text",
        "content",
    ):
        if key in value:
            found = _text(value.get(key))
            if found:
                return found
    return ""


def _canonical_tool_response(host: str, payload: dict) -> dict:
    """Translate one supported successful tool response to HookRuntime shape."""
    if host == "copilot":
        raw = payload.get("tool_result") or payload.get("toolResult") or {}
        stdout = _text(raw)
        result = raw if isinstance(raw, dict) else {}
        return {
            "stdout": stdout,
            "stderr": "",
            "interrupted": False,
            "isImage": False,
            "exit_code": 0 if result.get("result_type", result.get("resultType")) == "success" else None,
        }
    if host == "cursor":
        raw = _parse_mapping(payload.get("tool_output"))
    else:
        raw = payload.get("tool_response")
        raw = raw if isinstance(raw, dict) else {}
    error = raw.get("error")
    stderr = _text(error) if error else ""
    exit_code = raw.get("exit_code", raw.get("exitCode"))
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        exit_code = 1 if error else 0
    return {
        "stdout": _text(raw),
        "stderr": stderr,
        "interrupted": bool(raw.get("interrupted", False)),
        "isImage": bool(raw.get("isImage", False)),
        "exit_code": exit_code,
    }


def normalize_payload(host: str, event: str, payload: dict) -> dict:
    """Normalize one host-native hook payload for :class:`HookRuntime`."""
    host = host.strip().lower()
    if host not in SUPPORTED_NATIVE_HOOK_HOSTS:
        raise ValueError(f"unsupported native hook host: {host}")
    canonical_event = _EVENT_MAP[host].get(event)
    if canonical_event is None:
        raise ValueError(f"unsupported {host} hook event: {event}")
    normalized: dict[str, Any] = {
        "hook_event_name": canonical_event,
        "cwd": _project_root(payload),
    }
    session = _session_id(payload)
    if session is not None:
        normalized["session_id"] = session
    transcript = _transcript_path(payload)
    if transcript:
        normalized["transcript_path"] = transcript

    if canonical_event in {"PreToolUse", "PostToolUse"}:
        raw_tool = (
            payload.get("tool_name")
            or payload.get("toolName")
            or ""
        )
        raw_tool = str(raw_tool)
        normalized["tool_name"] = _TOOL_MAP[host].get(raw_tool, raw_tool)
        normalized["tool_input"] = _parse_mapping(
            payload.get("tool_input", payload.get("toolArgs"))
        )
        if canonical_event == "PostToolUse":
            normalized["tool_response"] = _canonical_tool_response(host, payload)

    if canonical_event == "UserPromptSubmit":
        normalized["prompt"] = str(
            payload.get("submitted_prompt")
            or payload.get("prompt")
            or ""
        )
        if payload.get("model"):
            normalized["model"] = payload["model"]

    if canonical_event == "SessionStart":
        normalized["source"] = str(
            payload.get("source") or payload.get("sessionSource") or "startup"
        )

    if canonical_event == "PreCompact":
        normalized["trigger"] = str(payload.get("trigger") or "auto")

    if canonical_event in {"Stop", "StopFailure"}:
        if payload.get("error"):
            normalized["error"] = payload["error"]

    return normalized


def _specific(response: dict | None) -> dict:
    """Return HookRuntime event-specific output when present."""
    if not isinstance(response, dict):
        return {}
    value = response.get("hookSpecificOutput")
    return value if isinstance(value, dict) else {}


def _additional_context(response: dict | None) -> str | None:
    """Return model-facing context emitted by HookRuntime."""
    specific = _specific(response)
    value = specific.get("additionalContext")
    return value if isinstance(value, str) and value else None


def _permission(response: dict | None) -> tuple[str | None, str | None]:
    """Return HookRuntime pre-tool permission decision and reason."""
    specific = _specific(response)
    decision = specific.get("permissionDecision")
    reason = specific.get("permissionDecisionReason")
    return (
        str(decision) if decision else None,
        str(reason) if reason else None,
    )


def _updated_stdout(response: dict | None) -> str | None:
    """Return a replaced stdout value from HookRuntime."""
    specific = _specific(response)
    updated = specific.get("updatedToolOutput")
    if not isinstance(updated, dict):
        return None
    stdout = updated.get("stdout")
    return stdout if isinstance(stdout, str) else None


def _blocked_prompt_reason(response: dict | None) -> str | None:
    """Return the ingress-block reason from HookRuntime when present."""
    if not isinstance(response, dict):
        return None
    if response.get("decision") != "block":
        return None
    reason = response.get("reason")
    return str(reason) if reason else "ACCO blocked this prompt."


def adapt_response(host: str, event: str, response: dict | None) -> dict:
    """Translate HookRuntime output into one host's documented response schema."""
    host = host.strip().lower()
    if response is None:
        return {}

    if host == "copilot":
        if event == "PreToolUse":
            decision, reason = _permission(response)
            result: dict[str, Any] = {}
            if decision:
                result["permissionDecision"] = decision
            if reason:
                result["permissionDecisionReason"] = reason
            return result
        if event == "PostToolUse":
            result = {}
            stdout = _updated_stdout(response)
            if stdout is not None:
                result["modifiedResult"] = {
                    "resultType": "success",
                    "textResultForLlm": stdout,
                }
            context = _additional_context(response)
            if context:
                result["additionalContext"] = context
            return result
        if event == "SessionStart":
            context = _additional_context(response)
            return {"additionalContext": context} if context else {}
        return {}

    if host == "cursor":
        if event == "preToolUse":
            decision, reason = _permission(response)
            if decision != "deny":
                return {}
            reason = reason or "ACCO blocked this tool call."
            return {
                "permission": "deny",
                "user_message": reason,
                "agent_message": reason,
            }
        if event == "beforeSubmitPrompt":
            reason = _blocked_prompt_reason(response)
            return (
                {"continue": False, "user_message": reason}
                if reason
                else {}
            )
        if event == "sessionStart":
            context = _additional_context(response)
            return {"additional_context": context} if context else {}
        return {}

    if host == "gemini":
        if event == "BeforeTool":
            decision, reason = _permission(response)
            result = {}
            if decision:
                result["decision"] = "deny" if decision == "deny" else "allow"
            if reason:
                result["reason"] = reason
            context = _additional_context(response)
            if context:
                result["hookSpecificOutput"] = {
                    "hookEventName": "BeforeTool",
                    "additionalContext": context,
                }
            return result
        if event == "AfterTool":
            result = {}
            stdout = _updated_stdout(response)
            if stdout is not None:
                # Gemini's documented AfterTool deny hides the original result
                # and sends reason back to the model as its replacement.
                result["decision"] = "deny"
                result["reason"] = stdout
            context = _additional_context(response)
            if context:
                result["hookSpecificOutput"] = {
                    "hookEventName": "AfterTool",
                    "additionalContext": context,
                }
            return result
        if event == "BeforeAgent":
            reason = _blocked_prompt_reason(response)
            if reason:
                return {"decision": "deny", "reason": reason}
            result = {}
            context = _additional_context(response)
            if context:
                result["hookSpecificOutput"] = {
                    "hookEventName": "BeforeAgent",
                    "additionalContext": context,
                }
            system = response.get("systemMessage") if isinstance(response, dict) else None
            if isinstance(system, str) and system:
                result["systemMessage"] = system
            return result
        if event == "SessionStart":
            context = _additional_context(response)
            return (
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
                if context
                else {}
            )
        return {}

    if host == "qwen":
        if event == "PreToolUse":
            specific = _specific(response)
            if not specific:
                return {}
            result = {
                "hookSpecificOutput": {
                    key: value
                    for key, value in specific.items()
                    if key in {
                        "permissionDecision",
                        "permissionDecisionReason",
                        "additionalContext",
                        "updatedInput",
                    }
                }
            }
            result["hookSpecificOutput"]["hookEventName"] = "PreToolUse"
            return result
        if event == "UserPromptSubmit":
            reason = _blocked_prompt_reason(response)
            if reason:
                return {"decision": "deny", "reason": reason}
            context = _additional_context(response)
            return (
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context,
                    }
                }
                if context
                else {}
            )
        if event == "SessionStart":
            context = _additional_context(response)
            return (
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
                if context
                else {}
            )
        return {}

    raise ValueError(f"unsupported native hook host: {host}")


def run_native_hook(host: str, event: str, payload: dict) -> dict:
    """Run one native host event through ACCO's existing policy runtime."""
    from .hook import run

    normalized = normalize_payload(host, event, payload)
    _code, response = run(normalized)
    return adapt_response(host, event, response)


def main(host: str, event: str) -> int:
    """Read one native hook payload from stdin and emit strict host JSON."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            payload = {}
        response = run_native_hook(host, event, payload)
    except Exception as exc:
        # Native hook integrations are optimization layers, not permission
        # authorities. Emit valid empty JSON so host failures remain fail-open.
        print(f"acco {host} hook error: {type(exc).__name__}: {exc}", file=sys.stderr)
        response = {}
    json.dump(response, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    return 0
