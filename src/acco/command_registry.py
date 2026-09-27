"""Extensible command registry for the top-level ACCO CLI."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .command_handlers.budget import context_budget_main
from .command_handlers.context import (
    browse_main,
    feedback_main,
    impact_main,
    knowledge_status_main,
    ranking_explain_main,
    recall_main,
    remember_main,
    semantic_index_main,
    semantic_status_main,
)
from .command_handlers.efficiency import (
    audit_main,
    cache_economics_main,
    continuity_main,
    cost_advisor_main,
    dashboard_main,
    learn_main,
)
from .command_handlers.everyday import (
    claude_main,
    codex_main,
    context_audit_main,
    gemini_main,
    guardian_main,
    lean_skill_main,
    statusline_main,
    wrap_main,
)
from .command_handlers.evaluation import (
    agent_evaluate_main,
    blind_grade_main,
    evaluate_main,
    ranking_calibrate_main,
    ranking_diff_main,
    ranking_snapshot_main,
)
from .command_handlers.experiment import (
    cost_report_main,
    evidence_run_main,
    experiment_main,
    knowledge_holdout_evaluate_main,
    knowledge_holdout_main,
    session_holdout_evaluate_main,
    session_holdout_main,
    trial_main,
)
from .command_handlers.host import (
    claude_plugin_path_main,
    client_capabilities_main,
    commands_main,
    fastpath_status_main,
    completion_main,
    doctor_main,
    host_check_main,
    transport_status_main,
    serve_main,
    setup_main,
    uninstall_main,
)
from .command_handlers.ingress import ingress_read_main, ingress_show_main
from .command_handlers.model_routing import (
    model_route_calibrate_main,
    model_route_main,
)
from .command_handlers.optimization import (
    browser_context_main,
    optimize_main,
    prefix_status_main,
    provider_proxy_main,
    recover_main,
    recovery_status_main,
)
from .command_handlers.output import (
    corpus_analyze_main,
    output_benchmark_main,
    output_calibrate_main,
    output_effectiveness_main,
    output_explain_main,
    output_policy_main,
    output_replay_main,
    output_save_main,
    output_telemetry_main,
)
from .command_handlers.patch import pack_diff_main, review_main
from .command_handlers.persistent_proxy import proxy_main
from .command_handlers.pricing import pricing_main
from .command_handlers.sdk import sdk_serve_main
from .command_handlers.workspace import workspace_main
from .pack_cli import main as pack_main
from .command_handlers.product import (
    advanced_main,
    bootstrap_main,
    demo_main,
    savings_main,
    start_main,
    status_main,
    update_main,
)

CommandHandler = Callable[[list[str]], int]


@dataclass(frozen=True)
class CommandSpec:
    """Bind one top-level command name to its handler."""

    name: str
    handler: CommandHandler


class CommandRegistry:
    """Dispatch top-level commands without embedding command knowledge in entry.py."""

    def __init__(self, specs: Iterable[CommandSpec]):
        """Build a registry and reject ambiguous duplicate command names."""
        handlers: dict[str, CommandHandler] = {}
        for spec in specs:
            if spec.name in handlers:
                raise ValueError(f"duplicate command registration: {spec.name}")
            handlers[spec.name] = spec.handler
        self._handlers = handlers

    def dispatch(self, args: list[str], fallback: CommandHandler) -> int:
        """Dispatch ``args`` to a registered handler or ``fallback``."""
        if not args:
            return fallback(args)
        handler = self._handlers.get(args[0])
        if handler is None:
            return fallback(args)
        return handler(args[1:])

    def names(self) -> tuple[str, ...]:
        """Return registered command names in deterministic order."""
        return tuple(sorted(self._handlers))


DEFAULT_COMMAND_REGISTRY = CommandRegistry(
    [
        CommandSpec("pack", pack_main),
        CommandSpec("context-budget", context_budget_main),
        CommandSpec("workspace", workspace_main),
        CommandSpec("impact", impact_main),
        CommandSpec("browse", browse_main),
        CommandSpec("feedback", feedback_main),
        CommandSpec("ranking-explain", ranking_explain_main),
        CommandSpec("remember", remember_main),
        CommandSpec("recall", recall_main),
        CommandSpec("knowledge-status", knowledge_status_main),
        CommandSpec("semantic-index", semantic_index_main),
        CommandSpec("semantic-status", semantic_status_main),
        CommandSpec("evaluate", evaluate_main),
        CommandSpec("agent-evaluate", agent_evaluate_main),
        CommandSpec("blind-grade", blind_grade_main),
        CommandSpec("ranking-snapshot", ranking_snapshot_main),
        CommandSpec("ranking-diff", ranking_diff_main),
        CommandSpec("ranking-calibrate", ranking_calibrate_main),
        CommandSpec("experiment", experiment_main),
        CommandSpec("trial", trial_main),
        CommandSpec("evidence-run", evidence_run_main),
        CommandSpec("session-holdout", session_holdout_main),
        CommandSpec("knowledge-holdout", knowledge_holdout_main),
        CommandSpec("knowledge-holdout-evaluate", knowledge_holdout_evaluate_main),
        CommandSpec("session-holdout-evaluate", session_holdout_evaluate_main),
        CommandSpec("cost-report", cost_report_main),
        CommandSpec("cost-advisor", cost_advisor_main),
        CommandSpec("pricing", pricing_main),
        CommandSpec("model-route", model_route_main),
        CommandSpec("model-route-calibrate", model_route_calibrate_main),
        CommandSpec("audit", audit_main),
        CommandSpec("dashboard", dashboard_main),
        CommandSpec("learn", learn_main),
        CommandSpec("optimize", optimize_main),
        CommandSpec("recover", recover_main),
        CommandSpec("recovery-status", recovery_status_main),
        CommandSpec("prefix-status", prefix_status_main),
        CommandSpec("provider-proxy", provider_proxy_main),
        CommandSpec("proxy", proxy_main),
        CommandSpec("browser-context", browser_context_main),
        CommandSpec("cache-economics", cache_economics_main),
        CommandSpec("continuity", continuity_main),
        CommandSpec("guardian", guardian_main),
        CommandSpec("wrap", wrap_main),
        CommandSpec("claude", claude_main),
        CommandSpec("codex", codex_main),
        CommandSpec("gemini", gemini_main),
        CommandSpec("lean-skill", lean_skill_main),
        CommandSpec("context-audit", context_audit_main),
        CommandSpec("statusline", statusline_main),
        CommandSpec("bootstrap", bootstrap_main),
        CommandSpec("start", start_main),
        CommandSpec("status", status_main),
        CommandSpec("demo", demo_main),
        CommandSpec("savings", savings_main),
        CommandSpec("update", update_main),
        CommandSpec("advanced", advanced_main),
        CommandSpec("setup", setup_main),
        CommandSpec("doctor", doctor_main),
        CommandSpec("uninstall", uninstall_main),
        CommandSpec("completion", completion_main),
        CommandSpec("commands", commands_main),
        CommandSpec("host-check", host_check_main),
        CommandSpec("transport-status", transport_status_main),
        CommandSpec("claude-plugin-path", claude_plugin_path_main),
        CommandSpec("client-capabilities", client_capabilities_main),
        CommandSpec("fastpath-status", fastpath_status_main),
        CommandSpec("ingress-show", ingress_show_main),
        CommandSpec("ingress-read", ingress_read_main),
        CommandSpec("corpus-analyze", corpus_analyze_main),
        CommandSpec("output-policy", output_policy_main),
        CommandSpec("output-benchmark", output_benchmark_main),
        CommandSpec("output-calibrate", output_calibrate_main),
        CommandSpec("output-effectiveness", output_effectiveness_main),
        CommandSpec("output-explain", output_explain_main),
        CommandSpec("output-replay", output_replay_main),
        CommandSpec("output-save", output_save_main),
        CommandSpec("output-telemetry", output_telemetry_main),
        CommandSpec("serve", serve_main),
        CommandSpec("sdk-serve", sdk_serve_main),
        CommandSpec("pack-diff", pack_diff_main),
        CommandSpec("review", review_main),
    ]
)
