"""Stable-prefix accounting for provider requests and cache-aware transforms."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .estimate import estimate_tokens
from .state import load, update

_PREFIX_ELEMENT_LIMIT = 512


@dataclass(frozen=True)
class PrefixPlan:
    """Describe the stable provider-request prefix without mutating the request."""

    fingerprint: str
    stable_tokens: int
    stable_bytes: int
    components: tuple[str, ...]
    previous_fingerprint: str | None
    reused: bool
    reuse_mode: str = "miss"
    element_count: int = 0
    epoch_key: str = "default"

    def to_dict(self) -> dict:
        """Return JSON-safe prefix metadata."""
        return {
            "fingerprint": self.fingerprint,
            "stable_tokens": self.stable_tokens,
            "stable_bytes": self.stable_bytes,
            "components": list(self.components),
            "previous_fingerprint": self.previous_fingerprint,
            "reused": self.reused,
            "reuse_mode": self.reuse_mode,
            "element_count": self.element_count,
            "epoch_key": self.epoch_key,
        }


def _stable_payload(body: dict) -> tuple[dict, tuple[str, ...]]:
    """Extract request fields expected to remain stable across neighboring turns."""
    stable: dict = {}
    components: list[str] = []
    for key in ("system", "instructions", "tools", "tool_choice"):
        if key in body:
            stable[key] = body[key]
            components.append(key)

    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        prefix = list(messages)
        if isinstance(prefix[-1], dict) and prefix[-1].get("role") == "user":
            prefix = prefix[:-1]
        if prefix:
            stable["messages"] = prefix
            components.append("messages[:-latest-user]")

    input_items = body.get("input")
    if isinstance(input_items, list) and input_items:
        prefix = list(input_items)
        if isinstance(prefix[-1], dict) and prefix[-1].get("role") == "user":
            prefix = prefix[:-1]
        if prefix:
            stable["input"] = prefix
            components.append("input[:-latest-user]")
    return stable, tuple(components)


def _element_digest(value: object) -> str:
    """Hash one stable prefix element without persisting request content."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def stable_prefix_element_hashes(body: dict) -> tuple[str, ...]:
    """Return bounded content-free hashes for append-only prefix detection."""
    hashes: list[str] = []
    for key in ("system", "instructions", "tools", "tool_choice"):
        if key in body:
            hashes.append(f"{key}:{_element_digest(body[key])}")

    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        prefix = list(messages)
        if isinstance(prefix[-1], dict) and prefix[-1].get("role") == "user":
            prefix = prefix[:-1]
        hashes.extend(
            f"message:{_element_digest(item)}" for item in prefix
        )

    input_items = body.get("input")
    if isinstance(input_items, list) and input_items:
        prefix = list(input_items)
        if isinstance(prefix[-1], dict) and prefix[-1].get("role") == "user":
            prefix = prefix[:-1]
        hashes.extend(
            f"input:{_element_digest(item)}" for item in prefix
        )
    return tuple(hashes)


def conversation_epoch_key(body: dict) -> str:
    """Return a content-free key separating concurrent/subagent cache prefixes."""
    anchor: dict = {}
    for key in ("system", "instructions", "tools", "tool_choice"):
        if key in body:
            anchor[key] = body[key]
    encoded = json.dumps(
        anchor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:20]


def _epoch_state(data: dict, provider: str, epoch_key: str) -> dict | None:
    """Return one provider/conversation prefix epoch when present."""
    providers = data.get("prefix_cache_epochs", {})
    if not isinstance(providers, dict):
        return None
    provider_state = providers.get(provider, {})
    if not isinstance(provider_state, dict):
        return None
    epochs = provider_state.get("epochs", {})
    if not isinstance(epochs, dict):
        return None
    value = epochs.get(epoch_key)
    return value if isinstance(value, dict) else None


def reusable_history_counts(
    root: Path,
    provider: str,
    body: dict,
    *,
    epoch_key: str | None = None,
) -> tuple[int, int]:
    """Return message/input elements already present in the prior stable prefix.

    The state contains hashes only. A count is returned only for the exact
    leading sequence previously observed, so callers can leave that cache-hot
    history byte-identical and optimize only the live frontier.
    """
    key = provider.strip().lower() or "generic"
    data = load(root)
    epoch = epoch_key or conversation_epoch_key(body)
    previous = _epoch_state(data, key, epoch)
    if previous is None:
        previous = data.get("prefix_cache", {}).get(key)
    if not isinstance(previous, dict):
        return 0, 0
    previous_hashes = previous.get("source_element_hashes")
    if not isinstance(previous_hashes, list):
        previous_hashes = previous.get("element_hashes")
    if not isinstance(previous_hashes, list):
        return 0, 0
    current = stable_prefix_element_hashes(body)
    matched = 0
    for old, new in zip(previous_hashes, current):
        if str(old) != new:
            break
        matched += 1
    if matched == 0:
        return 0, 0
    prefix = tuple(str(item) for item in previous_hashes[:matched])
    return (
        sum(item.startswith("message:") for item in prefix),
        sum(item.startswith("input:") for item in prefix),
    )


def stable_prefix_fingerprint(body: dict) -> tuple[str, int, int, tuple[str, ...]]:
    """Hash a canonical representation of the stable request prefix."""
    stable, components = _stable_payload(body)
    encoded = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    return digest, estimate_tokens(encoded.decode(errors="replace")), len(encoded), components


def observe_prefix(
    root: Path,
    provider: str,
    body: dict,
    *,
    source_body: dict | None = None,
    epoch_key: str | None = None,
) -> PrefixPlan:
    """Record provider-visible prefix reuse plus the source-prefix fingerprint."""
    fingerprint, tokens, size, components = stable_prefix_fingerprint(body)
    key = provider.strip().lower() or "generic"
    data = load(root)
    epoch = epoch_key or conversation_epoch_key(
        source_body if isinstance(source_body, dict) else body
    )
    previous = _epoch_state(data, key, epoch)
    if previous is None:
        previous = data.get("prefix_cache", {}).get(key)
    previous_fingerprint = (
        str(previous.get("fingerprint"))
        if isinstance(previous, dict) and previous.get("fingerprint")
        else None
    )
    element_hashes = stable_prefix_element_hashes(body)
    source_element_hashes = stable_prefix_element_hashes(
        source_body if isinstance(source_body, dict) else body
    )
    previous_hashes = (
        tuple(str(item) for item in previous.get("element_hashes", []))
        if isinstance(previous, dict)
        and isinstance(previous.get("element_hashes"), list)
        else ()
    )
    previous_count = (
        int(previous.get("element_count", 0) or 0)
        if isinstance(previous, dict)
        else 0
    )
    exact = previous_fingerprint == fingerprint and previous_fingerprint is not None
    extended = (
        not exact
        and previous_count > 0
        and previous_count == len(previous_hashes)
        and len(element_hashes) >= previous_count
        and tuple(element_hashes[:previous_count]) == previous_hashes
    )
    reused = exact or extended
    reuse_mode = "exact" if exact else "extended" if extended else "miss"

    def mutate(data: dict) -> None:
        cache = data.setdefault("prefix_cache", {})
        current = cache.get(key)
        if not isinstance(current, dict):
            current = {
                "hits": 0,
                "misses": 0,
                "exact_hits": 0,
                "extension_hits": 0,
            }
        if previous_fingerprint is not None:
            bucket = "hits" if reused else "misses"
            current[bucket] = int(current.get(bucket, 0) or 0) + 1
            if exact:
                current["exact_hits"] = int(current.get("exact_hits", 0) or 0) + 1
            elif extended:
                current["extension_hits"] = int(
                    current.get("extension_hits", 0) or 0
                ) + 1
        current.update(
            fingerprint=fingerprint,
            stable_tokens=tokens,
            stable_bytes=size,
            components=list(components),
            element_count=len(element_hashes),
            element_hashes=list(element_hashes[:_PREFIX_ELEMENT_LIMIT]),
            source_element_hashes=list(
                source_element_hashes[:_PREFIX_ELEMENT_LIMIT]
            ),
        )
        cache[key] = current

        epoch_cache = data.setdefault("prefix_cache_epochs", {})
        provider_state = epoch_cache.get(key)
        if not isinstance(provider_state, dict):
            provider_state = {"epochs": {}}
        epochs = provider_state.get("epochs")
        if not isinstance(epochs, dict):
            epochs = {}
        epochs[epoch] = {
            **current,
            "epoch_key": epoch,
        }
        # Bound conversation/subagent anchors; most recently touched epoch wins.
        if len(epochs) > 16:
            for old_key in list(epochs)[:-16]:
                epochs.pop(old_key, None)
        provider_state["epochs"] = epochs
        epoch_cache[key] = provider_state

    update(root, mutate)
    return PrefixPlan(
        fingerprint=fingerprint,
        stable_tokens=tokens,
        stable_bytes=size,
        components=components,
        previous_fingerprint=previous_fingerprint,
        reused=reused,
        reuse_mode=reuse_mode,
        element_count=len(element_hashes),
        epoch_key=epoch,
    )


def prefix_status(root: Path) -> dict:
    """Return prefix reuse counters without exposing request content."""
    raw = load(root).get("prefix_cache", {})
    if not isinstance(raw, dict):
        raw = {}
    providers: dict[str, dict] = {}
    for provider, value in sorted(raw.items()):
        if not isinstance(value, dict):
            continue
        hits = int(value.get("hits", 0) or 0)
        misses = int(value.get("misses", 0) or 0)
        attempts = hits + misses
        providers[str(provider)] = {
            "hits": hits,
            "misses": misses,
            "exact_hits": int(value.get("exact_hits", 0) or 0),
            "extension_hits": int(value.get("extension_hits", 0) or 0),
            "reuse_rate": hits / attempts if attempts else None,
            "stable_tokens": int(value.get("stable_tokens", 0) or 0),
            "stable_bytes": int(value.get("stable_bytes", 0) or 0),
            "components": list(value.get("components", [])),
            "fingerprint": value.get("fingerprint"),
        }
    data = load(root)
    epoch_state = data.get("prefix_cache_epochs", {})
    epoch_counts: dict[str, int] = {}
    if isinstance(epoch_state, dict):
        for provider, value in epoch_state.items():
            if not isinstance(value, dict):
                continue
            epochs = value.get("epochs", {})
            if isinstance(epochs, dict):
                epoch_counts[str(provider)] = len(epochs)
    return {"providers": providers, "epoch_counts": epoch_counts}
