"""Stable in-process SDK for embedding ACCO in custom Python agents."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

from .browser_context import compress_browser_payload
from .context_budget import plan_context_budget as build_context_budget
from .context_router import route_context
from .domain_middleware import (
    optimize_api_payload,
    optimize_database_rows,
    optimize_rag_context,
)
from .estimate import estimate_tokens
from .efficiency.ledger import recent_ledger_events, search_ledger
from .execution import ExecutionLimits, batch_execute, execute_file, execute_program
from .cache_ttl import cache_ttl_report
from .model_routing import route_task
from .observability import (
    observability_report,
    prometheus_metrics,
    record_framework_operation,
)
from .output_holdout import output_holdout_report
from .output import OutputPolicy, OutputPipeline
from .provider_transform import transform_provider_request
from .recovery import DEFAULT_CAPACITY_BYTES, RecoveryCapacityError, RecoveryStore
from .tool_field_learning import field_learning_report, record_field_retrieval


@dataclass(frozen=True)
class AccoSdkConfig:
    """Configure one in-process ACCO SDK engine."""

    root: Path
    recovery_capacity_bytes: int = DEFAULT_CAPACITY_BYTES

    def validate(self) -> AccoSdkConfig:
        """Validate and normalize the SDK configuration."""
        root = Path(self.root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"SDK root must be an existing directory: {root}")
        if self.recovery_capacity_bytes <= 0:
            raise ValueError("recovery_capacity_bytes must be positive")
        return AccoSdkConfig(
            root=root,
            recovery_capacity_bytes=int(self.recovery_capacity_bytes),
        )


class AccoEngine:
    """Expose ACCO optimization primitives to framework-neutral Python agents."""

    def __init__(
        self,
        root: str | Path = ".",
        *,
        recovery_capacity_bytes: int = DEFAULT_CAPACITY_BYTES,
    ):
        """Create one project-scoped engine with shared exact-recovery storage."""
        config = AccoSdkConfig(
            Path(root),
            recovery_capacity_bytes=recovery_capacity_bytes,
        ).validate()
        self.root = config.root
        self.recovery_capacity_bytes = config.recovery_capacity_bytes
        self.recovery = RecoveryStore(
            self.root,
            capacity_bytes=self.recovery_capacity_bytes,
        )
        self.output_pipeline = OutputPipeline()

    def _observe_framework(
        self,
        framework: str,
        operation: str,
        result: dict[str, Any],
        started: float,
    ) -> None:
        """Record content-free SDK/framework operation metrics."""
        before = result.get("original_tokens")
        after = result.get("output_tokens")
        if not isinstance(before, int) or isinstance(before, bool):
            return
        if not isinstance(after, int) or isinstance(after, bool):
            return
        try:
            record_framework_operation(
                self.root,
                framework=framework,
                operation=operation,
                original_tokens=before,
                output_tokens=after,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                changed=bool(result.get("changed")),
                success=True,
            )
        except OSError:
            pass

    def optimize_provider_request(
        self,
        provider: str,
        body: dict,
        *,
        request_path: str = "",
        compress_schemas: bool = True,
        compress_tool_results: bool = True,
        tool_result_min_tokens: int = 800,
        prefix_tracking: bool = True,
        context_budget_total_tokens: int | None = None,
        provider_cache_mode: str = "plan",
        provider_cache_expected_reuses: int = 2,
        output_holdout_enabled: bool = False,
        output_holdout_control_rate: float = 0.10,
        output_holdout_mode: str = "normal",
        output_holdout_calibration_file: str = ".acco.output-calibration.json",
        framework: str = "sdk",
    ) -> dict[str, Any]:
        """Optimize one provider request while keeping exact recovery available."""
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("provider must be a nonempty string")
        started = time.perf_counter()
        result = transform_provider_request(
            self.root,
            provider.strip(),
            body,
            request_path=request_path,
            compress_schemas=compress_schemas,
            compress_tool_results=compress_tool_results,
            tool_result_min_tokens=tool_result_min_tokens,
            recovery_capacity_bytes=self.recovery_capacity_bytes,
            prefix_tracking=prefix_tracking,
            context_budget_total_tokens=context_budget_total_tokens,
            provider_cache_mode=provider_cache_mode,
            provider_cache_expected_reuses=provider_cache_expected_reuses,
            output_holdout_enabled=output_holdout_enabled,
            output_holdout_control_rate=output_holdout_control_rate,
            output_holdout_mode=output_holdout_mode,
            output_holdout_calibration_file=output_holdout_calibration_file,
        )
        payload = {
            "schema": 1,
            "body": result.body,
            "metadata": result.metadata(),
            "original_tokens": result.original_tokens,
            "output_tokens": result.output_tokens,
            "changed": result.changed,
        }
        self._observe_framework(framework, "provider.optimize", payload, started)
        return payload

    def optimize_context(
        self,
        text: str,
        *,
        query: str = "",
        command: str = "",
        max_lines: int = 120,
        min_reduction: float = 0.08,
        tool_key: str = "sdk-context",
        framework: str = "sdk",
    ) -> dict[str, Any]:
        """Compress arbitrary agent/tool context with exact-source recovery."""
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        started = time.perf_counter()
        result = route_context(
            text,
            query=query,
            recovery=self.recovery,
            command=command,
            max_lines=max_lines,
            min_reduction=min_reduction,
            tool_key=tool_key,
        )
        payload = {"schema": 1, **result.to_dict()}
        self._observe_framework(framework, "context.optimize", payload, started)
        return payload

    def optimize_browser_context(
        self,
        text: str,
        *,
        query: str = "",
        max_lines: int = 120,
        min_tokens: int = 400,
        format_hint: str = "auto",
        framework: str = "sdk",
    ) -> dict[str, Any]:
        """Optimize caller-supplied browser/DOM/AX context with exact recovery."""
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        started = time.perf_counter()
        result = compress_browser_payload(
            text,
            query=query,
            max_lines=max_lines,
            min_tokens=min_tokens,
            format_hint=format_hint,
            recovery=self.recovery,
        )
        payload = {"schema": 1, **result.to_dict()}
        self._observe_framework(framework, "browser.optimize", payload, started)
        return payload

    def optimize_output(
        self,
        text: str,
        *,
        command: str = "",
        exit_code: int | None = None,
        max_lines: int = 80,
        keep_tail: int = 20,
        min_reduction: float = 0.02,
        recoverable: bool = True,
        framework: str = "sdk",
    ) -> dict[str, Any]:
        """Optimize command output and optionally persist the exact original."""
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        if max_lines <= 0:
            raise ValueError("max_lines must be positive")
        if keep_tail < 0:
            raise ValueError("keep_tail must be nonnegative")
        if not 0 <= min_reduction < 1:
            raise ValueError("min_reduction must be in [0, 1)")
        started = time.perf_counter()
        result = self.output_pipeline.process(
            text,
            command,
            exit_code=exit_code,
            policy=OutputPolicy(
                max_lines=max_lines,
                keep_tail=keep_tail,
                min_reduction=min_reduction,
            ),
        )
        original_tokens = estimate_tokens(text)
        candidate = result.text
        recovery_handle = None
        if result.requires_recovery and not recoverable:
            candidate = text
        elif result.compressed and recoverable:
            try:
                recovery_handle = self.recovery.put(
                    text,
                    content_type="text/plain",
                    metadata={
                        "transform": "sdk-output",
                        "processor": result.processor,
                        "content_kind": result.content_kind,
                        "safety_class": result.safety_class.name,
                    },
                )
            except RecoveryCapacityError:
                candidate = text
                recovery_handle = None
        changed = candidate != text
        output_tokens = estimate_tokens(candidate)
        payload = {
            "schema": 1,
            "text": candidate,
            "processor": result.processor,
            "content_kind": result.content_kind,
            "safety_class": result.safety_class.name,
            "validation": result.validation,
            "requires_recovery": result.safety_class.requires_recovery,
            "changed": changed,
            "compressed": changed,
            "failed": result.failed,
            "recovered_lines": list(result.recovered_lines) if changed else [],
            "original_tokens": original_tokens,
            "output_tokens": output_tokens if changed else original_tokens,
            "recovery_handle": recovery_handle,
        }
        self._observe_framework(framework, "output.optimize", payload, started)
        return payload

    def plan_context_budget(
        self,
        prompt: str,
        *,
        total_tokens: int,
        task: str | None = None,
        observed_tokens: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Plan one total model-context envelope for a custom agent."""
        return build_context_budget(
            prompt,
            total_tokens=total_tokens,
            task=task,
            observed_tokens=observed_tokens,
        ).to_dict()

    def route_model(
        self,
        prompt: str,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        current_model: str | None = None,
        allowed_models: list[str] | tuple[str, ...] | None = None,
        min_savings: float = 0.05,
        conservative: bool = True,
        task_override: str | None = None,
        calibration: dict | None = None,
    ) -> dict[str, Any]:
        """Return ACCO's deterministic model-routing decision as JSON-safe data."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a nonempty string")
        return route_task(
            prompt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            current_model=current_model,
            allowed_models=allowed_models,
            min_savings=min_savings,
            conservative=conservative,
            task_override=task_override,
            calibration=calibration,
        ).to_dict()

    def optimize_rag(
        self,
        documents: list[Any],
        *,
        query: str = "",
        max_documents: int = 8,
        min_reduction: float = 0.08,
        framework: str = "sdk",
    ) -> dict[str, Any]:
        """Compress caller-supplied RAG documents for model context."""
        started = time.perf_counter()
        result = optimize_rag_context(
            documents,
            query=query,
            recovery=self.recovery,
            max_documents=max_documents,
            min_reduction=min_reduction,
        )
        self._observe_framework(framework, "middleware.rag", result, started)
        return result

    def optimize_api_payload(
        self,
        payload: Any,
        *,
        query: str = "",
        min_reduction: float = 0.08,
        framework: str = "sdk",
    ) -> dict[str, Any]:
        """Compress caller-supplied JSON API data for model context."""
        started = time.perf_counter()
        result = optimize_api_payload(
            payload,
            query=query,
            recovery=self.recovery,
            min_reduction=min_reduction,
        )
        self._observe_framework(framework, "middleware.api", result, started)
        return result

    def optimize_database_rows(
        self,
        rows: list[Any],
        *,
        query: str = "",
        columns: list[str] | None = None,
        max_rows: int = 20,
        min_reduction: float = 0.08,
        framework: str = "sdk",
    ) -> dict[str, Any]:
        """Compress caller-supplied query results without opening a database."""
        started = time.perf_counter()
        result = optimize_database_rows(
            rows,
            query=query,
            recovery=self.recovery,
            columns=columns,
            max_rows=max_rows,
            min_reduction=min_reduction,
        )
        self._observe_framework(framework, "middleware.database", result, started)
        return result

    def execute(
        self,
        code: str,
        files: list[str] | tuple[str, ...],
        *,
        timeout_seconds: int = 5,
        max_result_bytes: int = 64 * 1024,
    ) -> dict[str, Any]:
        """Run restricted analysis over repository files outside model context."""
        return execute_program(
            self.root,
            code,
            files,
            recovery=self.recovery,
            limits=ExecutionLimits(
                timeout_seconds=timeout_seconds,
                max_result_bytes=max_result_bytes,
            ),
        )

    def execute_file(
        self,
        program_file: str,
        files: list[str] | tuple[str, ...],
        *,
        timeout_seconds: int = 5,
        max_result_bytes: int = 64 * 1024,
    ) -> dict[str, Any]:
        """Run one repository-contained restricted analysis program."""
        return execute_file(
            self.root,
            program_file,
            files,
            recovery=self.recovery,
            limits=ExecutionLimits(
                timeout_seconds=timeout_seconds,
                max_result_bytes=max_result_bytes,
            ),
        )

    def batch_execute(
        self,
        jobs: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        *,
        timeout_seconds: int = 5,
        max_result_bytes: int = 64 * 1024,
    ) -> dict[str, Any]:
        """Run a bounded batch of out-of-context analysis jobs."""
        return batch_execute(
            self.root,
            jobs,
            recovery=self.recovery,
            limits=ExecutionLimits(
                timeout_seconds=timeout_seconds,
                max_result_bytes=max_result_bytes,
            ),
        )

    def session_search(
        self,
        query: str,
        *,
        kinds: list[str] | tuple[str, ...] | None = None,
        session: str | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        """Search redacted structured session history."""
        return search_ledger(
            self.root,
            query,
            kinds=kinds,
            session=session,
            limit=limit,
        )

    def session_recent(
        self,
        *,
        kinds: list[str] | tuple[str, ...] | None = None,
        session: str | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        """Return recent redacted structured session events."""
        events = recent_ledger_events(
            self.root,
            kinds=kinds,
            session=session,
            limit=limit,
        )
        return {"schema": 1, "count": len(events), "events": events}

    def recover(
        self,
        handle: str,
        *,
        pointer: str | None = None,
    ) -> dict[str, Any]:
        """Recover exact bytes or one typed-object JSON-Pointer subtree."""
        if handle.startswith("tsr_obj_") or handle.startswith("tsr://"):
            selected = self.recovery.select(handle, pointer)
            metadata = selected.get("metadata")
            tool_key = metadata.get("tool_key") if isinstance(metadata, dict) else None
            selected_pointer = selected.get("pointer")
            if isinstance(tool_key, str) and isinstance(selected_pointer, str):
                record_field_retrieval(self.root, tool_key, selected_pointer)
            return {
                "schema": 1,
                "kind": "object",
                **selected,
            }
        record = self.recovery.get(handle)
        try:
            text = record.payload.decode("utf-8")
            payload = text
            encoding = "utf-8"
        except UnicodeDecodeError:
            payload = base64.b64encode(record.payload).decode("ascii")
            encoding = "base64"
        return {
            "schema": 1,
            "kind": "bytes",
            "handle": record.handle,
            "content_type": record.content_type,
            "encoding": encoding,
            "payload": payload,
            "size_bytes": record.size_bytes,
            "metadata": record.metadata,
            "created_at": record.created_at,
            "last_accessed_at": record.last_accessed_at,
            "access_count": record.access_count,
        }

    def tool_field_learning(self, *, limit: int = 50) -> dict[str, Any]:
        """Report local learned structured-field importance without field values."""
        return field_learning_report(self.root, limit=limit)

    def cache_ttl_learning(self) -> dict[str, Any]:
        """Report provider-observed cache TTL bounds and qualified estimates."""
        return cache_ttl_report(self.root)

    def output_holdout(self, *, bootstrap_samples: int = 1000) -> dict[str, Any]:
        """Report measured provider output-token holdout evidence."""
        return output_holdout_report(
            self.root,
            bootstrap_samples=bootstrap_samples,
        )

    def observability(self, *, days: int = 7) -> dict[str, Any]:
        """Return provider/framework operational metrics for this project."""
        return observability_report(self.root, days=days)

    def prometheus(self, *, days: int = 7) -> str:
        """Return Prometheus text exposition for local ACCO runtime metrics."""
        return prometheus_metrics(self.root, days=days)

    def middleware(self, provider: str) -> AccoMiddleware:
        """Create a provider-bound middleware facade for a custom agent."""
        return AccoMiddleware(self, provider=provider)

    def rag(self) -> AccoRagMiddleware:
        """Create optional RAG-context middleware."""
        return AccoRagMiddleware(self)

    def api(self) -> AccoApiMiddleware:
        """Create optional JSON API-payload middleware."""
        return AccoApiMiddleware(self)

    def database(self) -> AccoDatabaseMiddleware:
        """Create optional database-result middleware."""
        return AccoDatabaseMiddleware(self)


class AccoMiddleware:
    """Framework-neutral before-request/after-tool middleware facade."""

    def __init__(self, engine: AccoEngine, *, provider: str):
        """Bind middleware calls to one provider identity."""
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("provider must be a nonempty string")
        self.engine = engine
        self.provider = provider.strip()

    def before_request(self, body: dict, **options: Any) -> dict[str, Any]:
        """Optimize one provider-bound model request before it is sent."""
        return self.engine.optimize_provider_request(
            self.provider,
            body,
            **options,
        )

    def after_tool_result(
        self,
        text: str,
        *,
        query: str = "",
        command: str = "",
        max_lines: int = 120,
        min_reduction: float = 0.08,
    ) -> dict[str, Any]:
        """Optimize one tool result before adding it back to agent context."""
        return self.engine.optimize_context(
            text,
            query=query,
            command=command,
            max_lines=max_lines,
            min_reduction=min_reduction,
        )

    def after_browser_result(
        self,
        text: str,
        *,
        query: str = "",
        max_lines: int = 120,
        min_tokens: int = 400,
        format_hint: str = "auto",
    ) -> dict[str, Any]:
        """Optimize browser/DOM/AX tool context before the next model call."""
        return self.engine.optimize_browser_context(
            text,
            query=query,
            max_lines=max_lines,
            min_tokens=min_tokens,
            format_hint=format_hint,
        )

    def route(self, prompt: str, **options: Any) -> dict[str, Any]:
        """Return a model route decision for an orchestrator-controlled turn."""
        return self.engine.route_model(prompt, **options)

    def recover(self, handle: str) -> dict[str, Any]:
        """Recover exact source bytes for a prior middleware transform."""
        return self.engine.recover(handle)



class AccoRagMiddleware:
    """Optional adapter for already-retrieved RAG documents."""

    def __init__(self, engine: AccoEngine):
        """Bind the adapter to one project-scoped recovery store."""
        self.engine = engine

    def optimize(
        self,
        documents: list[Any],
        *,
        query: str = "",
        max_documents: int = 8,
        min_reduction: float = 0.08,
    ) -> dict[str, Any]:
        """Compress documents without performing retrieval or embedding calls."""
        return self.engine.optimize_rag(
            documents,
            query=query,
            max_documents=max_documents,
            min_reduction=min_reduction,
        )

    def recover(self, handle: str) -> dict[str, Any]:
        """Recover the exact canonical JSON submitted to the adapter."""
        return self.engine.recover(handle)


class AccoApiMiddleware:
    """Optional adapter for caller-supplied JSON API payloads."""

    def __init__(self, engine: AccoEngine):
        """Bind the adapter to one project-scoped recovery store."""
        self.engine = engine

    def optimize(
        self,
        payload: Any,
        *,
        query: str = "",
        min_reduction: float = 0.08,
    ) -> dict[str, Any]:
        """Compress JSON data for LLM context without making network requests."""
        return self.engine.optimize_api_payload(
            payload,
            query=query,
            min_reduction=min_reduction,
        )

    def recover(self, handle: str) -> dict[str, Any]:
        """Recover the exact canonical JSON submitted to the adapter."""
        return self.engine.recover(handle)


class AccoDatabaseMiddleware:
    """Optional adapter for caller-supplied database/query result rows."""

    def __init__(self, engine: AccoEngine):
        """Bind the adapter to one project-scoped recovery store."""
        self.engine = engine

    def optimize(
        self,
        rows: list[Any],
        *,
        query: str = "",
        columns: list[str] | None = None,
        max_rows: int = 20,
        min_reduction: float = 0.08,
    ) -> dict[str, Any]:
        """Compress rows without opening a database connection or running SQL."""
        return self.engine.optimize_database_rows(
            rows,
            query=query,
            columns=columns,
            max_rows=max_rows,
            min_reduction=min_reduction,
        )

    def recover(self, handle: str) -> dict[str, Any]:
        """Recover the exact canonical JSON submitted to the adapter."""
        return self.engine.recover(handle)
