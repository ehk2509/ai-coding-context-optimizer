"""Provider-request transformation with recovery, schema, and prefix accounting."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .context_budget import ContextBudgetPlan, plan_context_budget
from .context_router import route_context
from .efficiency.store import append_event
from .estimate import estimate_tokens
from .prefix_cache import (
    PrefixPlan,
    conversation_epoch_key,
    observe_prefix,
    reusable_history_counts,
    stable_prefix_fingerprint,
)
from .provider_cache import (
    apply_provider_cache_plan,
    plan_provider_cache,
    record_cache_plan,
)
from .provider_cost import (
    PROVIDER_MODEL_ROUTING_MODES,
    apply_calibrated_provider_route,
    deduplicate_provider_history,
)
from .provider_boundary import (
    ProviderRequestProfile,
    detect_provider_request,
    gemini_function_responses,
    iter_gemini_function_response_strings,
    latest_user_text,
)
from .recovery import RecoveryCapacityError, RecoveryStore
from .tool_schema import compress_tool_catalog


@dataclass(frozen=True)
class ProviderTransformResult:
    """Describe one local provider-request optimization pass."""

    body: dict
    changed: bool
    original_tokens: int
    output_tokens: int
    recovery_handles: tuple[str, ...]
    schema_recovery_handle: str | None
    prefix: PrefixPlan
    profile: ProviderRequestProfile
    transformed_segments: int = 0
    deduplicated_segments: int = 0
    estimated_duplicate_tokens_saved: int = 0
    model_routing: dict[str, Any] | None = None
    context_budget: dict[str, Any] | None = None
    cache_plan: dict[str, Any] | None = None

    def metadata(self) -> dict:
        """Return request transformation metadata without request content."""
        return {
            "changed": self.changed,
            "original_tokens": self.original_tokens,
            "output_tokens": self.output_tokens,
            "token_reduction": (
                max(0.0, 1.0 - self.output_tokens / self.original_tokens)
                if self.original_tokens else 0.0
            ),
            "recovery_handles": list(self.recovery_handles),
            "schema_recovery_handle": self.schema_recovery_handle,
            "prefix": self.prefix.to_dict(),
            "request": self.profile.to_dict(),
            "transformed_segments": self.transformed_segments,
            "deduplicated_segments": self.deduplicated_segments,
            "estimated_duplicate_tokens_saved": self.estimated_duplicate_tokens_saved,
            "model_routing": self.model_routing or {
                "mode": "off",
                "evaluated": False,
                "applied": False,
            },
            "context_budget": self.context_budget,
            "cache_plan": self.cache_plan,
            "policy": "retrieval-first-historical-only",
        }


def _json_tokens(value: Any) -> int:
    """Estimate tokens in compact JSON serialization."""
    return estimate_tokens(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _tool_result_token_segments(
    body: dict,
    profile: ProviderRequestProfile,
) -> list[int]:
    """Return content-free token sizes for explicit historical tool-result strings."""
    segments: list[int] = []
    messages = body.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if message.get("role") == "tool" and isinstance(content, str):
                segments.append(estimate_tokens(content))
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    value = block.get("content")
                    if isinstance(value, str):
                        segments.append(estimate_tokens(value))
                    elif isinstance(value, list):
                        for item in value:
                            if (
                                isinstance(item, dict)
                                and item.get("type") == "text"
                                and isinstance(item.get("text"), str)
                            ):
                                segments.append(estimate_tokens(item["text"]))

    input_items = body.get("input")
    if isinstance(input_items, list):
        for item in input_items:
            if (
                isinstance(item, dict)
                and item.get("type") in {"function_call_output", "tool_result"}
                and isinstance(item.get("output"), str)
            ):
                segments.append(estimate_tokens(item["output"]))

    if profile.provider == "gemini":
        for parent, key in gemini_function_responses(body):
            response = parent[key]
            if isinstance(response, str):
                segments.append(estimate_tokens(response))
            elif isinstance(response, (dict, list)):
                for leaf_parent, leaf_key in iter_gemini_function_response_strings(response):
                    segments.append(estimate_tokens(leaf_parent[leaf_key]))
    return segments


def _provider_context_budget(
    body: dict,
    profile: ProviderRequestProfile,
    *,
    total_tokens: int | None,
) -> tuple[ContextBudgetPlan | None, list[int], int]:
    """Plan provider-side schema/tool slices from observed request demand."""
    segments = _tool_result_token_segments(body, profile)
    schema_tokens = (
        _json_tokens(body["tools"])
        if isinstance(body.get("tools"), list)
        else 0
    )
    if total_tokens is None:
        return None, segments, schema_tokens
    observed = {
        "tool_results": sum(segments),
        "schemas": schema_tokens,
    }
    plan = plan_context_budget(
        latest_user_text(body, profile),
        total_tokens=total_tokens,
        observed_tokens=observed,
    )
    return plan, segments, schema_tokens


def _tool_name_index(body: dict) -> dict[str, str]:
    """Map provider tool-call ids to bounded stable tool names."""
    names: dict[str, str] = {}
    messages = body.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        call_id = block.get("id")
                        name = block.get("name")
                        if isinstance(call_id, str) and isinstance(name, str):
                            names[call_id] = name[:96]
            calls = message.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    call_id = call.get("id")
                    function = call.get("function")
                    name = function.get("name") if isinstance(function, dict) else None
                    if isinstance(call_id, str) and isinstance(name, str):
                        names[call_id] = name[:96]
    input_items = body.get("input")
    if isinstance(input_items, list):
        for item in input_items:
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            call_id = item.get("call_id") or item.get("id")
            name = item.get("name")
            if isinstance(call_id, str) and isinstance(name, str):
                names[call_id] = name[:96]
    return names

def _compress_tool_text(
    text: str,
    *,
    query: str,
    recovery: RecoveryStore,
    min_tokens: int,
) -> tuple[str, str | None]:
    """Route one large historical tool-result string through exact recovery."""
    if estimate_tokens(text) < min_tokens:
        return text, None
    result = route_context(
        text,
        query=query,
        recovery=recovery,
        command="provider-tool-result",
        max_lines=100,
        min_reduction=0.08,
    )
    return (
        result.text,
        result.recovery_handle if result.changed else None,
    )


def _transform_content_blocks(
    blocks: list,
    *,
    query: str,
    recovery: RecoveryStore,
    min_tokens: int,
    handles: list[str],
) -> tuple[list, int]:
    """Transform Anthropic-style historical tool-result content blocks."""
    out = []
    changed = 0
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            out.append(block)
            continue
        updated = dict(block)
        content = updated.get("content")
        if isinstance(content, str):
            transformed, handle = _compress_tool_text(
                content,
                query=query,
                recovery=recovery,
                min_tokens=min_tokens,
            )
            updated["content"] = transformed
            if handle:
                handles.append(handle)
                changed += 1
        elif isinstance(content, list):
            new_content = []
            for item in content:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "text"
                    and isinstance(item.get("text"), str)
                ):
                    transformed, handle = _compress_tool_text(
                        item["text"],
                        query=query,
                        recovery=recovery,
                        min_tokens=min_tokens,
                    )
                    item = dict(item)
                    item["text"] = transformed
                    if handle:
                        handles.append(handle)
                        changed += 1
                new_content.append(item)
            updated["content"] = new_content
        out.append(updated)
    return out, changed


def _transform_messages(
    transformed: dict,
    *,
    query: str,
    recovery: RecoveryStore,
    min_tokens: int,
    handles: list[str],
) -> int:
    """Transform explicit historical tool outputs deterministically."""
    messages = transformed.get("messages")
    if not isinstance(messages, list):
        return 0
    changed = 0
    new_messages = []
    for message in messages:
        if not isinstance(message, dict):
            new_messages.append(message)
            continue
        updated = dict(message)
        content = updated.get("content")
        if isinstance(content, list):
            updated["content"], count = _transform_content_blocks(
                content,
                query=query,
                recovery=recovery,
                min_tokens=min_tokens,
                handles=handles,
            )
            changed += count
        if updated.get("role") == "tool" and isinstance(content, str):
            updated["content"], handle = _compress_tool_text(
                content,
                query=query,
                recovery=recovery,
                min_tokens=min_tokens,
            )
            if handle:
                handles.append(handle)
                changed += 1
        new_messages.append(updated)
    transformed["messages"] = new_messages
    return changed


def _transform_openai_input(
    transformed: dict,
    *,
    query: str,
    recovery: RecoveryStore,
    min_tokens: int,
    handles: list[str],
) -> int:
    """Transform OpenAI Responses historical tool outputs deterministically."""
    input_items = transformed.get("input")
    if not isinstance(input_items, list):
        return 0
    changed = 0
    new_input = []
    for item in input_items:
        if (
            isinstance(item, dict)
            and item.get("type") in {"function_call_output", "tool_result"}
            and isinstance(item.get("output"), str)
        ):
            item = dict(item)
            item["output"], handle = _compress_tool_text(
                item["output"],
                query=query,
                recovery=recovery,
                min_tokens=min_tokens,
            )
            if handle:
                handles.append(handle)
                changed += 1
        new_input.append(item)
    transformed["input"] = new_input
    return changed


def _transform_gemini(
    transformed: dict,
    *,
    query: str,
    recovery: RecoveryStore,
    min_tokens: int,
    handles: list[str],
) -> int:
    """Transform long string leaves inside Gemini functionResponse payloads."""
    changed = 0
    for parent, key in gemini_function_responses(transformed):
        response = parent[key]
        if isinstance(response, str):
            candidate, handle = _compress_tool_text(
                response,
                query=query,
                recovery=recovery,
                min_tokens=min_tokens,
            )
            parent[key] = candidate
            if handle:
                handles.append(handle)
                changed += 1
            continue
        if not isinstance(response, (dict, list)):
            continue
        for leaf_parent, leaf_key in iter_gemini_function_response_strings(response):
            value = leaf_parent[leaf_key]
            candidate, handle = _compress_tool_text(
                value,
                query=query,
                recovery=recovery,
                min_tokens=min_tokens,
            )
            leaf_parent[leaf_key] = candidate
            if handle:
                handles.append(handle)
                changed += 1
    return changed


def transform_provider_request(
    root: Path,
    provider: str,
    body: dict,
    *,
    request_path: str = "",
    compress_schemas: bool = True,
    compress_tool_results: bool = True,
    deduplicate_history: bool = True,
    tool_result_min_tokens: int = 800,
    recovery_capacity_bytes: int = 512 * 1024 * 1024,
    prefix_tracking: bool = True,
    model_routing_mode: str = "off",
    model_routing_calibration_file: str = ".acco.routing-calibration.json",
    model_routing_min_savings: float = 0.05,
    live_zone: bool = True,
    context_budget_total_tokens: int | None = None,
    provider_cache_mode: str = "plan",
    provider_cache_expected_reuses: int = 2,
) -> ProviderTransformResult:
    """Optimize historical provider context while leaving current task/source intact."""
    if not isinstance(body, dict):
        raise ValueError("provider request body must be a JSON object")
    profile = detect_provider_request(provider, body, path=request_path)
    original_tokens = _json_tokens(body)
    transformed = deepcopy(body)
    recovery = RecoveryStore(root, capacity_bytes=recovery_capacity_bytes)
    handles: list[str] = []
    schema_handle = None
    transformed_segments = 0
    deduplicated_segments = 0
    duplicate_tokens_saved = 0
    routing_metadata: dict[str, Any] = {
        "mode": str(model_routing_mode or "off").strip().lower(),
        "evaluated": False,
        "applied": False,
    }
    context_plan, tool_segment_tokens, schema_tokens = _provider_context_budget(
        body,
        profile,
        total_tokens=context_budget_total_tokens,
    )
    effective_tool_result_min_tokens = tool_result_min_tokens
    compress_schema_for_budget = True
    compress_tools_for_budget = True
    if context_plan is not None:
        schema_budget = context_plan.tokens_for("schemas")
        tool_budget = context_plan.tokens_for("tool_results")
        compress_schema_for_budget = schema_tokens > schema_budget
        total_tool_tokens = sum(tool_segment_tokens)
        compress_tools_for_budget = total_tool_tokens > tool_budget
        if compress_tools_for_budget and tool_segment_tokens:
            target_per_segment = max(
                120,
                tool_budget // len(tool_segment_tokens),
            )
            effective_tool_result_min_tokens = min(
                tool_result_min_tokens,
                target_per_segment,
            )

    protected_messages = 0
    protected_input = 0
    if live_zone and prefix_tracking:
        protected_messages, protected_input = reusable_history_counts(
            root, profile.provider, body
        )

    normalized_routing_mode = str(model_routing_mode or "off").strip().lower()
    if normalized_routing_mode not in PROVIDER_MODEL_ROUTING_MODES:
        raise ValueError(
            "provider model routing mode must be one of: "
            + ", ".join(PROVIDER_MODEL_ROUTING_MODES)
        )
    if not 0 <= model_routing_min_savings <= 1:
        raise ValueError("model_routing_min_savings must be between 0 and 1")
    cache_mode = str(provider_cache_mode or "off").strip().lower()
    if cache_mode not in {"off", "plan", "apply"}:
        raise ValueError("provider_cache_mode must be one of: off, plan, apply")
    if isinstance(provider_cache_expected_reuses, bool) or int(provider_cache_expected_reuses) < 0:
        raise ValueError("provider_cache_expected_reuses must be nonnegative")

    try:
        history = deduplicate_provider_history(
            transformed,
            profile,
            recovery=recovery,
            min_tokens=effective_tool_result_min_tokens,
            enabled=deduplicate_history and not (protected_messages or protected_input),
        )
        if history.segments:
            handles.extend(history.recovery_handles)
            deduplicated_segments = history.segments
            duplicate_tokens_saved = history.estimated_tokens_saved

        if (
            compress_schemas
            and compress_schema_for_budget
            and isinstance(transformed.get("tools"), list)
        ):
            schema = compress_tool_catalog(
                transformed["tools"],
                recovery=recovery,
                min_reduction=0.02,
            )
            if schema.changed:
                transformed["tools"] = schema.value
                schema_handle = schema.recovery_handle

        if compress_tool_results and compress_tools_for_budget:
            query = "" if live_zone else latest_user_text(transformed, profile)
            transformed_segments += _transform_messages(
                transformed,
                query=query,
                recovery=recovery,
                min_tokens=effective_tool_result_min_tokens,
                handles=handles,
            )
            transformed_segments += _transform_openai_input(
                transformed,
                query=query,
                recovery=recovery,
                min_tokens=effective_tool_result_min_tokens,
                handles=handles,
            )
            if profile.provider == "gemini":
                transformed_segments += _transform_gemini(
                    transformed,
                    query=query,
                    recovery=recovery,
                    min_tokens=effective_tool_result_min_tokens,
                    handles=handles,
                )
    except RecoveryCapacityError:
        transformed = deepcopy(body)
        handles = []
        schema_handle = None
        transformed_segments = 0
        deduplicated_segments = 0
        duplicate_tokens_saved = 0

    routing_metadata = apply_calibrated_provider_route(
        root,
        transformed,
        profile,
        prompt=latest_user_text(transformed, profile),
        input_tokens=original_tokens,
        mode=normalized_routing_mode,
        calibration_file=model_routing_calibration_file,
        min_savings=model_routing_min_savings,
    )

    cache_metadata: dict[str, Any] | None = None
    cache_applied = False
    if cache_mode != "off":
        fingerprint, tokens, size, components = stable_prefix_fingerprint(transformed)
        epoch = conversation_epoch_key(body)
        provisional_prefix = PrefixPlan(
            fingerprint=fingerprint,
            stable_tokens=tokens,
            stable_bytes=size,
            components=components,
            previous_fingerprint=None,
            reused=False,
            epoch_key=epoch,
        )
        cache_plan = plan_provider_cache(
            profile.provider,
            provisional_prefix,
            model=(
                str(transformed.get("model"))
                if isinstance(transformed.get("model"), str)
                else None
            ),
            expected_reuses=int(provider_cache_expected_reuses),
        )
        record_cache_plan(root, cache_plan)
        cache_metadata = cache_plan.to_dict()
        cache_metadata["mode"] = cache_mode
        if cache_mode == "apply":
            transformed, cache_applied, apply_reason = apply_provider_cache_plan(
                transformed,
                cache_plan,
            )
            cache_metadata["applied"] = cache_applied
            cache_metadata["apply_reason"] = apply_reason
        else:
            cache_metadata["applied"] = False
            cache_metadata["apply_reason"] = "plan_only"

    output_tokens = _json_tokens(transformed)
    routing_applied = bool(routing_metadata.get("applied"))
    changed = (
        transformed != body
        and (output_tokens < original_tokens or routing_applied or cache_applied)
    )
    if not changed:
        transformed = deepcopy(body)
        handles = []
        schema_handle = None
        transformed_segments = 0
        deduplicated_segments = 0
        duplicate_tokens_saved = 0
        output_tokens = original_tokens
    elif duplicate_tokens_saved > 0:
        try:
            append_event(
                root,
                {
                    "kind": "saving",
                    "feature": "provider_history_dedup",
                    "estimated_tokens_saved": duplicate_tokens_saved,
                    "segments": deduplicated_segments,
                    "provider": profile.provider,
                },
            )
        except OSError:
            pass

    prefix_provider = profile.provider
    if prefix_tracking:
        prefix = observe_prefix(
            root,
            prefix_provider,
            transformed,
            source_body=body,
        )
    else:
        fingerprint, tokens, size, components = stable_prefix_fingerprint(
            transformed
        )
        prefix = PrefixPlan(
            fingerprint=fingerprint,
            stable_tokens=tokens,
            stable_bytes=size,
            components=components,
            previous_fingerprint=None,
            reused=False,
            epoch_key=conversation_epoch_key(body),
        )
    return ProviderTransformResult(
        body=transformed,
        changed=changed,
        original_tokens=original_tokens,
        output_tokens=output_tokens,
        recovery_handles=tuple(dict.fromkeys(handles)),
        schema_recovery_handle=schema_handle,
        prefix=prefix,
        profile=profile,
        transformed_segments=transformed_segments,
        deduplicated_segments=deduplicated_segments,
        estimated_duplicate_tokens_saved=duplicate_tokens_saved,
        model_routing=routing_metadata,
        context_budget=context_plan.to_dict() if context_plan is not None else None,
        cache_plan=cache_metadata,
    )
