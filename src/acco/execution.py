"""Restricted out-of-context computation over explicit repository inputs.

The model supplies a small analysis program and repository-relative file names.
ACCO reads the large inputs locally, executes the program in an isolated Python
subprocess with a deliberately tiny builtin surface, and returns only the
JSON-serializable result. The source inputs therefore never need to enter model
context merely so the model can count, group, filter, or summarize them.

This is a defensive execution boundary, not a hardened OS container. Imports,
shell/process access, arbitrary file access, private/dunder attribute traversal,
dynamic evaluation, and environment access are excluded from the language
surface. A wall-clock timeout and hard input/result bounds remain mandatory.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from .recovery import RecoveryCapacityError, RecoveryStore

DEFAULT_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RESULT_BYTES = 64 * 1024
MAX_RESULT_BYTES = 1024 * 1024
MAX_CODE_CHARS = 16_000
MAX_FILES = 128
MAX_INPUT_BYTES = 32 * 1024 * 1024
_PREVIEW_CHARS = 12_000

_FORBIDDEN_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "memoryview",
    "open",
    "setattr",
    "vars",
}

_FORBIDDEN_NODES = (
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Nonlocal,
)

_RUNNER = r"""
import collections
import json
import re
import statistics
import sys

payload = json.loads(sys.stdin.read())
data = payload["data"]

safe_builtins = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}

scope = {
    "__builtins__": safe_builtins,
    "data": data,
    "files": data,
    "Counter": collections.Counter,
    "mean": statistics.mean,
    "median": statistics.median,
    "json_loads": json.loads,
    "json_dumps": json.dumps,
    "regex_findall": re.findall,
    "regex_search": re.search,
    "regex_sub": re.sub,
}

try:
    exec(compile(payload["code"], "<acco-execute>", "exec"), scope, scope)
    if "result" not in scope:
        raise ValueError("program must assign a JSON-serializable value to result")
    encoded = json.dumps(
        {"ok": True, "result": scope["result"]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
except BaseException as exc:
    encoded = json.dumps(
        {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
        ensure_ascii=False,
        separators=(",", ":"),
    )

sys.stdout.write(encoded)
"""


class ExecutionValidationError(ValueError):
    """Raised when a requested analysis program crosses the restricted boundary."""


@dataclass(frozen=True)
class ExecutionLimits:
    """Bound one out-of-context program invocation."""

    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES
    max_files: int = MAX_FILES
    max_input_bytes: int = MAX_INPUT_BYTES
    max_code_chars: int = MAX_CODE_CHARS

    def validate(self) -> ExecutionLimits:
        """Validate limits and return the normalized immutable value."""
        if not 1 <= int(self.timeout_seconds) <= MAX_TIMEOUT_SECONDS:
            raise ValueError(
                f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}"
            )
        if not 1024 <= int(self.max_result_bytes) <= MAX_RESULT_BYTES:
            raise ValueError(
                f"max_result_bytes must be between 1024 and {MAX_RESULT_BYTES}"
            )
        if not 1 <= int(self.max_files) <= MAX_FILES:
            raise ValueError(f"max_files must be between 1 and {MAX_FILES}")
        if not 1 <= int(self.max_input_bytes) <= MAX_INPUT_BYTES:
            raise ValueError(
                f"max_input_bytes must be between 1 and {MAX_INPUT_BYTES}"
            )
        if not 1 <= int(self.max_code_chars) <= MAX_CODE_CHARS:
            raise ValueError(
                f"max_code_chars must be between 1 and {MAX_CODE_CHARS}"
            )
        return ExecutionLimits(
            timeout_seconds=int(self.timeout_seconds),
            max_result_bytes=int(self.max_result_bytes),
            max_files=int(self.max_files),
            max_input_bytes=int(self.max_input_bytes),
            max_code_chars=int(self.max_code_chars),
        )


class _ProgramValidator(ast.NodeVisitor):
    """Reject syntax that can escape the intended data-analysis surface."""

    def visit(self, node: ast.AST) -> Any:
        """Reject forbidden node classes before ordinary recursive traversal."""
        if isinstance(node, _FORBIDDEN_NODES):
            raise ExecutionValidationError(
                f"{type(node).__name__} is not allowed in ACCO execution"
            )
        return super().visit(node)

    def visit_Name(self, node: ast.Name) -> Any:
        """Reject private and dynamically powerful names."""
        if node.id.startswith("_") or node.id in _FORBIDDEN_NAMES:
            raise ExecutionValidationError(
                f"name {node.id!r} is not allowed in ACCO execution"
            )
        return self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        """Reject private/dunder traversal on otherwise safe values."""
        if node.attr.startswith("_"):
            raise ExecutionValidationError(
                f"private attribute {node.attr!r} is not allowed in ACCO execution"
            )
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        """Allow helper functions only when their names and arguments are public."""
        if node.name.startswith("_"):
            raise ExecutionValidationError("private helper names are not allowed")
        for argument in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]:
            if argument.arg.startswith("_"):
                raise ExecutionValidationError(
                    "private helper argument names are not allowed"
                )
        if node.args.vararg and node.args.vararg.arg.startswith("_"):
            raise ExecutionValidationError(
                "private helper argument names are not allowed"
            )
        if node.args.kwarg and node.args.kwarg.arg.startswith("_"):
            raise ExecutionValidationError(
                "private helper argument names are not allowed"
            )
        return self.generic_visit(node)


def validate_program(code: str, *, max_code_chars: int = MAX_CODE_CHARS) -> None:
    """Validate one restricted Python analysis program without executing it."""
    if not isinstance(code, str) or not code.strip():
        raise ExecutionValidationError("code must be a nonempty string")
    if len(code) > max_code_chars:
        raise ExecutionValidationError(
            f"code exceeds the {max_code_chars}-character execution limit"
        )
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ExecutionValidationError(f"invalid Python: {exc.msg}") from exc
    _ProgramValidator().visit(tree)
    assigns_result = any(
        isinstance(node, ast.Name)
        and node.id == "result"
        and isinstance(node.ctx, ast.Store)
        for node in ast.walk(tree)
    )
    if not assigns_result:
        raise ExecutionValidationError(
            "program must assign a JSON-serializable value to result"
        )


def _resolve_input(root: Path, requested: str) -> tuple[str, bytes]:
    """Resolve and read one repository-contained regular file."""
    candidate = Path(requested)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ExecutionValidationError(
            f"execution input escapes repository root: {requested}"
        ) from exc
    if not resolved.is_file():
        raise ExecutionValidationError(f"execution input is not a file: {requested}")
    raw = resolved.read_bytes()
    if b"\x00" in raw:
        raise ExecutionValidationError(
            f"binary execution input is not supported: {relative.as_posix()}"
        )
    return relative.as_posix(), raw


def _load_inputs(
    root: Path,
    files: list[str] | tuple[str, ...],
    limits: ExecutionLimits,
) -> tuple[dict[str, str], int]:
    """Load bounded repository text inputs under stable relative-path keys."""
    if not isinstance(files, (list, tuple)) or not files:
        raise ExecutionValidationError("files must contain at least one path")
    if len(files) > limits.max_files:
        raise ExecutionValidationError(
            f"file count exceeds execution limit of {limits.max_files}"
        )
    loaded: dict[str, str] = {}
    total = 0
    for value in files:
        path = str(value)
        key, raw = _resolve_input(root, path)
        if key in loaded:
            continue
        total += len(raw)
        if total > limits.max_input_bytes:
            raise ExecutionValidationError(
                f"execution inputs exceed {limits.max_input_bytes} bytes"
            )
        loaded[key] = raw.decode("utf-8", errors="replace")
    return loaded, total


def _subprocess_environment() -> dict[str, str]:
    """Return the minimal environment required for cross-platform Python startup."""
    import os

    env: dict[str, str] = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0",
    }
    for name in ("SYSTEMROOT", "WINDIR"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env


def _preview(serialized: str) -> str:
    """Return a bounded head/tail preview of an oversized exact result."""
    if len(serialized) <= _PREVIEW_CHARS:
        return serialized
    half = _PREVIEW_CHARS // 2
    omitted = len(serialized) - (half * 2)
    return (
        serialized[:half]
        + f"\n... [ACCO omitted {omitted} result characters; recover exact result] ...\n"
        + serialized[-half:]
    )


def execute_program(
    root: str | Path,
    code: str,
    files: list[str] | tuple[str, ...],
    *,
    recovery: RecoveryStore | None = None,
    limits: ExecutionLimits | None = None,
) -> dict[str, Any]:
    """Execute restricted Python over explicit repository files outside model context."""
    repository = Path(root).expanduser().resolve()
    if not repository.is_dir():
        raise ValueError(f"execution root must be an existing directory: {repository}")
    normalized_limits = (limits or ExecutionLimits()).validate()
    validate_program(code, max_code_chars=normalized_limits.max_code_chars)
    data, input_bytes = _load_inputs(repository, files, normalized_limits)
    payload = json.dumps(
        {"code": code, "data": data},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    started = time.monotonic()
    try:
        process = subprocess.run(
            [sys.executable, "-I", "-S", "-c", _RUNNER],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=normalized_limits.timeout_seconds,
            cwd=str(repository),
            env=_subprocess_environment(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"ACCO execution timed out after {normalized_limits.timeout_seconds}s"
        ) from exc
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if process.returncode != 0:
        detail = (process.stderr or "").strip()[-1000:]
        raise RuntimeError(
            "ACCO execution subprocess failed"
            + (f": {detail}" if detail else "")
        )
    try:
        response = json.loads(process.stdout)
    except ValueError as exc:
        raise RuntimeError("ACCO execution returned invalid runner output") from exc
    if not isinstance(response, dict) or not response.get("ok"):
        error = response.get("error") if isinstance(response, dict) else None
        raise RuntimeError(str(error or "ACCO execution failed"))
    result = response.get("result")
    serialized = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result_bytes = len(serialized.encode("utf-8"))
    common = {
        "schema": 1,
        "language": "restricted-python",
        "files": list(data),
        "input_bytes": input_bytes,
        "result_bytes": result_bytes,
        "elapsed_ms": elapsed_ms,
        "timeout_seconds": normalized_limits.timeout_seconds,
        "out_of_context": True,
    }
    if result_bytes <= normalized_limits.max_result_bytes:
        return {
            **common,
            "truncated": False,
            "result": result,
            "recovery_handle": None,
        }
    store = recovery or RecoveryStore(repository)
    try:
        handle = store.put(
            serialized.encode("utf-8"),
            content_type="application/json",
            metadata={
                "transform": "out-of-context-execution-result",
                "language": "restricted-python",
                "files": list(data),
                "result_bytes": result_bytes,
            },
        )
    except RecoveryCapacityError:
        raise RecoveryCapacityError(
            "execution result exceeds the response limit and exact recovery "
            "capacity is unavailable; no lossy result was returned"
        ) from None
    return {
        **common,
        "truncated": True,
        "result": None,
        "preview": _preview(serialized),
        "recovery_handle": handle,
    }
