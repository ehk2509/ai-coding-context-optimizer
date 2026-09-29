"""Content classification and invariant gates for output compression."""

from __future__ import annotations

from dataclasses import dataclass
import ast
import csv
from io import StringIO
import json
import re
from typing import Any

from .contracts import SafetyClass

_LOG = re.compile(
    r"(?im)^(?:\[[^\]]+\]\s*)?"
    r"(?:\d{4}-\d{2}-\d{2}(?:[T ][^\s]+)?\s+)?"
    r"(?:TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\b"
)
_DIAGNOSTIC = re.compile(
    r"(?i)\b(?:error|failed|failure|traceback|assertionerror|exception|panic)\b"
)
_DIFF = re.compile(r"(?m)^diff --git .+\n")
_SEARCH = re.compile(r"(?m)^(?:[^:\n]+:\d+(?::\d+)?:|https?://\S+)")
_YAML = re.compile(r"(?m)^[A-Za-z0-9_.-]+\s*:\s*\S")
_INI = re.compile(r"(?m)^\[[^\]]+\]\s*$")
_SOURCE = re.compile(
    r"(?m)^\s*(?:def |class |async def |function |interface |type |enum |"
    r"func |fn |public |private |protected |export |import |from |package )"
)
_MARKDOWN_TABLE = re.compile(r"(?m)^\s*\|?.+\|.+\|?\s*$")
_HTML = re.compile(r"(?i)<(?:html|body|div|table|form|button|a|input|main|section)\b")


@dataclass(frozen=True)
class ContentProfile:
    """Describe detected payload shape and the default safety contract."""

    kind: str
    confidence: float
    safety_class: SafetyClass

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible content metadata."""
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "safety_class": self.safety_class.name,
            "requires_recovery": self.safety_class.requires_recovery,
        }


def detect_content(text: str) -> ContentProfile:
    """Classify model-visible text without relying on its producing command."""
    stripped = text.lstrip()
    if not stripped:
        return ContentProfile("empty", 1.0, SafetyClass.S0_EXACT)

    if stripped[:1] in "[{":
        try:
            json.loads(stripped)
            return ContentProfile("json", 1.0, SafetyClass.S4_LOSSY_RECOVERABLE)
        except (ValueError, TypeError):
            pass

    if _DIFF.search(text) and "@@" in text:
        return ContentProfile("diff", 1.0, SafetyClass.S4_LOSSY_RECOVERABLE)
    if _HTML.search(text):
        return ContentProfile("html", 0.95, SafetyClass.S4_LOSSY_RECOVERABLE)

    lines = [line for line in text.splitlines() if line.strip()]
    if lines:
        tableish = sum(line.count("|") >= 2 for line in lines[:100])
        if len(lines) >= 4 and tableish >= max(3, int(len(lines[:100]) * 0.7)):
            return ContentProfile(
                "markdown-table", 0.9, SafetyClass.S4_LOSSY_RECOVERABLE
            )

        first = lines[0]
        for delimiter in (",", "\t", ";"):
            if delimiter not in first:
                continue
            try:
                rows = list(csv.reader(StringIO("\n".join(lines[:80])), delimiter=delimiter))
            except csv.Error:
                continue
            widths = [len(row) for row in rows if row]
            if len(widths) >= 4 and min(widths) >= 2 and max(widths) == min(widths):
                return ContentProfile(
                    "delimited-table", 0.9, SafetyClass.S4_LOSSY_RECOVERABLE
                )

    if _LOG.search(text):
        return ContentProfile("log", 0.9, SafetyClass.S4_LOSSY_RECOVERABLE)
    if lines and sum(bool(_SEARCH.search(line)) for line in lines[:40]) >= 3:
        return ContentProfile(
            "search-results", 0.85, SafetyClass.S4_LOSSY_RECOVERABLE
        )
    source_lines = sum(bool(_SOURCE.match(line)) for line in lines[:160])
    if source_lines:
        try:
            ast.parse(text)
        except SyntaxError:
            if source_lines >= 3 and not _DIAGNOSTIC.search(text):
                return ContentProfile(
                    "source", 0.7, SafetyClass.S4_LOSSY_RECOVERABLE
                )
        else:
            return ContentProfile(
                "source", 0.95, SafetyClass.S4_LOSSY_RECOVERABLE
            )
    if _INI.search(text) or _YAML.search(text):
        return ContentProfile("configuration", 0.7, SafetyClass.S4_LOSSY_RECOVERABLE)
    return ContentProfile("text", 0.5, SafetyClass.S4_LOSSY_RECOVERABLE)


def _changed_diff_lines(text: str) -> set[str]:
    """Return exact changed lines that a diff compressor must preserve."""
    return {
        line
        for line in text.splitlines()
        if (
            (line.startswith("+") and not line.startswith("+++"))
            or (line.startswith("-") and not line.startswith("---"))
            or line.startswith("\\ No newline")
        )
    }


def _source_contract_lines(text: str) -> set[str]:
    """Return source declarations/imports that generic source clipping must keep."""
    important: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _SOURCE.match(line):
            important.add(stripped)
    return important


def validate_candidate(
    original: str,
    candidate: str,
    profile: ContentProfile,
) -> tuple[bool, str]:
    """Validate format-specific invariants before a transform may be accepted."""
    if candidate == original:
        return True, "unchanged"
    if not candidate.strip():
        return False, "candidate-empty"
    if len(candidate.encode()) >= len(original.encode()):
        return False, "not-smaller"

    kind = profile.kind
    if kind == "json":
        try:
            json.loads(candidate)
        except (ValueError, TypeError):
            return False, "invalid-json"
        return True, "json-valid"

    if kind == "diff":
        missing = _changed_diff_lines(original) - set(candidate.splitlines())
        if missing:
            return False, "changed-diff-lines-missing"
        return True, "diff-changes-preserved"

    if kind in {"markdown-table", "delimited-table"}:
        original_header = next(
            (line.strip() for line in original.splitlines() if line.strip()),
            "",
        )
        if original_header and original_header not in candidate:
            return False, "table-header-missing"
        return True, "table-schema-preserved"

    if kind == "source":
        declarations = _source_contract_lines(original)
        if declarations and not declarations.issubset(
            {line.strip() for line in candidate.splitlines()}
        ):
            return False, "source-declaration-missing"
        # Python snippets get an extra syntax gate when candidate parses as Python.
        if any(line.lstrip().startswith(("def ", "class ", "import ", "from ")) for line in original.splitlines()):
            try:
                ast.parse(candidate)
            except SyntaxError:
                return False, "source-syntax-invalid"
        return True, "source-contract-preserved"

    return True, "bounded-selective"
