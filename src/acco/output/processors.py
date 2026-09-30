"""Built-in format-aware command-output processors."""

from __future__ import annotations

import re
import shlex

from .payload_processors import payload_processors
from .specialized_processors import extended_processors
from .text import ensure_newline, filter_text, preprocess

_PYTEST = re.compile(r"\b(pytest|py\.test|python\s+-m\s+pytest)\b", re.I)
_JEST = re.compile(r"\b(jest|vitest|npm\s+test|pnpm\s+test|yarn\s+test)\b", re.I)
_GIT_LOG = re.compile(r"\bgit\s+log\b", re.I)
_NPM_INSTALL = re.compile(r"\b(npm|pnpm|yarn|bun|pip|pip3|uv)\s+(i|install|ci|sync)\b", re.I)
_GIT_STATUS = re.compile(r"\bgit\s+status\b", re.I)
_SEARCH = re.compile(r"(^|[;&|]\s*|\b)(rg|grep|find)\b", re.I)
# grep/rg flags that request surrounding lines (-A/-B/-C N, --context...).
_CONTEXT_FLAG = re.compile(
    r"^(?:-[a-zA-Z]*[ABC](?:=?\d+)?|--(?:after-|before-)?context(?:=\d+)?)$"
)


def _is_context_search(command: str) -> bool:
    """Return whether a grep/rg invocation asks for context around each hit.

    Such output is code the agent chose to read, not a list of hits.
    """
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|;&")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    searching = False
    for token in tokens:
        if token and set(token) <= set("|;&"):
            searching = False
        elif token.rsplit("/", 1)[-1] in {"grep", "egrep", "rg"}:
            searching = True
        elif searching and _CONTEXT_FLAG.match(token):
            return True
    return False


_LINT = re.compile(r"\b(ruff|eslint|pylint|clippy)\b", re.I)
_TYPECHECK = re.compile(r"\b(tsc|mypy|pyright)\b", re.I)
_COMPILED_TEST = re.compile(r"\b(go\s+test|cargo\s+test|dotnet\s+test)\b", re.I)
_BUILD = re.compile(
    r"\b(cargo\s+build|go\s+build|gradle|gradlew|mvn|maven|"
    r"npm\s+run\s+build|pnpm\s+(?:run\s+)?build|yarn\s+build)\b",
    re.I,
)
_CONTAINER_LOG = re.compile(r"\b(docker\s+logs|kubectl\s+logs)\b", re.I)
_FAIL_BLOCK = re.compile(
    r"^=+ FAILURES =+[\s\S]*?(?=^=+ (?:short test summary|warnings summary)|\Z)",
    re.M | re.I,
)
_SHORT_SUMMARY = re.compile(
    r"^=+ short test summary info =+[\s\S]*?(?=^=+ |\Z)",
    re.M | re.I,
)
_LAST_COUNTS = re.compile(r"=+ .*\d+ (passed|failed|error).* =+\s*$", re.I | re.M)


def pytest_slice(text: str) -> str | None:
    """Return a compact pytest failure/summary view when one is available."""
    parts: list[str] = []
    fail = _FAIL_BLOCK.search(text)
    if fail:
        parts.append(fail.group(0).strip())
    summary = _SHORT_SUMMARY.search(text)
    if summary:
        parts.append(summary.group(0).strip())
    counts = list(_LAST_COUNTS.finditer(text))
    if counts:
        parts.append(counts[-1].group(0).strip())
    if not parts:
        return None
    body = "\n\n".join(parts)
    out = (
        f"[filtered pytest: {len(text.splitlines())} lines → failures/summary]\n"
        + body
        + "\n"
    )
    return out if len(out) < len(text) else None


def keep_matching(
    text: str,
    pattern: re.Pattern[str],
    limit: int,
    label: str,
) -> str | None:
    """Keep bounded matching lines when that representation is smaller."""
    lines = text.splitlines()
    kept = [line for line in lines if pattern.search(line)]
    if not kept:
        return None
    kept = kept[:limit]
    omitted = len(lines) - len(kept)
    if omitted <= 0:
        return None
    out = (
        f"[filtered {label}: {len(lines)} lines → {len(kept)} kept, {omitted} omitted]\n"
        + "\n".join(kept)
        + "\n"
    )
    return out if len(out) < len(text) else None


class PytestProcessor:
    """Compress pytest output while retaining failure evidence."""

    name = "pytest"
    priority = 10
    handles_failure = True

    def matches(self, command: str) -> bool:
        """Return whether ``command`` invokes pytest."""
        return bool(_PYTEST.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Compress pytest output conservatively."""
        return pytest_slice(text) or (
            text
            if failed
            else filter_text(preprocess(text), max_lines, keep_tail, prepared=True)
        )


class JsTestProcessor:
    """Compress Jest/Vitest-style output while retaining complex failures."""

    name = "js-test"
    priority = 20
    handles_failure = True

    def matches(self, command: str) -> bool:
        """Return whether ``command`` invokes a supported JavaScript test runner."""
        return bool(_JEST.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Compress JavaScript test output conservatively."""
        complex_failure = failed and bool(
            re.search(r"(?m)^\s+at\s+|^\s*[+-]\s+.+$", text)
        )
        if complex_failure:
            return text
        candidate = keep_matching(
            text,
            re.compile(
                r"(FAIL|PASS|✕|×|Error|Expected|Received|Tests:|Test Suites:|Snapshots:)",
                re.I,
            ),
            limit=max(40, max_lines),
            label="test",
        )
        if candidate:
            return candidate
        prepared = preprocess(text)
        return filter_text(prepared, max_lines, keep_tail, prepared=True)


class GitLogProcessor:
    """Compress ``git log`` into a compact commit inventory."""

    name = "git-log"
    priority = 30
    handles_failure = False

    def matches(self, command: str) -> bool:
        """Return whether ``command`` is a git-log invocation."""
        return bool(_GIT_LOG.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Keep commit identity and subject with compact refs and diff stats."""
        del failed, keep_tail
        prepared = preprocess(text)
        lines = prepared.splitlines()
        commit_starts = [
            index for index, line in enumerate(lines) if line.startswith("commit ")
        ]
        if not commit_starts:
            oneline = [
                line
                for line in lines
                if re.match(r"^[0-9a-f]{4,40}\s+\S", line, re.I)
            ]
            if len(lines) > 40 and len(oneline) >= len(lines) * 0.8:
                kept = lines[:25]
                candidate = (
                    "\n".join(kept)
                    + f"\n... {len(lines) - len(kept)} older commits omitted\n"
                )
                if len(candidate.encode()) < len(text.encode()):
                    return candidate
            return filter_text(prepared, max_lines, 10, prepared=True)

        compact: list[str] = []
        starts = [*commit_starts, len(lines)]
        wants_stats = bool(re.search(r"(?:^|\s)--stat(?:\s|$)", command))
        for position, start in enumerate(commit_starts):
            block = lines[start : starts[position + 1]]
            commit_line = block[0][len("commit ") :].strip()
            commit_id, _, decoration = commit_line.partition(" ")
            label = commit_id[:8]

            refs = ""
            if decoration.startswith("("):
                refs = decoration.strip("()")
                refs = refs.replace("HEAD -> ", "HEAD>")
                refs = re.sub(r"\s*,\s*", ",", refs)

            subject = ""
            stat = ""
            for line in block[1:]:
                stripped = line.strip()
                summary = re.match(
                    r"^(\d+) files? changed(?:, (\d+) insertions?\(\+\))?"
                    r"(?:, (\d+) deletions?\(-\))?$",
                    stripped,
                )
                if summary:
                    if wants_stats:
                        files = int(summary.group(1))
                        inserted = int(summary.group(2) or 0)
                        deleted = int(summary.group(3) or 0)
                        parts = []
                        if files > 1:
                            parts.append(f"{files}f")
                        if inserted:
                            parts.append(f"+{inserted}")
                        if deleted:
                            parts.append(f"-{deleted}")
                        stat = " ".join(parts)
                    continue
                if (
                    subject
                    or not stripped
                    or stripped.startswith(("Author:", "Date:", "Merge:"))
                    or re.match(r"^.+\s+\|\s+\d+", stripped)
                ):
                    continue
                if line.startswith(("    ", "\t")):
                    subject = stripped

            row = label
            if refs:
                row += f" [{refs}]"
            if subject:
                row += " " + subject
            if stat:
                row += f" [{stat}]"
            compact.append(row)
            if len(compact) >= max(20, max_lines):
                break

        omitted = len(commit_starts) - len(compact)
        if omitted > 0:
            compact.append(f"... {omitted} older commits omitted")
        candidate = "\n".join(compact) + "\n"
        return candidate if len(candidate.encode()) < len(text.encode()) else text


class PackageInstallProcessor:
    """Compress successful package-manager installation chatter."""

    name = "package-install"
    priority = 40
    handles_failure = False

    def matches(self, command: str) -> bool:
        """Return whether ``command`` is a supported package installation."""
        return bool(_NPM_INSTALL.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Compress successful package installation output."""
        prepared = preprocess(text)
        candidate = keep_matching(
            prepared,
            re.compile(
                r"(ERR!|error|warn|added \d+|removed \d+|audited|packages? in)",
                re.I,
            ),
            limit=40,
            label="install",
        )
        return candidate or filter_text(
            prepared, max_lines, keep_tail, prepared=True
        )


class GitStatusProcessor:
    """Compress git status into porcelain-like branch and file state."""

    name = "git-status"
    priority = 31
    handles_failure = False

    def matches(self, command: str) -> bool:
        """Return whether the command invokes git status."""
        return bool(_GIT_STATUS.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Drop help prose while retaining branch, staging, and path identity."""
        del command, failed, keep_tail
        prepared = preprocess(text)
        headers: list[str] = []
        changes: list[str] = []
        section = ""

        long_codes = {
            "modified": "M",
            "new file": "A",
            "deleted": "D",
            "renamed": "R",
            "copied": "C",
            "typechange": "T",
            "both modified": "UU",
            "both added": "AA",
            "both deleted": "DD",
            "added by us": "AU",
            "added by them": "UA",
            "deleted by us": "DU",
            "deleted by them": "UD",
        }

        for line in prepared.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("On branch", "Your branch", "HEAD detached")):
                headers.append(stripped)
                continue
            if stripped.startswith("## "):
                headers.append(stripped)
                continue
            if stripped.startswith(("nothing to commit", "no changes added")):
                headers.append(stripped)
                continue
            if stripped.startswith("Changes to be committed:"):
                section = "staged"
                continue
            if stripped.startswith("Changes not staged for commit:"):
                section = "unstaged"
                continue
            if stripped.startswith("Untracked files:"):
                section = "untracked"
                continue
            if stripped.startswith("Unmerged paths:"):
                section = "unmerged"
                continue
            if stripped.startswith("("):
                continue

            leading_spaces = len(line) - len(line.lstrip(" "))
            short = (
                re.match(r"^([ MADRCUT?!]{1,2})\s+(.+)$", line)
                if leading_spaces <= 2 and not line.startswith("\t")
                else None
            )
            if short:
                changes.append(f"{short.group(1)} {short.group(2).strip()}")
                continue

            matched_long = False
            for prefix, code in long_codes.items():
                marker = prefix + ":"
                if not stripped.startswith(marker):
                    continue
                path = stripped.split(":", 1)[1].strip()
                if len(code) == 2:
                    changes.append(f"{code} {path}")
                elif section == "staged":
                    changes.append(f"S {prefix}: {path}")
                elif section == "unstaged":
                    changes.append(f"U {prefix}: {path}")
                else:
                    changes.append(f"{prefix}: {path}")
                matched_long = True
                break
            if matched_long:
                continue

            if (
                section == "untracked"
                and line[:1].isspace()
                and not stripped.startswith("(")
            ):
                changes.append(f"? {stripped}")

        rows = [*headers, *changes[: max(40, max_lines)]]
        if len(changes) > len(rows) - len(headers):
            rows.append(f"... {len(changes) - (len(rows) - len(headers))} paths omitted")
        if not rows:
            return filter_text(prepared, max_lines, 10, prepared=True)
        candidate = "\n".join(rows) + "\n"
        return candidate if len(candidate.encode()) < len(text.encode()) else text


class SearchProcessor:
    """Compress large grep/ripgrep/find result sets to bounded unique hits."""

    name = "search"
    priority = 35
    handles_failure = True

    def matches(self, command: str) -> bool:
        """Return whether the command is a supported search invocation."""
        return bool(_SEARCH.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Keep first unique result lines plus an omitted-result count.

        Context searches pass through unchanged: capping them drops the code
        the agent explicitly asked to read.
        """
        del failed, keep_tail
        if _is_context_search(command):
            return text
        lines = preprocess(text).splitlines()
        unique: list[str] = []
        seen: set[str] = set()
        for line in lines:
            if line in seen:
                continue
            seen.add(line)
            unique.append(line)
            if len(unique) >= max(25, max_lines):
                break
        omitted = len(lines) - len(unique)
        if omitted <= 0:
            return ensure_newline(text)
        result = (
            f"[filtered search: {len(lines)} lines → {len(unique)} unique hits, "
            f"{omitted} omitted]\n"
            + "\n".join(unique)
            + "\n"
        )
        return result if len(result) < len(text) else text


class LintProcessor:
    """Compress common linter output while preserving file diagnostics."""

    name = "lint"
    priority = 36
    handles_failure = True

    def matches(self, command: str) -> bool:
        """Return whether the command invokes a supported linter."""
        return bool(_LINT.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Keep location-bearing diagnostics and summary lines."""
        del command, failed, keep_tail
        candidate = keep_matching(
            preprocess(text),
            re.compile(
                r"(:\d+(?::\d+)?\b|\berror\b|\bwarning\b|"
                r"\bproblems?\b|\bfound\s+\d+\b|\bE\d{3,4}\b|\bW\d{3,4}\b)",
                re.I,
            ),
            limit=max(60, max_lines),
            label="lint",
        )
        return candidate or filter_text(
            preprocess(text), max_lines, 12, prepared=True
        )


class TypecheckProcessor:
    """Compress compiler/typechecker diagnostics without hiding locations."""

    name = "typecheck"
    priority = 37
    handles_failure = True

    def matches(self, command: str) -> bool:
        """Return whether the command invokes a supported typechecker."""
        return bool(_TYPECHECK.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Keep typed diagnostics, source locations, and summaries."""
        del command, failed, keep_tail
        candidate = keep_matching(
            preprocess(text),
            re.compile(
                r"(error\s+TS\d+|:\d+(?::\d+)?\b|\berror:|"
                r"\bnote:|Found \d+ error|Success: no issues)",
                re.I,
            ),
            limit=max(60, max_lines),
            label="typecheck",
        )
        return candidate or filter_text(
            preprocess(text), max_lines, 12, prepared=True
        )


class CompiledTestProcessor:
    """Compress Go/Cargo test output to failures and final package summaries."""

    name = "compiled-test"
    priority = 38
    handles_failure = True

    def matches(self, command: str) -> bool:
        """Return whether the command invokes Go or Cargo tests."""
        return bool(_COMPILED_TEST.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Keep test failures, panic/error lines, and package/result summaries."""
        del command, failed, keep_tail
        candidate = keep_matching(
            preprocess(text),
            re.compile(
                r"(--- FAIL:|\bFAIL\b|\bPASS\b|panicked at|\berror\b|"
                r"test result:|^ok\s|^\?\s|^FAIL\s|Failed!|Passed!|Total tests:|Failed:|Passed:)",
                re.I,
            ),
            limit=max(60, max_lines),
            label="compiled tests",
        )
        return candidate or filter_text(
            preprocess(text), max_lines, 12, prepared=True
        )


class BuildProcessor:
    """Compress common build output while retaining diagnostic evidence."""

    name = "build"
    priority = 39
    handles_failure = True

    def matches(self, command: str) -> bool:
        """Return whether the command invokes a supported build system."""
        return bool(_BUILD.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Keep build errors/warnings and terminal status lines."""
        del command, failed
        candidate = keep_matching(
            preprocess(text),
            re.compile(
                r"(\berror\b|\bwarning\b|FAILED|BUILD (?:SUCCESS|FAIL)|"
                r"Finished|:\d+(?::\d+)?\b)",
                re.I,
            ),
            limit=max(70, max_lines),
            label="build",
        )
        return candidate or filter_text(
            preprocess(text), max_lines, max(keep_tail, 15), prepared=True
        )


class ContainerLogProcessor:
    """Bound successful Docker/Kubernetes log dumps while preserving their tail."""

    name = "container-log"
    priority = 41
    handles_failure = False

    def matches(self, command: str) -> bool:
        """Return whether the command requests Docker or Kubernetes logs."""
        return bool(_CONTAINER_LOG.search(command))

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Retain a bounded head/tail view for successful log commands."""
        del command, failed
        return filter_text(
            preprocess(text),
            max_lines,
            max(keep_tail, 20),
            prepared=True,
        )


class GenericProcessor:
    """Provide a conservative fallback for unknown command families."""

    name = "generic"
    priority = 999
    handles_failure = True

    def matches(self, command: str) -> bool:
        """Match every command as the final fallback."""
        return True

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Compress only successful unknown output; failed output passes through."""
        if failed:
            return text
        prepared = preprocess(text)
        return filter_text(prepared, max_lines, keep_tail, prepared=True)


def default_processors() -> list:
    """Return fresh instances of the complete built-in processor set."""
    return [
        PytestProcessor(),
        JsTestProcessor(),
        GitLogProcessor(),
        GitStatusProcessor(),
        SearchProcessor(),
        LintProcessor(),
        TypecheckProcessor(),
        CompiledTestProcessor(),
        BuildProcessor(),
        PackageInstallProcessor(),
        ContainerLogProcessor(),
        *payload_processors(),
        GenericProcessor(),
        *extended_processors(),
    ]
