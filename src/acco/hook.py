"""Claude Code JSON hook adapter.

This module translates Claude's stdin/stdout protocol and environment settings
into the host-neutral :mod:`acco.hook_runtime` application boundary.
Concrete services are composed here so the runtime itself stays independent of
Claude, environment variables, persistence, and repository implementations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .delta_context import apply_delta
from .efficiency import (
    capture_guardian,
    continuity_context,
    deduplicate_output,
    observe_prompt,
    observe_tool,
    start_session,
)
from .estimate import estimate_tokens
from .output import OutputPipeline
from .output_telemetry import finish_output_turn, start_output_turn
from .generation_policy import automatic_output_policy
from .task_checklist import task_checklist_note
from .model_routing import automatic_model_route
from .ingress import maybe_stage_prompt
from .guard import _digest, run as guard_run
from .hook_runtime import (
    MIN_NET_TOKENS,
    HookConfig,
    HookRuntime,
    HookServices,
    cap_for as cap_for,
)
from .policy import user_nudge
from .recovery import RecoveryStore
from .runtime_config import settings_for
from .state import record_read, reset_session
from .tool_proxy import proxy_read

def _passthrough() -> int:
    """Return the successful exit status that tells Claude to keep original data."""

    return 0


def _config_from_env(root: Path | None = None) -> HookConfig:
    """Resolve project configuration with environment-variable overrides."""

    settings = settings_for(root)
    return HookConfig(
        disabled=settings.disabled,
        delta_enabled=settings.delta,
        min_lines=settings.min_lines,
        keep_tail=settings.keep_tail,
        max_lines=settings.max_lines,
        min_net_tokens=MIN_NET_TOKENS,
        output_policy_enabled=settings.output_policy,
        task_checklist_enabled=settings.output_task_checklist,
        output_policy_mode=settings.output_mode,
        output_policy_task=settings.output_task,
        output_policy_adaptive=settings.output_adaptive,
        output_policy_min_tokens=settings.output_min_tokens,
        output_policy_max_tokens=settings.output_max_tokens,
        output_policy_calibration_file=settings.output_calibration_file,
        output_telemetry_enabled=settings.output_telemetry,
        model_routing_enabled=settings.model_routing_enabled,
        model_routing_mode=settings.model_routing_mode,
        model_routing_current_model=settings.model_routing_current_model,
        model_routing_allowed_models=settings.model_routing_allowed_models,
        model_routing_min_savings=settings.model_routing_min_savings,
        model_routing_conservative=settings.model_routing_conservative,
        model_routing_calibration_file=settings.model_routing_calibration_file,
        efficiency_enabled=settings.efficiency_enabled,
        continuity_enabled=settings.continuity_enabled,
        cross_turn_dedup_enabled=settings.cross_turn_dedup,
        waste_detection_enabled=settings.waste_detection,
        ingress_enabled=settings.ingress_enabled,
        ingress_threshold_tokens=settings.ingress_threshold_tokens,
        ingress_packet_tokens=settings.ingress_packet_tokens,
        tool_proxy_enabled=settings.tool_proxy_enabled,
        tool_proxy_provider=settings.tool_proxy_provider,
        tool_proxy_model=settings.tool_proxy_model,
        tool_proxy_endpoint=settings.tool_proxy_endpoint,
        tool_proxy_min_tokens=settings.tool_proxy_min_tokens,
        tool_proxy_target_tokens=settings.tool_proxy_target_tokens,
        tool_proxy_model_input_tokens=settings.tool_proxy_model_input_tokens,
        tool_proxy_timeout_seconds=settings.tool_proxy_timeout_seconds,
        tool_proxy_max_ranges=settings.tool_proxy_max_ranges,
        tool_proxy_max_range_lines=settings.tool_proxy_max_range_lines,
    )


def _services() -> HookServices:
    """Compose concrete ACCO services for the Claude adapter.

    Construction happens per top-level call so tests and embedders can replace
    module-level callables without hidden singleton state.
    """

    from .output_store import store_output as store_output_service

    return HookServices(
        guard=guard_run,
        output_pipeline=OutputPipeline(),
        apply_delta=apply_delta,
        store_output=store_output_service,
        user_nudge=user_nudge,
        generation_policy=automatic_output_policy,
        task_checklist=task_checklist_note,
        reset_session=reset_session,
        record_read=record_read,
        digest=_digest,
        estimate_tokens=estimate_tokens,
        telemetry_start=start_output_turn,
        telemetry_finish=finish_output_turn,
        efficiency_session_start=start_session,
        continuity_context=continuity_context,
        guardian_checkpoint=capture_guardian,
        efficiency_prompt=observe_prompt,
        deduplicate_output=deduplicate_output,
        observe_tool=observe_tool,
        ingress_optimizer=maybe_stage_prompt,
        smart_read_proxy=proxy_read,
        model_route=automatic_model_route,
        recovery_output=lambda root, text, **kwargs: RecoveryStore(root).put(
            text,
            content_type=str(kwargs.get("content_type", "text/plain")),
            metadata=(
                kwargs.get("metadata")
                if isinstance(kwargs.get("metadata"), dict)
                else {}
            ),
        ),
    )


def _runtime(root: Path | None = None) -> HookRuntime:
    """Build the Claude runtime from project config plus environment overrides."""

    return HookRuntime(_services(), _config_from_env(root))


def _payload_root(payload: dict) -> Path:
    """Resolve the project root carried by one Claude hook payload."""

    raw = payload.get("cwd") or payload.get("cwd_path")
    return Path(str(raw)) if raw else Path.cwd()


def run_post(payload: dict) -> tuple[int, dict | None]:
    """Process a Claude post-tool payload through the default runtime."""

    return _runtime(_payload_root(payload)).run_post(payload)


def run_session_start(payload: dict) -> tuple[int, dict | None]:
    """Process a Claude session-start payload through the default runtime."""

    return _runtime(_payload_root(payload)).run_session_start(payload)


def run_user_prompt(payload: dict) -> tuple[int, dict | None]:
    """Process a Claude user-prompt payload through the default runtime."""

    return _runtime(_payload_root(payload)).run_user_prompt(payload)


def run_post_read(payload: dict) -> None:
    """Record a Claude full-file read through the default runtime."""

    _runtime(_payload_root(payload)).run_post_read(payload)


def run(payload: dict) -> tuple[int, dict | None]:
    """Process one Claude hook payload through the default runtime."""

    return _runtime(_payload_root(payload)).run(payload)


def main(argv: list[str] | None = None) -> int:
    """Run the selected coding-host hook JSON stdin/stdout adapter."""

    parser = argparse.ArgumentParser(prog="acco hook")
    parser.add_argument(
        "--host",
        choices=["claude", "cursor", "gemini", "qwen", "copilot"],
        default="claude",
    )
    parser.add_argument("--event")
    args = parser.parse_args(argv)
    if args.host != "claude":
        if not args.event:
            parser.error("--event is required when --host is not claude")
        from .native_hooks import main as native_main

        return native_main(args.host, args.event)

    if args.event:
        parser.error("--event is only used with non-Claude hosts")
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return _passthrough()
    if not isinstance(payload, dict):
        return _passthrough()
    try:
        code, response = run(payload)
    except Exception as exc:
        print(f"acco hook error: {exc}", file=sys.stderr)
        return _passthrough()
    if response is not None:
        json.dump(response, sys.stdout)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
