"""Project-level runtime configuration with environment overrides."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path

from .generation_policy import OUTPUT_TASK_OPTIONS
from .model_routing import (
    DEFAULT_ALLOWED_MODELS,
    DEFAULT_ROUTING_CALIBRATION_FILE,
    ROUTING_MODES,
)
from .output_saver import OUTPUT_MODES

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

CONFIG_NAME = ".acco.toml"
MCP_PROFILES = ("minimal", "context", "memory", "adaptive", "full")


@dataclass(frozen=True)
class RuntimeSettings:
    """Resolved ACCO runtime settings for one project."""

    disabled: bool = False
    guard: bool = True
    read_max_lines: int = 220
    reread: bool = False
    allow: tuple[str, ...] = ()
    delta: bool = False
    min_lines: int = 40
    max_lines: int | None = None
    keep_tail: int = 15
    output_policy: bool = True
    output_task_checklist: bool = True
    output_mode: str = "normal"
    output_task: str = "auto"
    output_adaptive: bool = True
    output_min_tokens: int | None = None
    output_max_tokens: int | None = None
    output_calibration_file: str = ".acco.output-calibration.json"
    output_telemetry: bool = True
    model_routing_enabled: bool = False
    model_routing_mode: str = "advisory"
    model_routing_current_model: str = ""
    model_routing_allowed_models: tuple[str, ...] = DEFAULT_ALLOWED_MODELS
    model_routing_min_savings: float = 0.05
    model_routing_conservative: bool = True
    model_routing_calibration_file: str = DEFAULT_ROUTING_CALIBRATION_FILE
    efficiency_enabled: bool = True
    continuity_enabled: bool = True
    cross_turn_dedup: bool = True
    waste_detection: bool = True
    knowledge_read_avoidance: bool = False
    cache_economics: bool = False
    cache_expected_reuses: int = 2
    cache_write_factor: float = 1.25
    cache_read_factor: float = 0.10
    cache_min_relative_savings: float = 0.05
    ingress_enabled: bool = False
    ingress_threshold_tokens: int = 12000
    ingress_packet_tokens: int = 1600
    retrieval_cache: bool = True
    retrieval_cache_max_entries: int = 64
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
    mcp_profile: str = "full"
    mcp_adaptive_max_tools: int = 12
    mcp_compress_schemas: bool = False
    prefix_tracking: bool = True
    provider_history_dedup: bool = True
    provider_model_routing_mode: str = "off"
    provider_model_routing_calibration_file: str = DEFAULT_ROUTING_CALIBRATION_FILE
    provider_model_routing_min_savings: float = 0.05
    context_budget_enabled: bool = False
    context_budget_total_tokens: int = 12000


def find_project_config(start: Path | None = None) -> Path | None:
    """Find the nearest project config by walking toward the filesystem root."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _bool(value: object, fallback: bool) -> bool:
    """Normalize TOML booleans while preserving fallback for other values."""
    return value if isinstance(value, bool) else fallback


def _positive_int(value: object, fallback: int) -> int:
    """Normalize positive integer settings."""
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else fallback
    )


def _nonnegative_int(value: object, fallback: int) -> int:
    """Normalize a nonnegative integer setting."""
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else fallback
    )


def _choice(value: object, fallback: str, choices: tuple[str, ...]) -> str:
    """Normalize a string choice while preserving fallback for invalid values."""
    if not isinstance(value, str):
        return fallback
    normalized = value.strip().lower()
    return normalized if normalized in choices else fallback


def _string(value: object, fallback: str) -> str:
    """Normalize a non-empty string setting."""
    if not isinstance(value, str):
        return fallback
    normalized = value.strip()
    return normalized or fallback


def _positive_float(value: object, fallback: float) -> float:
    """Normalize a positive floating-point setting."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    numeric = float(value)
    return numeric if math.isfinite(numeric) and numeric > 0 else fallback


def _fraction(value: object, fallback: float) -> float:
    """Normalize one floating-point setting in the inclusive 0..1 range."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    numeric = float(value)
    return numeric if math.isfinite(numeric) and 0 <= numeric <= 1 else fallback


def _optional_positive_int(
    value: object, fallback: int | None
) -> int | None:
    """Normalize an optional positive integer setting."""
    if value is None:
        return None
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else fallback
    )


def _load_file(start: Path | None = None) -> RuntimeSettings:
    """Load the nearest TOML config without environment overrides."""
    path = find_project_config(start)
    if path is None:
        return RuntimeSettings()
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Invalid ACCO config: {path}") from exc
    hooks = payload.get("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"Expected [hooks] table in ACCO config: {path}")
    output = payload.get("output", {})
    if not isinstance(output, dict):
        raise ValueError(f"Expected [output] table in ACCO config: {path}")
    model_routing = payload.get("model_routing", {})
    if not isinstance(model_routing, dict):
        raise ValueError(
            f"Expected [model_routing] table in ACCO config: {path}"
        )
    efficiency = payload.get("efficiency", {})
    if not isinstance(efficiency, dict):
        raise ValueError(
            f"Expected [efficiency] table in ACCO config: {path}"
        )
    ingress = payload.get("ingress", {})
    if not isinstance(ingress, dict):
        raise ValueError(f"Expected [ingress] table in ACCO config: {path}")
    retrieval = payload.get("retrieval", {})
    if not isinstance(retrieval, dict):
        raise ValueError(f"Expected [retrieval] table in ACCO config: {path}")
    tool_proxy = payload.get("tool_proxy", {})
    if not isinstance(tool_proxy, dict):
        raise ValueError(f"Expected [tool_proxy] table in ACCO config: {path}")
    mcp = payload.get("mcp", {})
    if not isinstance(mcp, dict):
        raise ValueError(f"Expected [mcp] table in ACCO config: {path}")
    provider = payload.get("provider", {})
    if not isinstance(provider, dict):
        raise ValueError(f"Expected [provider] table in ACCO config: {path}")
    context_budget = payload.get("context_budget", {})
    if not isinstance(context_budget, dict):
        raise ValueError(f"Expected [context_budget] table in ACCO config: {path}")
    allow = hooks.get("allow", [])
    allow_tuple = (
        tuple(item for item in allow if isinstance(item, str))
        if isinstance(allow, list)
        else ()
    )
    keep_tail = hooks.get("keep_tail", 15)
    if not isinstance(keep_tail, int) or isinstance(keep_tail, bool):
        keep_tail = 15
    route_allowed = model_routing.get(
        "allowed_models", list(DEFAULT_ALLOWED_MODELS)
    )
    route_allowed_tuple = (
        tuple(
            item.strip()
            for item in route_allowed
            if isinstance(item, str) and item.strip()
        )
        if isinstance(route_allowed, list)
        else DEFAULT_ALLOWED_MODELS
    )
    if not route_allowed_tuple:
        route_allowed_tuple = DEFAULT_ALLOWED_MODELS
    return RuntimeSettings(
        disabled=_bool(hooks.get("disabled"), False),
        guard=_bool(hooks.get("guard"), True),
        read_max_lines=_positive_int(hooks.get("read_max_lines"), 220),
        reread=_bool(hooks.get("reread"), False),
        allow=allow_tuple,
        delta=_bool(hooks.get("delta"), False),
        min_lines=_positive_int(hooks.get("min_lines"), 40),
        max_lines=_optional_positive_int(hooks.get("max_lines"), None),
        keep_tail=max(0, keep_tail),
        output_policy=_bool(output.get("enabled"), True),
        output_task_checklist=_bool(output.get("task_checklist"), True),
        output_mode=_choice(output.get("mode"), "normal", OUTPUT_MODES),
        output_task=_choice(output.get("task"), "auto", OUTPUT_TASK_OPTIONS),
        output_adaptive=_bool(output.get("adaptive"), True),
        output_min_tokens=_optional_positive_int(output.get("min_tokens"), None),
        output_max_tokens=_optional_positive_int(output.get("max_tokens"), None),
        output_calibration_file=_string(
            output.get("calibration_file"),
            ".acco.output-calibration.json",
        ),
        output_telemetry=_bool(output.get("telemetry"), True),
        model_routing_enabled=_bool(model_routing.get("enabled"), False),
        model_routing_mode=_choice(
            model_routing.get("mode"), "advisory", ROUTING_MODES
        ),
        model_routing_current_model=_string(
            model_routing.get("current_model"), ""
        ),
        model_routing_allowed_models=route_allowed_tuple,
        model_routing_min_savings=_fraction(
            model_routing.get("min_savings"), 0.05
        ),
        model_routing_conservative=_bool(
            model_routing.get("conservative"), True
        ),
        model_routing_calibration_file=_string(
            model_routing.get("calibration_file"),
            DEFAULT_ROUTING_CALIBRATION_FILE,
        ),
        efficiency_enabled=_bool(efficiency.get("enabled"), True),
        continuity_enabled=_bool(efficiency.get("continuity"), True),
        cross_turn_dedup=_bool(efficiency.get("dedup"), True),
        waste_detection=_bool(efficiency.get("waste_detection"), True),
        knowledge_read_avoidance=_bool(
            efficiency.get("knowledge_read_avoidance"),
            False,
        ),
        cache_economics=_bool(efficiency.get("cache_economics"), False),
        cache_expected_reuses=_nonnegative_int(
            efficiency.get("cache_expected_reuses"),
            2,
        ),
        cache_write_factor=_positive_float(
            efficiency.get("cache_write_factor"),
            1.25,
        ),
        cache_read_factor=_positive_float(
            efficiency.get("cache_read_factor"),
            0.10,
        ),
        cache_min_relative_savings=_fraction(
            efficiency.get("cache_min_relative_savings"),
            0.05,
        ),
        ingress_enabled=_bool(ingress.get("enabled"), False),
        ingress_threshold_tokens=_positive_int(
            ingress.get("threshold_tokens"),
            12000,
        ),
        ingress_packet_tokens=_positive_int(
            ingress.get("packet_tokens"),
            1600,
        ),
        retrieval_cache=_bool(retrieval.get("cache"), True),
        retrieval_cache_max_entries=_positive_int(
            retrieval.get("cache_max_entries"),
            64,
        ),
        tool_proxy_enabled=_bool(tool_proxy.get("enabled"), False),
        tool_proxy_provider=_choice(
            tool_proxy.get("provider"),
            "ollama",
            ("ollama", "deterministic"),
        ),
        tool_proxy_model=_string(tool_proxy.get("model"), "qwen2.5-coder:7b"),
        tool_proxy_endpoint=_string(
            tool_proxy.get("endpoint"),
            "http://127.0.0.1:11434",
        ),
        tool_proxy_min_tokens=_positive_int(
            tool_proxy.get("min_tokens"),
            2500,
        ),
        tool_proxy_target_tokens=_positive_int(
            tool_proxy.get("target_tokens"),
            1800,
        ),
        tool_proxy_model_input_tokens=_positive_int(
            tool_proxy.get("model_input_tokens"),
            12000,
        ),
        tool_proxy_timeout_seconds=_positive_float(
            tool_proxy.get("timeout_seconds"),
            6.0,
        ),
        tool_proxy_max_ranges=_positive_int(
            tool_proxy.get("max_ranges"),
            4,
        ),
        tool_proxy_max_range_lines=_positive_int(
            tool_proxy.get("max_range_lines"),
            80,
        ),
        mcp_profile=_choice(
            mcp.get("profile"),
            "full",
            MCP_PROFILES,
        ),
        mcp_adaptive_max_tools=min(
            24,
            max(
                7,
                _positive_int(
                    mcp.get("adaptive_max_tools"),
                    12,
                ),
            ),
        ),
        mcp_compress_schemas=_bool(
            mcp.get("compress_schemas"),
            False,
        ),
        prefix_tracking=_bool(
            provider.get("prefix_tracking"),
            True,
        ),
        provider_history_dedup=_bool(
            provider.get("history_dedup"),
            True,
        ),
        provider_model_routing_mode=_choice(
            provider.get("model_routing"),
            "off",
            ("off", "observe", "calibrated"),
        ),
        provider_model_routing_calibration_file=_string(
            provider.get("routing_calibration_file"),
            DEFAULT_ROUTING_CALIBRATION_FILE,
        ),
        provider_model_routing_min_savings=_fraction(
            provider.get("routing_min_savings"),
            0.05,
        ),
        context_budget_enabled=_bool(
            context_budget.get("enabled"),
            False,
        ),
        context_budget_total_tokens=max(
            1000,
            _positive_int(
                context_budget.get("total_tokens"),
                12000,
            ),
        ),
    )


def _env_bool(name: str, fallback: bool) -> bool:
    """Read a conventional boolean environment override."""
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_string(name: str, fallback: str) -> str:
    """Read a non-empty string environment override."""
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    normalized = raw.strip()
    return normalized or fallback


def _env_choice(name: str, fallback: str, choices: tuple[str, ...]) -> str:
    """Read a normalized string-choice environment override."""
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    normalized = raw.strip().lower()
    return normalized if normalized in choices else fallback


def _env_float(
    name: str,
    fallback: float,
    *,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float:
    """Read one floating-point environment override."""
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        value = float(raw)
    except ValueError:
        return fallback
    if not math.isfinite(value) or value < minimum or (
        maximum is not None and value > maximum
    ):
        return fallback
    return value


def _env_int(
    name: str, fallback: int | None, *, minimum: int = 1
) -> int | None:
    """Read an integer environment override."""
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        return max(minimum, int(raw))
    except ValueError:
        return fallback


def settings_for(start: Path | None = None) -> RuntimeSettings:
    """Resolve project config with environment variables taking precedence."""
    base = _load_file(start)
    allow_raw = os.environ.get("ACCO_ALLOW")
    allow = (
        tuple(part for part in allow_raw.split(":") if part)
        if allow_raw is not None
        else base.allow
    )
    max_lines = _env_int("ACCO_MAX_LINES", base.max_lines)
    read_max_lines = _env_int(
        "ACCO_READ_MAX_LINES", base.read_max_lines
    )
    min_lines = _env_int("ACCO_MIN_LINES", base.min_lines)
    keep_tail = _env_int(
        "ACCO_KEEP_TAIL", base.keep_tail, minimum=0
    )
    return RuntimeSettings(
        disabled=_env_bool("ACCO_DISABLED", base.disabled),
        guard=_env_bool("ACCO_GUARD", base.guard),
        read_max_lines=int(read_max_lines or base.read_max_lines),
        reread=_env_bool("ACCO_REREAD", base.reread),
        allow=allow,
        delta=_env_bool("ACCO_DELTA", base.delta),
        min_lines=int(min_lines or base.min_lines),
        max_lines=max_lines,
        keep_tail=int(keep_tail if keep_tail is not None else base.keep_tail),
        output_policy=_env_bool("ACCO_OUTPUT_POLICY", base.output_policy),
        output_task_checklist=_env_bool(
            "ACCO_TASK_CHECKLIST", base.output_task_checklist
        ),
        output_mode=_env_choice(
            "ACCO_OUTPUT_MODE", base.output_mode, OUTPUT_MODES
        ),
        output_task=_env_choice(
            "ACCO_OUTPUT_TASK", base.output_task, OUTPUT_TASK_OPTIONS
        ),
        output_adaptive=_env_bool(
            "ACCO_OUTPUT_ADAPTIVE", base.output_adaptive
        ),
        output_min_tokens=_env_int(
            "ACCO_OUTPUT_MIN_TOKENS", base.output_min_tokens
        ),
        output_max_tokens=_env_int(
            "ACCO_OUTPUT_MAX_TOKENS", base.output_max_tokens
        ),
        output_calibration_file=_env_string(
            "ACCO_OUTPUT_CALIBRATION_FILE",
            base.output_calibration_file,
        ),
        output_telemetry=_env_bool(
            "ACCO_OUTPUT_TELEMETRY", base.output_telemetry
        ),
        model_routing_enabled=_env_bool(
            "ACCO_MODEL_ROUTING", base.model_routing_enabled
        ),
        model_routing_mode=_env_choice(
            "ACCO_MODEL_ROUTING_MODE",
            base.model_routing_mode,
            ROUTING_MODES,
        ),
        model_routing_current_model=_env_string(
            "ACCO_MODEL_ROUTING_CURRENT_MODEL",
            base.model_routing_current_model,
        ),
        model_routing_allowed_models=(
            tuple(
                part.strip()
                for part in os.environ["ACCO_MODEL_ROUTING_ALLOWED"].split(":")
                if part.strip()
            )
            if os.environ.get("ACCO_MODEL_ROUTING_ALLOWED")
            else base.model_routing_allowed_models
        ),
        model_routing_min_savings=_env_float(
            "ACCO_MODEL_ROUTING_MIN_SAVINGS",
            base.model_routing_min_savings,
            minimum=0.0,
            maximum=1.0,
        ),
        model_routing_conservative=_env_bool(
            "ACCO_MODEL_ROUTING_CONSERVATIVE",
            base.model_routing_conservative,
        ),
        model_routing_calibration_file=_env_string(
            "ACCO_MODEL_ROUTING_CALIBRATION_FILE",
            base.model_routing_calibration_file,
        ),
        efficiency_enabled=_env_bool(
            "ACCO_EFFICIENCY", base.efficiency_enabled
        ),
        continuity_enabled=_env_bool(
            "ACCO_CONTINUITY", base.continuity_enabled
        ),
        cross_turn_dedup=_env_bool(
            "ACCO_CROSS_TURN_DEDUP", base.cross_turn_dedup
        ),
        waste_detection=_env_bool(
            "ACCO_WASTE_DETECTION", base.waste_detection
        ),
        knowledge_read_avoidance=_env_bool(
            "ACCO_KNOWLEDGE_READ_AVOIDANCE",
            base.knowledge_read_avoidance,
        ),
        cache_economics=_env_bool(
            "ACCO_CACHE_ECONOMICS",
            base.cache_economics,
        ),
        cache_expected_reuses=int(
            _env_int(
                "ACCO_CACHE_EXPECTED_REUSES",
                base.cache_expected_reuses,
                minimum=0,
            )
            or 0
        ),
        cache_write_factor=_env_float(
            "ACCO_CACHE_WRITE_FACTOR",
            base.cache_write_factor,
            minimum=0.000001,
        ),
        cache_read_factor=_env_float(
            "ACCO_CACHE_READ_FACTOR",
            base.cache_read_factor,
            minimum=0.000001,
        ),
        cache_min_relative_savings=_env_float(
            "ACCO_CACHE_MIN_RELATIVE_SAVINGS",
            base.cache_min_relative_savings,
            minimum=0.0,
            maximum=1.0,
        ),
        ingress_enabled=_env_bool(
            "ACCO_INGRESS_OPTIMIZER",
            base.ingress_enabled,
        ),
        ingress_threshold_tokens=int(
            _env_int(
                "ACCO_INGRESS_THRESHOLD_TOKENS",
                base.ingress_threshold_tokens,
                minimum=200,
            )
            or base.ingress_threshold_tokens
        ),
        ingress_packet_tokens=int(
            _env_int(
                "ACCO_INGRESS_PACKET_TOKENS",
                base.ingress_packet_tokens,
                minimum=200,
            )
            or base.ingress_packet_tokens
        ),
        retrieval_cache=_env_bool(
            "ACCO_RETRIEVAL_CACHE",
            base.retrieval_cache,
        ),
        retrieval_cache_max_entries=int(
            _env_int(
                "ACCO_RETRIEVAL_CACHE_MAX_ENTRIES",
                base.retrieval_cache_max_entries,
                minimum=1,
            )
            or base.retrieval_cache_max_entries
        ),
        tool_proxy_enabled=_env_bool(
            "ACCO_TOOL_PROXY",
            base.tool_proxy_enabled,
        ),
        tool_proxy_provider=_env_choice(
            "ACCO_TOOL_PROXY_PROVIDER",
            base.tool_proxy_provider,
            ("ollama", "deterministic"),
        ),
        tool_proxy_model=_env_string(
            "ACCO_TOOL_PROXY_MODEL",
            base.tool_proxy_model,
        ),
        tool_proxy_endpoint=_env_string(
            "ACCO_TOOL_PROXY_ENDPOINT",
            base.tool_proxy_endpoint,
        ),
        tool_proxy_min_tokens=int(
            _env_int(
                "ACCO_TOOL_PROXY_MIN_TOKENS",
                base.tool_proxy_min_tokens,
                minimum=200,
            )
            or base.tool_proxy_min_tokens
        ),
        tool_proxy_target_tokens=int(
            _env_int(
                "ACCO_TOOL_PROXY_TARGET_TOKENS",
                base.tool_proxy_target_tokens,
                minimum=200,
            )
            or base.tool_proxy_target_tokens
        ),
        tool_proxy_model_input_tokens=int(
            _env_int(
                "ACCO_TOOL_PROXY_MODEL_INPUT_TOKENS",
                base.tool_proxy_model_input_tokens,
                minimum=400,
            )
            or base.tool_proxy_model_input_tokens
        ),
        tool_proxy_timeout_seconds=_env_float(
            "ACCO_TOOL_PROXY_TIMEOUT_SECONDS",
            base.tool_proxy_timeout_seconds,
            minimum=0.2,
        ),
        tool_proxy_max_ranges=int(
            _env_int(
                "ACCO_TOOL_PROXY_MAX_RANGES",
                base.tool_proxy_max_ranges,
                minimum=1,
            )
            or base.tool_proxy_max_ranges
        ),
        tool_proxy_max_range_lines=int(
            _env_int(
                "ACCO_TOOL_PROXY_MAX_RANGE_LINES",
                base.tool_proxy_max_range_lines,
                minimum=1,
            )
            or base.tool_proxy_max_range_lines
        ),
        mcp_profile=_env_choice(
            "ACCO_MCP_PROFILE",
            base.mcp_profile,
            MCP_PROFILES,
        ),
        mcp_adaptive_max_tools=min(
            24,
            int(
                _env_int(
                    "ACCO_MCP_ADAPTIVE_MAX_TOOLS",
                    base.mcp_adaptive_max_tools,
                    minimum=7,
                )
                or base.mcp_adaptive_max_tools
            ),
        ),
        mcp_compress_schemas=_env_bool(
            "ACCO_MCP_COMPRESS_SCHEMAS",
            base.mcp_compress_schemas,
        ),
        prefix_tracking=_env_bool(
            "ACCO_PREFIX_TRACKING",
            base.prefix_tracking,
        ),
        provider_history_dedup=_env_bool(
            "ACCO_PROVIDER_HISTORY_DEDUP",
            base.provider_history_dedup,
        ),
        provider_model_routing_mode=_env_choice(
            "ACCO_PROVIDER_MODEL_ROUTING",
            base.provider_model_routing_mode,
            ("off", "observe", "calibrated"),
        ),
        provider_model_routing_calibration_file=_env_string(
            "ACCO_PROVIDER_ROUTING_CALIBRATION_FILE",
            base.provider_model_routing_calibration_file,
        ),
        provider_model_routing_min_savings=_env_float(
            "ACCO_PROVIDER_ROUTING_MIN_SAVINGS",
            base.provider_model_routing_min_savings,
            minimum=0.0,
            maximum=1.0,
        ),
        context_budget_enabled=_env_bool(
            "ACCO_CONTEXT_BUDGET",
            base.context_budget_enabled,
        ),
        context_budget_total_tokens=int(
            _env_int(
                "ACCO_CONTEXT_BUDGET_TOTAL_TOKENS",
                base.context_budget_total_tokens,
                minimum=1000,
            )
            or base.context_budget_total_tokens
        ),
    )
