"""Conversation-stable output shaping holdouts with measured token evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
import random
from pathlib import Path
from statistics import mean
from typing import Any

from .efficiency.store import append_event, load_events
from .generation_policy import classify_output_task
from .output_budget import adaptive_output_budget, load_output_calibration
from .provider_boundary import ProviderRequestProfile

EXPERIMENT_ID = "output-holdout-v1"


@dataclass(frozen=True)
class OutputHoldoutDecision:
    """Describe one deterministic conversation-level output-shaping assignment."""

    experiment: str
    arm: str
    epoch_key: str
    task: str
    mode: str
    budget_tokens: int
    enabled: bool
    eligible: bool
    applied: bool
    provider_field: str | None
    original_limit: int | None
    shaped_limit: int | None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible holdout metadata."""
        return asdict(self)


def holdout_epoch_key(body: dict, profile: ProviderRequestProfile) -> str:
    """Return a conversation-stable opaque experiment key when possible."""
    explicit = None
    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        for key in ("conversation_id", "session_id", "thread_id"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                explicit = value
                break
    if explicit is None:
        for key in ("conversation_id", "session_id", "thread_id", "user"):
            value = body.get(key)
            if isinstance(value, str) and value:
                explicit = value
                break

    anchor: dict[str, Any] = {
        "provider": profile.provider,
        "system": body.get("system"),
        "instructions": body.get("instructions"),
        "tools": body.get("tools"),
    }
    if explicit is not None:
        anchor["explicit_conversation"] = explicit
    else:
        if profile.provider == "gemini":
            contents = body.get("contents")
            if isinstance(contents, list) and contents:
                anchor["first_turn"] = contents[0]
        else:
            messages = body.get("messages")
            if isinstance(messages, list) and messages:
                anchor["first_turn"] = messages[0]
            else:
                input_items = body.get("input")
                if isinstance(input_items, list) and input_items:
                    anchor["first_turn"] = input_items[0]
                elif isinstance(input_items, str):
                    anchor["first_turn"] = input_items
    encoded = json.dumps(
        anchor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _control_arm(epoch_key: str, control_rate: float) -> bool:
    """Assign a conversation deterministically without storing prompt content."""
    digest = hashlib.sha256(
        f"{EXPERIMENT_ID}:{epoch_key}".encode("utf-8")
    ).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(2**64)
    return bucket < control_rate


def _provider_limit(body: dict, profile: ProviderRequestProfile) -> tuple[str | None, int | None]:
    """Return one existing provider output-limit field without inventing a new one."""
    if profile.provider == "anthropic":
        value = body.get("max_tokens")
        return ("max_tokens", value) if isinstance(value, int) and not isinstance(value, bool) else (None, None)
    if profile.provider == "openai":
        for key in ("max_output_tokens", "max_completion_tokens", "max_tokens"):
            value = body.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return key, value
        return None, None
    if profile.provider == "gemini":
        config = body.get("generationConfig")
        if isinstance(config, dict):
            value = config.get("maxOutputTokens")
            if isinstance(value, int) and not isinstance(value, bool):
                return "generationConfig.maxOutputTokens", value
    return None, None


def _set_provider_limit(body: dict, field: str, value: int) -> None:
    """Clamp one already-present provider output-limit field."""
    if field == "generationConfig.maxOutputTokens":
        config = dict(body.get("generationConfig") or {})
        config["maxOutputTokens"] = value
        body["generationConfig"] = config
    else:
        body[field] = value


def apply_output_holdout(
    root: Path,
    body: dict,
    profile: ProviderRequestProfile,
    *,
    prompt: str,
    epoch_key: str,
    enabled: bool = False,
    control_rate: float = 0.10,
    mode: str = "normal",
    calibration_file: str = ".acco.output-calibration.json",
) -> OutputHoldoutDecision:
    """Assign control/treatment and clamp only an existing output limit in treatment."""
    if not 0 < control_rate < 1:
        raise ValueError("output holdout control_rate must be between 0 and 1")
    task = classify_output_task(prompt) or "general"
    path = Path(calibration_file)
    if not path.is_absolute():
        path = root / path
    calibration = load_output_calibration(path)
    budget = adaptive_output_budget(
        prompt,
        task=task,
        mode=mode,
        calibration=calibration,
    ).max_tokens
    control = _control_arm(epoch_key, control_rate)
    arm = "control" if control else "treatment"
    field, current = _provider_limit(body, profile)
    eligible = bool(
        field is not None
        and current is not None
        and current > budget
    )
    applied = False
    shaped = current

    if enabled and arm == "treatment" and eligible:
        shaped = budget
        _set_provider_limit(body, field, shaped)
        applied = True

    decision = OutputHoldoutDecision(
        experiment=EXPERIMENT_ID,
        arm=arm,
        epoch_key=epoch_key,
        task=task,
        mode=mode,
        budget_tokens=budget,
        enabled=bool(enabled),
        eligible=eligible,
        applied=applied,
        provider_field=field,
        original_limit=current,
        shaped_limit=shaped,
    )
    if enabled:
        append_event(
            root,
            {
                "kind": "output_holdout_assignment",
                "feature": "output_shaping",
                **decision.to_dict(),
            },
        )
    return decision


def record_output_holdout_observation(
    root: Path,
    *,
    provider: str,
    model: str,
    output_tokens: int,
    decision: dict[str, Any],
) -> None:
    """Record one measured output-token observation for a randomized holdout arm."""
    if (
        decision.get("experiment") != EXPERIMENT_ID
        or decision.get("enabled") is not True
        or decision.get("eligible") is not True
    ):
        return
    tokens = int(output_tokens)
    if tokens < 0:
        return
    append_event(
        root,
        {
            "kind": "output_holdout_observation",
            "feature": "output_shaping",
            "experiment": EXPERIMENT_ID,
            "provider": str(provider or "generic").lower(),
            "model": str(model or "unknown")[:160],
            "arm": decision.get("arm"),
            "epoch_key": decision.get("epoch_key"),
            "task": decision.get("task"),
            "mode": decision.get("mode"),
            "eligible": True,
            "applied": bool(decision.get("applied")),
            "provider_field": decision.get("provider_field"),
            "original_limit": decision.get("original_limit"),
            "budget_tokens": decision.get("budget_tokens"),
            "output_tokens": tokens,
            "evidence_basis": "provider-observed randomized holdout",
        },
    )


def _epoch_means(
    events: list[dict],
) -> dict[tuple[str, str, str, str, str], dict[str, list[float]]]:
    """Aggregate repeated turns to conversation-level means before comparison."""
    by_epoch: dict[tuple[str, str, str, str, str, str], list[int]] = defaultdict(list)
    arms: dict[tuple[str, str, str, str, str, str], str] = {}
    for event in events:
        if event.get("kind") != "output_holdout_observation":
            continue
        arm = event.get("arm")
        epoch = event.get("epoch_key")
        tokens = event.get("output_tokens")
        if arm not in {"control", "treatment"} or not isinstance(epoch, str):
            continue
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
            continue
        if event.get("eligible") is not True:
            continue
        field = event.get("provider_field")
        if not isinstance(field, str) or not field:
            continue
        key = (
            str(event.get("provider") or "generic"),
            str(event.get("model") or "unknown"),
            str(event.get("task") or "general"),
            str(event.get("mode") or "normal"),
            field,
            epoch,
        )
        by_epoch[key].append(tokens)
        arms[key] = arm

    strata: dict[tuple[str, str, str, str, str], dict[str, list[float]]] = defaultdict(
        lambda: {"control": [], "treatment": []}
    )
    for key, values in by_epoch.items():
        provider, model, task, mode, field, _epoch = key
        arm = arms[key]
        strata[(provider, model, task, mode, field)][arm].append(mean(values))
    return strata


def _weighted_reduction(
    strata: dict[tuple[str, str, str, str, str], dict[str, list[float]]],
) -> tuple[float | None, int]:
    """Return matched-stratum weighted output-token reduction."""
    total_weight = 0
    weighted = 0.0
    for arms in strata.values():
        control = arms["control"]
        treatment = arms["treatment"]
        if len(control) < 3 or len(treatment) < 3:
            continue
        base = mean(control)
        if base <= 0:
            continue
        weight = min(len(control), len(treatment))
        weighted += (1.0 - mean(treatment) / base) * weight
        total_weight += weight
    return (
        weighted / total_weight if total_weight else None,
        total_weight,
    )


def output_holdout_report(root: Path, *, bootstrap_samples: int = 1000) -> dict[str, Any]:
    """Report measured conversation-level output-token reduction with a bootstrap CI."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    events = load_events(root)
    strata = _epoch_means(events)
    reduction, matched = _weighted_reduction(strata)

    rng = random.Random(0)
    bootstrap: list[float] = []
    qualified = {
        key: value
        for key, value in strata.items()
        if len(value["control"]) >= 3 and len(value["treatment"]) >= 3
    }
    if qualified:
        for _ in range(bootstrap_samples):
            sampled: dict[tuple[str, str, str, str, str], dict[str, list[float]]] = {}
            for key, arms in qualified.items():
                sampled[key] = {
                    "control": [
                        rng.choice(arms["control"]) for _ in range(len(arms["control"]))
                    ],
                    "treatment": [
                        rng.choice(arms["treatment"])
                        for _ in range(len(arms["treatment"]))
                    ],
                }
            value, _weight = _weighted_reduction(sampled)
            if value is not None:
                bootstrap.append(value)
    bootstrap.sort()
    ci = None
    if bootstrap:
        low = bootstrap[int(0.025 * (len(bootstrap) - 1))]
        high = bootstrap[int(0.975 * (len(bootstrap) - 1))]
        ci = [low, high]

    details = []
    for key, arms in sorted(strata.items()):
        provider, model, task, mode, provider_field = key
        base = mean(arms["control"]) if arms["control"] else None
        treatment = mean(arms["treatment"]) if arms["treatment"] else None
        details.append(
            {
                "provider": provider,
                "model": model,
                "task": task,
                "mode": mode,
                "provider_field": provider_field,
                "control_epochs": len(arms["control"]),
                "treatment_epochs": len(arms["treatment"]),
                "control_mean_output_tokens": base,
                "treatment_mean_output_tokens": treatment,
                "reduction": (
                    1.0 - treatment / base
                    if base and treatment is not None
                    else None
                ),
                "qualified": len(arms["control"]) >= 3 and len(arms["treatment"]) >= 3,
            }
        )
    return {
        "schema": 1,
        "experiment": EXPERIMENT_ID,
        "matched_epoch_weight": matched,
        "measured_output_token_reduction": reduction,
        "ci95": ci,
        "strata": details,
        "claim_boundary": (
            "Randomized provider-observed output-token evidence only. "
            "It does not establish response-quality or cost-per-success parity."
        ),
    }
