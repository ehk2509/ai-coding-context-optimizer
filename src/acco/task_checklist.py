"""Task-specific coverage checklist extracted from the user's prompt.

Focused verification checks what the agent touched. When an issue names
several paths ("… also reproduces with `scatterplot`"), agents can fix and
verify the first path and stop. A generic "cover everything" rule is easy to
skim past, so this module names the concrete items the prompt itself lists:
each reproduction code example and each sentence that points at another
affected API or path. It is deterministic, prompt-only, and silent unless the
prompt names at least two separate items.
"""

from __future__ import annotations

import re

MAX_ITEMS = 6
MAX_ITEM_CHARS = 180
MAX_CALLS_PER_BLOCK = 4

_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_CALL_RE = re.compile(r"(?<![\w.])([A-Za-z_][\w]*(?:\.[A-Za-z_]\w*)*)\s*\(")
_CODE_REF_RE = re.compile(r"`[^`\n]+`|\b[A-Za-z_]\w*(?:\.\w+)+\b|\b\w+\(\)")
_ALSO_RE = re.compile(
    r"\b(also|as well|likewise|similarly|additionally|in addition|both|"
    r"same (?:bug|issue|problem|error|behaviou?r)|another (?:path|case|api|function|method))\b",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`(\"'])")
_URL_RE = re.compile(r"https?://\S+")
_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)|^\s*File \"", re.MULTILINE)
# Calls that describe setup rather than a distinct code path under test.
_NOISE_CALLS = {
    "print", "len", "range", "list", "dict", "set", "tuple", "str", "int", "float",
    "bool", "open", "isinstance", "type", "super", "sorted", "enumerate", "zip",
    "map", "filter", "min", "max", "sum", "abs", "repr", "format", "getattr",
    "setattr", "hasattr", "assert", "if", "for", "while", "return", "import",
}


def _shorten(text: str) -> str:
    """Collapse whitespace and cap one checklist item."""
    text = " ".join(text.split())
    if len(text) <= MAX_ITEM_CHARS:
        return text
    return text[: MAX_ITEM_CHARS - 1].rstrip() + "…"


def _identifier(ref: str) -> str:
    """Return the bare name a code reference points at (`a.b(x)` -> b)."""
    names = re.findall(r"[A-Za-z_]\w*", ref)
    return names[-1] if names else ""


def _block_calls(code: str) -> tuple[str, ...]:
    """Return the distinct non-trivial calls a reproduction example makes."""
    if _TRACEBACK_RE.search(code):
        return ()
    calls: list[str] = []
    for match in _CALL_RE.finditer(code):
        name = match.group(1)
        if name.split(".")[-1] in _NOISE_CALLS or name in calls:
            continue
        calls.append(name)
        if len(calls) == MAX_CALLS_PER_BLOCK:
            break
    return tuple(calls)


def extract_task_checklist(prompt: str) -> list[str]:
    """Return the separate reproductions/paths the prompt names, in order."""
    examples: list[str] = []
    seen_calls: set[frozenset[str]] = set()
    for index, match in enumerate(_FENCE_RE.finditer(prompt), start=1):
        calls = _block_calls(match.group(1))
        # A repeated example of the same calls is not a separate path.
        if len(calls) < 2 or frozenset(calls) in seen_calls:
            continue
        seen_calls.add(frozenset(calls))
        examples.append(f"code example {index} from the task (calls {', '.join(calls)})")
    others: list[str] = []
    prose = _URL_RE.sub("", _FENCE_RE.sub("\n", prompt))
    lowered = prompt.lower()
    for line in prose.splitlines():
        for sentence in _SENTENCE_RE.split(" ".join(line.split())):
            if not _ALSO_RE.search(sentence):
                continue
            # Only a code reference that appears nowhere else in the prompt marks
            # a different path/API. Another symptom of the same option or
            # function (pylint's "also, the help for `verbose`…") is not a
            # separate item; listing it pulled agents toward the wrong fix.
            if any(
                lowered.count(_identifier(ref).lower()) == 1
                for ref in _CODE_REF_RE.findall(sentence)
                if _identifier(ref)
            ):
                others.append(f'"{_shorten(sentence)}"')
    # Examples alone usually repeat one bug; only an explicit pointer to
    # another affected path/API makes the task multi-path.
    if not others:
        return []
    primary = examples or ["the primary behaviour reported in the task"]
    return list(dict.fromkeys(primary + others))[:MAX_ITEMS]


def task_checklist_note(prompt: str, **_: object) -> str | None:
    """Return a checklist note when the prompt names two or more items."""
    items = extract_task_checklist(prompt)
    if len(items) < 2:
        return None
    return (
        "ACCO TASK CHECKLIST — the task names these separate items. Before "
        "finishing, reproduce or otherwise check each one against your change; "
        "fixing one does not cover the others:\n"
        + "\n".join(f"- {item}" for item in items)
    )
