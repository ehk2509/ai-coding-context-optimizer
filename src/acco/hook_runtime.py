"""Host-neutral runtime for coding-agent hook events.

The runtime owns event policy but depends only on injected callables. Host adapters
translate their payload/configuration into :class:`HookConfig` and compose concrete
services at the edge.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .output.contracts import OutputPolicy, OutputResult
from .output.pipeline import detect_failure

HookResponse = tuple[int, dict | None]
GuardService = Callable[[dict], HookResponse]
DeltaService = Callable[..., tuple[str, dict]]
StoreOutputService = Callable[[dict], str]
RecoveryOutputService = Callable[..., str | None]
UserNudgeService = Callable[[Path, str], str | None]
GenerationPolicyService = Callable[..., str | None]
TaskChecklistService = Callable[..., str | None]
ModelRoutingService = Callable[..., str | None]
ResetSessionService = Callable[..., None]
RecordReadService = Callable[..., None]
DigestService = Callable[[str], str]
EstimateTokensService = Callable[[str], int]
TelemetryStartService = Callable[..., None]
TelemetryFinishService = Callable[..., dict | None]
EfficiencySessionStartService = Callable[..., None]
ContinuityContextService = Callable[..., str | None]
GuardianCheckpointService = Callable[..., object | None]
EfficiencyPromptService = Callable[..., None]
DeduplicateOutputService = Callable[..., str | None]
ObserveToolService = Callable[..., str | None]
IngressOptimizerService = Callable[..., object | None]
SmartReadProxyService = Callable[..., str | None]


def _noop_session_start(*args, **kwargs) -> None:
    """Ignore an efficiency session-start event."""
    del args, kwargs


def _noop_recovery(*args, **kwargs) -> str | None:
    """Return no universal recovery handle."""
    del args, kwargs
    return None


def _noop_context(*args, **kwargs) -> str | None:
    """Return no optional hook context."""
    del args, kwargs
    return None


def _noop_guardian(*args, **kwargs) -> object | None:
    """Ignore a pre-compaction checkpoint event."""
    del args, kwargs
    return None


def _noop_prompt(*args, **kwargs) -> None:
    """Ignore an efficiency prompt event."""
    del args, kwargs


def _noop_dedup(*args, **kwargs) -> str | None:
    """Return no cross-turn deduplication replacement."""
    del args, kwargs
    return None


def _noop_ingress(*args, **kwargs) -> object | None:
    """Return no prompt-ingress intervention."""
    del args, kwargs
    return None


def _noop_observe(*args, **kwargs) -> str | None:
    """Return no behavioral-efficiency nudge."""
    del args, kwargs
    return None


def _noop_smart_read(*args, **kwargs) -> str | None:
    """Return no smart-read replacement."""
    del args, kwargs
    return None


class OutputPipelineService(Protocol):
    """Process captured command output behind the hook runtime boundary."""

    def process(
        self,
        text: str,
        command: str = "",
        *,
        exit_code: int | None = None,
        policy: OutputPolicy | None = None,
    ) -> OutputResult:
        """Return the optimized output result for one captured command."""
        ...


DEFAULT_MIN_LINES = 40
DEFAULT_KEEP_TAIL = 15
MIN_NET_TOKENS = 50
DEFAULT_FILTERABLE_TOOLS = frozenset({"Bash"})


@dataclass(frozen=True)
class HookConfig:
    """Configure host-independent hook behavior for one invocation."""

    disabled: bool = False
    delta_enabled: bool = False
    min_lines: int = DEFAULT_MIN_LINES
    keep_tail: int = DEFAULT_KEEP_TAIL
    max_lines: int | None = None
    min_net_tokens: int = MIN_NET_TOKENS
    filterable_tools: frozenset[str] = DEFAULT_FILTERABLE_TOOLS
    output_policy_enabled: bool = True
    task_checklist_enabled: bool = True
    output_policy_mode: str = "normal"
    output_policy_task: str = "auto"
    output_policy_adaptive: bool = True
    output_policy_min_tokens: int | None = None
    output_policy_max_tokens: int | None = None
    output_policy_calibration_file: str = ".acco.output-calibration.json"
    output_telemetry_enabled: bool = True
    model_routing_enabled: bool = False
    model_routing_mode: str = "advisory"
    model_routing_current_model: str = ""
    model_routing_allowed_models: tuple[str, ...] = ()
    model_routing_min_savings: float = 0.05
    model_routing_conservative: bool = True
    model_routing_calibration_file: str = ".acco.routing-calibration.json"
    efficiency_enabled: bool = True
    continuity_enabled: bool = True
    cross_turn_dedup_enabled: bool = True
    waste_detection_enabled: bool = True
    ingress_enabled: bool = False
    ingress_threshold_tokens: int = 12000
    ingress_packet_tokens: int = 1600
    tool_proxy_enabled: bool = False
    tool_proxy_provider: str = "ollama"
    tool_proxy_model: str = "qwen2.5-coder:7b"
    tool_proxy_endpoint: str = "http://127.0.0.1:11434"
    tool_proxy_min_tokens: int = 2500
    tool_proxy_target_tokens: int = 1800
    tool_proxy_model_input_tokens: int = 12000
    tool_proxy_timeout_seconds: float = 6.0
    tool_proxy_max_ranges: int = 4
    tool_proxy_max_range_lines: int = 80


@dataclass(frozen=True)
class HookServices:
    """Provide side-effecting services required by :class:`HookRuntime`."""

    guard: GuardService
    output_pipeline: OutputPipelineService
    apply_delta: DeltaService
    store_output: StoreOutputService
    user_nudge: UserNudgeService
    generation_policy: GenerationPolicyService
    reset_session: ResetSessionService
    record_read: RecordReadService
    digest: DigestService
    estimate_tokens: EstimateTokensService
    telemetry_start: TelemetryStartService
    telemetry_finish: TelemetryFinishService
    efficiency_session_start: EfficiencySessionStartService = _noop_session_start
    continuity_context: ContinuityContextService = _noop_context
    guardian_checkpoint: GuardianCheckpointService = _noop_guardian
    efficiency_prompt: EfficiencyPromptService = _noop_prompt
    deduplicate_output: DeduplicateOutputService = _noop_dedup
    observe_tool: ObserveToolService = _noop_observe
    ingress_optimizer: IngressOptimizerService = _noop_ingress
    smart_read_proxy: SmartReadProxyService = _noop_smart_read
    model_route: ModelRoutingService = _noop_context
    task_checklist: TaskChecklistService = _noop_context
    recovery_output: RecoveryOutputService = _noop_recovery


def cap_for(n_lines: int) -> int:
    """Return the default retained-line cap for an output of ``n_lines``."""

    if n_lines >= 1000:
        return 90
    if n_lines >= 300:
        return 60
    return 30


class HookRuntime:
    """Route hook events through injected application services."""

    def __init__(self, services: HookServices, config: HookConfig | None = None):
        """Create a runtime from explicit services and optional configuration."""

        self.services = services
        self.config = config or HookConfig()

    @staticmethod
    def cwd(payload: dict) -> Path:
        """Resolve the working directory carried by a host payload."""

        raw = payload.get("cwd") or payload.get("cwd_path") or "."
        return Path(str(raw))

    @staticmethod
    def exit_code(response: dict) -> int | None:
        """Extract an integer exit code from supported host response fields."""

        for key in ("exit_code", "exitCode", "code"):
            value = response.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None

    def run_post(self, payload: dict) -> HookResponse:
        """Process a post-tool event and record local efficiency evidence."""

        tool = str(payload.get("tool_name") or "")
        if tool not in self.config.filterable_tools:
            return 0, None

        response = payload.get("tool_response")
        if not isinstance(response, dict):
            return 0, None
        if response.get("isImage") or response.get("interrupted"):
            return 0, None
        if not isinstance(response.get("stdout"), str) or not isinstance(
            response.get("stderr"), str
        ):
            return 0, None
        if not isinstance(response.get("interrupted"), bool) or not isinstance(
            response.get("isImage"), bool
        ):
            return 0, None

        root = self.cwd(payload)
        command = str((payload.get("tool_input") or {}).get("command", ""))
        replacement = dict(response)
        original = response["stdout"]
        failed = detect_failure(original, self.exit_code(response))
        n_lines = len(original.splitlines())
        min_lines = max(1, self.config.min_lines)
        keep_tail = max(0, self.config.keep_tail)
        changed = False

        deduped = self.services.deduplicate_output(
            root,
            command,
            original,
            session_id=payload.get("session_id"),
            enabled=(
                self.config.efficiency_enabled
                and self.config.cross_turn_dedup_enabled
            ),
        )
        if deduped is not None:
            replacement["stdout"] = deduped
            changed = replacement["stdout"] != original
        elif n_lines < min_lines:
            if self.config.delta_enabled:
                replacement["stdout"], _delta_meta = self.services.apply_delta(
                    root,
                    command,
                    original,
                    original,
                    session_id=payload.get("session_id"),
                )
                changed = replacement["stdout"] != original
        else:
            max_lines = self.config.max_lines
            if max_lines is None:
                max_lines = cap_for(n_lines)
            output_result = self.services.output_pipeline.process(
                original,
                command,
                exit_code=self.exit_code(response),
                policy=OutputPolicy(
                    max_lines=max(1, max_lines),
                    keep_tail=keep_tail,
                ),
            )
            replacement["stdout"] = output_result.text
            if self.config.delta_enabled:
                replacement["stdout"], _delta_meta = self.services.apply_delta(
                    root,
                    command,
                    original,
                    replacement["stdout"],
                    session_id=payload.get("session_id"),
                )
            changed = replacement["stdout"] != original

        if not changed:
            behavior_note = self.services.observe_tool(
                root,
                payload,
                original_text=original,
                delivered_text=original,
                failed=failed,
                enabled=self.config.efficiency_enabled,
                waste_detection=self.config.waste_detection_enabled,
            )
            if behavior_note:
                return 0, {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": behavior_note,
                    }
                }
            return 0, None

        legacy_note = (
            "\n[acco: filtered output; original saved. "
            "Retrieve: acco output {id} --stream stdout --offset 1 --limit 80]"
        )
        recovery_note = (
            "\n[acco recovery: {handle}; "
            "use recover_context or acco recover]"
        )
        candidate = (
            replacement["stdout"]
            + legacy_note.format(id="0" * 32)
            + recovery_note.format(handle="tsr_" + "0" * 32)
            + "\n"
        )
        if (
            self.services.estimate_tokens(original)
            - self.services.estimate_tokens(candidate)
            < self.config.min_net_tokens
            or len(candidate.encode()) >= len(original.encode())
        ):
            behavior_note = self.services.observe_tool(
                root,
                payload,
                original_text=original,
                delivered_text=original,
                failed=failed,
                enabled=self.config.efficiency_enabled,
                waste_detection=self.config.waste_detection_enabled,
            )
            if behavior_note:
                return 0, {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": behavior_note,
                    }
                }
            return 0, None

        recovery_handle = self.services.recovery_output(
            root,
            original,
            content_type="text/plain",
            metadata={
                "transform": "hook-output-compression",
                "command": command[:500],
            },
        )
        output_id = self.services.store_output(response)
        replacement["stdout"] += legacy_note.format(id=output_id)
        if recovery_handle:
            replacement["stdout"] += recovery_note.format(
                handle=recovery_handle
            )
        replacement["stdout"] += "\n"
        behavior_note = self.services.observe_tool(
            root,
            payload,
            original_text=original,
            delivered_text=replacement["stdout"],
            failed=failed,
            enabled=self.config.efficiency_enabled,
            waste_detection=self.config.waste_detection_enabled,
        )
        specific = {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": replacement,
        }
        if behavior_note:
            specific["additionalContext"] = behavior_note
        return 0, {"hookSpecificOutput": specific}

    def run_pre_compact(self, payload: dict) -> HookResponse:
        """Capture bounded structured state before the host compacts context."""

        root = self.cwd(payload)
        trigger = str(
            payload.get("trigger")
            or payload.get("source")
            or "compact"
        ).lower()
        self.services.guardian_checkpoint(
            root,
            session_id=payload.get("session_id"),
            source=f"precompact:{trigger}",
            enabled=(
                self.config.efficiency_enabled
                and self.config.continuity_enabled
            ),
        )
        return 0, None

    def run_session_start(self, payload: dict) -> HookResponse:
        """Reset transient state and restore compact structured continuity."""

        root = self.cwd(payload)
        source = str(payload.get("source") or "").lower()
        continuity = self.services.continuity_context(
            root,
            session_id=payload.get("session_id"),
            source=source,
            enabled=(
                self.config.efficiency_enabled
                and self.config.continuity_enabled
            ),
        )
        self.services.efficiency_session_start(
            root,
            session_id=payload.get("session_id"),
            source=source,
            enabled=self.config.efficiency_enabled,
        )
        new_convo = source in {"", "startup", "clear", "compact"}
        self.services.reset_session(
            root,
            reads=new_convo,
            reminder=True,
            session_id=payload.get("session_id"),
        )
        if not continuity:
            return 0, None
        return 0, {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": continuity,
            }
        }

    def run_user_prompt(self, payload: dict) -> HookResponse:
        """Inject compact lifecycle and generation policy only when needed."""

        root = self.cwd(payload)
        prompt = str(payload.get("prompt") or payload.get("user_prompt") or "")
        response: dict = {}

        staged = self.services.ingress_optimizer(
            root,
            prompt,
            enabled=self.config.ingress_enabled,
            threshold_tokens=self.config.ingress_threshold_tokens,
            packet_tokens=self.config.ingress_packet_tokens,
        )
        if staged is not None:
            stage_id = str(getattr(staged, "id", ""))
            original_tokens = int(getattr(staged, "original_tokens", 0))
            packet_tokens = int(getattr(staged, "packet_tokens", 0))
            return 0, {
                "decision": "block",
                "reason": (
                    "ACCO blocked this oversized prompt before model "
                    f"processing and staged it losslessly as {stage_id} "
                    f"(~{original_tokens} -> ~{packet_tokens} packet tokens). "
                    "Submit a small follow-up such as: "
                    f"'Use staged prompt {stage_id}; run acco ingress-show "
                    f"{stage_id} --path . and continue.' The exact original remains "
                    "recoverable with acco ingress-read."
                ),
                "suppressOriginalPrompt": True,
            }

        self.services.efficiency_prompt(
            root,
            prompt,
            session_id=payload.get("session_id"),
            enabled=self.config.efficiency_enabled,
        )

        context_notes: list[str] = []
        if self.config.output_policy_enabled:
            generation_note = self.services.generation_policy(
                root,
                prompt,
                session_id=payload.get("session_id"),
                mode=self.config.output_policy_mode,
                task=self.config.output_policy_task,
                adaptive=self.config.output_policy_adaptive,
                min_tokens=self.config.output_policy_min_tokens,
                max_tokens=self.config.output_policy_max_tokens,
                calibration_file=self.config.output_policy_calibration_file,
            )
            if generation_note:
                context_notes.append(generation_note)
            # Unlike the policy (re-sent only when it changes), the checklist is
            # specific to each prompt's own named reproductions and paths.
            checklist_note = (
                self.services.task_checklist(prompt)
                if self.config.task_checklist_enabled
                else None
            )
            if checklist_note:
                context_notes.append(checklist_note)

        routing_note = self.services.model_route(
            root,
            prompt,
            session_id=payload.get("session_id"),
            enabled=self.config.model_routing_enabled,
            mode=self.config.model_routing_mode,
            current_model=(
                str(payload.get("model"))
                if payload.get("model")
                else self.config.model_routing_current_model or None
            ),
            allowed_models=(
                self.config.model_routing_allowed_models or None
            ),
            min_savings=self.config.model_routing_min_savings,
            conservative=self.config.model_routing_conservative,
            calibration_file=self.config.model_routing_calibration_file,
        )
        if routing_note:
            context_notes.append(routing_note)

        if context_notes:
            response["hookSpecificOutput"] = {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n\n".join(context_notes),
            }

        if self.config.output_telemetry_enabled:
            self.services.telemetry_start(
                root,
                transcript_path=payload.get("transcript_path"),
                session_id=payload.get("session_id"),
                prompt_id=payload.get("prompt_id"),
            )

        lifecycle_note = self.services.user_nudge(root, prompt)
        if lifecycle_note:
            response["systemMessage"] = lifecycle_note

        return (0, response) if response else (0, None)

    def run_stop(self, payload: dict, *, failed: bool = False) -> HookResponse:
        """Record one completed or API-failed model turn without storing content."""

        if self.config.output_telemetry_enabled:
            self.services.telemetry_finish(
                self.cwd(payload),
                transcript_path=payload.get("transcript_path"),
                session_id=payload.get("session_id"),
                status="api_failure" if failed else "completed",
                error=payload.get("error") if failed else None,
            )
        return 0, None

    def run_post_read(self, payload: dict) -> HookResponse:
        """Record a verified read and optionally replace a large full-file result."""

        root = self.cwd(payload)
        tool_input = payload.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            return 0, None
        ranged = any(
            key in tool_input for key in ("offset", "limit", "start_line", "end_line")
        )
        raw = (
            tool_input.get("file_path")
            or tool_input.get("path")
            or tool_input.get("filePath")
        )
        response = payload.get("tool_response")
        resolved_path: Path | None = None
        original_text = ""
        verified_full_read = False

        if raw:
            resolved_path = Path(str(raw))
            if not resolved_path.is_absolute():
                resolved_path = root / resolved_path
            if resolved_path.is_file():
                try:
                    original_text = resolved_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                except OSError:
                    original_text = ""
                info = response.get("file") if isinstance(response, dict) else None
                verified_full_read = bool(
                    original_text
                    and not ranged
                    and isinstance(info, dict)
                    and info.get("content") == original_text
                )
                if verified_full_read:
                    self.services.record_read(
                        root,
                        resolved_path,
                        self.services.digest(original_text),
                        session_id=payload.get("session_id"),
                    )

        delivered_text = original_text
        updated: dict | None = None
        if (
            verified_full_read
            and resolved_path is not None
            and isinstance(response, dict)
        ):
            proxied = self.services.smart_read_proxy(
                root,
                resolved_path,
                original_text,
                transcript_path=payload.get("transcript_path"),
                enabled=self.config.tool_proxy_enabled,
                provider=self.config.tool_proxy_provider,
                model=self.config.tool_proxy_model,
                endpoint=self.config.tool_proxy_endpoint,
                min_tokens=self.config.tool_proxy_min_tokens,
                target_tokens=self.config.tool_proxy_target_tokens,
                model_input_tokens=self.config.tool_proxy_model_input_tokens,
                timeout_seconds=self.config.tool_proxy_timeout_seconds,
                max_ranges=self.config.tool_proxy_max_ranges,
                max_range_lines=self.config.tool_proxy_max_range_lines,
            )
            if proxied is not None and proxied != original_text:
                info = response.get("file")
                if isinstance(info, dict):
                    updated = dict(response)
                    updated_file = dict(info)
                    updated_file["content"] = proxied
                    updated["file"] = updated_file
                    delivered_text = proxied

        observe_kwargs = {
            "enabled": self.config.efficiency_enabled,
            "waste_detection": self.config.waste_detection_enabled,
        }
        if verified_full_read:
            observe_kwargs["original_text"] = original_text
            observe_kwargs["delivered_text"] = delivered_text
        note = self.services.observe_tool(root, payload, **observe_kwargs)

        if updated is None and not note:
            return 0, None
        specific: dict = {"hookEventName": "PostToolUse"}
        if updated is not None:
            specific["updatedToolOutput"] = updated
        if note:
            specific["additionalContext"] = note
        return 0, {"hookSpecificOutput": specific}

    def run_post_state_only(self, payload: dict) -> HookResponse:
        """Record Edit/Write activity without rewriting the tool result."""

        note = self.services.observe_tool(
            self.cwd(payload),
            payload,
            enabled=self.config.efficiency_enabled,
            waste_detection=self.config.waste_detection_enabled,
        )
        if not note:
            return 0, None
        return 0, {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": note,
            }
        }

    def run(self, payload: dict) -> HookResponse:
        """Route one normalized hook payload to the appropriate service."""

        if self.config.disabled:
            return 0, None

        event = payload.get("hook_event_name") or payload.get("hookEventName") or ""
        if event == "PreCompact":
            return self.run_pre_compact(payload)
        if event == "SessionStart":
            return self.run_session_start(payload)
        if event == "UserPromptSubmit":
            return self.run_user_prompt(payload)
        if event == "Stop":
            return self.run_stop(payload)
        if event == "StopFailure":
            return self.run_stop(payload, failed=True)
        if event == "PreToolUse" or (
            not event
            and payload.get("tool_name") == "Read"
            and "tool_response" not in payload
        ):
            return self.services.guard(payload)
        if event == "PostToolUse" and payload.get("tool_name") == "Read":
            return self.run_post_read(payload)
        if event == "PostToolUse" and payload.get("tool_name") in {"Edit", "Write"}:
            return self.run_post_state_only(payload)
        return self.run_post(payload)
