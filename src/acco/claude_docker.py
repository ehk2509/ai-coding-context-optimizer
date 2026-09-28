"""Run one Claude Code benchmark arm inside an isolated Docker container."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile

from . import docker_platform
from pathlib import Path

AUTH_MODES = ("api", "subscription")

# The SWE-bench images keep the prepared repository at /testbed with its
# dependencies installed into the "testbed" conda environment.
TASK_REPO = "/testbed"
TASK_ENV_BIN = "/opt/miniconda3/envs/testbed/bin"
TASK_BASE_PYTHON = "/opt/miniconda3/bin/python3"

# Claude Code and ACCO are layered onto the task image. ACCO gets its own venv
# built from the image's base conda Python; only an `acco` launcher reaches
# PATH, so the agent's python/pip stay the project's testbed environment.
_TASK_AGENT_DOCKERFILE = """\
FROM {agent_image} AS tools
FROM {task_image}
COPY --from=tools /usr/local/lib/node_modules/@anthropic-ai/claude-code /opt/claude-code
COPY --from=tools /usr/bin/rg /usr/local/bin/rg
COPY --from=tools /opt /tmp/tools-opt
RUN site="$(dirname "$(ls -d /tmp/tools-opt/*/lib/python3.11/site-packages/acco | head -n 1)")" \\
    && {base_python} -m venv --without-pip /opt/acco-venv \\
    && cp -a "$site/." "$(/opt/acco-venv/bin/python -c 'import sysconfig; print(sysconfig.get_path("purelib"))')/" \\
    && rm -rf /tmp/tools-opt \\
    && /opt/acco-venv/bin/python -c 'import acco.entry' \\
    && ln -s /opt/claude-code/bin/claude.exe /usr/local/bin/claude \\
    && printf '#!/bin/sh\\nexec /opt/acco-venv/bin/python -m acco.entry "$@"\\n' > /usr/local/bin/acco \\
    && chmod 755 /usr/local/bin/acco
ENV PATH="{env_bin}:${{PATH}}" \\
    DISABLE_AUTOUPDATER=1
WORKDIR {repo}
"""


def _docker_env(command: list[str], name: str) -> None:
    """Handle docker env."""
    if os.environ.get(name):
        command.extend(["-e", name])


def task_agent_image(agent_image: str, task_image: str) -> str:
    """Build (once) and return the task image with Claude Code and ACCO added."""
    dockerfile = _TASK_AGENT_DOCKERFILE.format(
        agent_image=agent_image,
        task_image=task_image,
        base_python=TASK_BASE_PYTHON,
        env_bin=TASK_ENV_BIN,
        repo=TASK_REPO,
    )
    digest = hashlib.sha256(dockerfile.encode("utf-8")).hexdigest()[:16]
    tag = f"acco-task-agent:{digest}"
    exists = subprocess.run(
        ["docker", "image", "inspect", tag], capture_output=True, check=False
    )
    if exists.returncode != 0:
        proc = subprocess.run(
            ["docker", "build", "-q", "-t", tag, "-"],
            input=dockerfile,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise ValueError(
                f"failed to build task agent image from {task_image}: "
                + proc.stderr[-2000:]
            )
    return tag


def _git(worktree: Path, *args: str, stdin: bytes | None = None) -> None:
    """Run one git command in the worktree and raise on failure."""
    proc = subprocess.run(
        ["git", "-C", str(worktree), *args],
        input=stdin,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(
            f"git {' '.join(args)} failed: "
            + proc.stderr.decode("utf-8", "replace")[-2000:]
        )


def _gitignore_literal(path: str) -> str:
    """Return an anchored .gitignore pattern that matches exactly one path."""
    escaped = "".join("\\" + ch if ch in "\\*?[!# " else ch for ch in path)
    return "/" + escaped


def prepare_task_worktree(worktree: Path, task_image: str) -> None:
    """Make the snapshot match the grader's /testbed before the agent starts.

    The official images commit environment adjustments on top of the task
    revision and keep build products (compiled extensions, egg-info) as
    ignored files. The adjustments become the snapshot's new base commit so
    they never appear in the agent's patch; the build products are copied in
    and excluded so the editable install at /testbed keeps working.
    """
    environment = subprocess.run(
        [
            "docker", "run", "--rm", task_image, "git",
            "-c", "safe.directory=*", "-C", TASK_REPO,
            "diff", "--binary", "HEAD~1", "HEAD",
        ],
        capture_output=True,
        check=False,
    )
    if environment.returncode != 0:
        raise ValueError(
            "failed to read the SWE-bench environment commit: "
            + environment.stderr.decode("utf-8", "replace")[-2000:]
        )
    if environment.stdout.strip():
        _git(worktree, "apply", "--index", "--binary", "-", stdin=environment.stdout)
        _git(
            worktree, "commit", "-q", "--no-gpg-sign", "--no-verify",
            "-m", "SWE-bench environment",
        )

    proc = subprocess.Popen(
        [
            "docker", "run", "--rm", task_image, "bash", "-c",
            f"cd {TASK_REPO} && git -c safe.directory='*' ls-files -z -o -i "
            "--exclude-standard | tar --null -T - -cf -",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    copied: list[str] = []
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            for member in archive:
                if member.isfile() or member.issym():
                    copied.append(member.name)
                archive.extract(member, worktree, filter="data")
    finally:
        proc.stdout.close()
    stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    if proc.stderr:
        proc.stderr.close()
    if proc.wait() != 0:
        raise ValueError(f"failed to copy SWE-bench build products: {stderr[-2000:]}")
    if copied:
        # Some images ignore build products only through their own
        # .git/info/exclude; exclude every copied path explicitly so none of
        # them can leak into the captured patch.
        exclude = worktree / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write("\n# SWE-bench build products\n")
            handle.writelines(_gitignore_literal(name) + "\n" for name in copied)


def run(
    *,
    worktree: Path,
    transcript: Path,
    prompt_file: Path,
    model: str,
    condition: str,
    image: str,
    auth: str = "api",
    task_image: str | None = None,
) -> int:
    """Run the requested value."""
    if shutil.which("docker") is None:
        raise ValueError("Docker is required for the isolated Claude runner")
    if auth not in AUTH_MODES:
        raise ValueError("auth must be api or subscription")
    if auth == "subscription":
        # A long-lived token from `claude setup-token`. The host's own login is
        # never copied into the container, so refresh-token rotation inside a
        # run cannot sign the host session out.
        if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            raise ValueError(
                "CLAUDE_CODE_OAUTH_TOKEN is required for subscription runs; "
                "create one with `claude setup-token`"
            )
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_API_KEY is required for Claude benchmark runs")
        if not os.environ.get("ANTHROPIC_WORKSPACE_ID"):
            raise ValueError(
                "ANTHROPIC_WORKSPACE_ID is required for this frozen benchmark key"
            )
    if condition not in {"baseline", "enabled"}:
        raise ValueError("condition must be baseline or enabled")
    if not worktree.is_dir() or not prompt_file.is_file():
        raise ValueError("benchmark worktree and prompt file must exist")

    prompt = prompt_file.read_text(encoding="utf-8")
    claude_home = transcript.parent / "claude-home"
    # A retried run reuses this directory; a failed attempt's leftover config
    # and backups make the next Claude Code start refuse to run.
    shutil.rmtree(claude_home, ignore_errors=True)
    claude_home.mkdir(parents=True, exist_ok=True)

    # With a task image the agent works in the grader's own environment: the
    # snapshot is mounted over /testbed so its interpreter, dependencies and
    # editable install resolve to the agent's code.
    repo_mount = "/workspace"
    if task_image:
        prepare_task_worktree(worktree, task_image)
        image = task_agent_image(image, task_image)
        repo_mount = TASK_REPO

    user_args, sandboxed_root = docker_platform.docker_user_args()
    child_env = os.environ.copy()
    if auth == "api":
        child_env["ANTHROPIC_CUSTOM_HEADERS"] = (
            "anthropic-workspace-id: " + os.environ["ANTHROPIC_WORKSPACE_ID"]
        )
    command = [
        "docker", "run", "--rm",
        *user_args,
        "--workdir", repo_mount,
        "-e", "HOME=/tmp",
        "-v", f"{worktree.resolve()}:{repo_mount}",
        "-v", f"{claude_home.resolve()}:/tmp/.claude",
    ]
    if sandboxed_root:
        # Claude Code refuses --dangerously-skip-permissions as root unless it
        # is told it is sandboxed, which this throwaway container is.
        command.extend(["-e", "IS_SANDBOX=1"])
    state_dir = os.environ.get("ACCO_STATE_DIR")
    if state_dir:
        state_path = Path(state_dir).resolve()
        state_path.mkdir(parents=True, exist_ok=True)
        command.extend([
            "-v",
            f"{state_path}:/acco-state",
            "-e",
            "ACCO_STATE_DIR=/acco-state",
        ])
    credentials = (
        ("CLAUDE_CODE_OAUTH_TOKEN",)
        if auth == "subscription"
        else ("ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID")
    )
    for name in (
        *credentials,
        "ACCO_DISABLED",
        "ACCO_BENCHMARK_CONDITION",
        "ACCO_BENCHMARK_TASK",
        "ACCO_BENCHMARK_TRIAL",
        "ACCO_EFFICIENCY",
        "ACCO_CONTINUITY",
        "ACCO_CROSS_TURN_DEDUP",
        "ACCO_WASTE_DETECTION",
        "ACCO_OUTPUT_POLICY",
        "ACCO_TASK_CHECKLIST",
    ):
        _docker_env(command, name)
    if auth == "api":
        command.extend(["-e", "ANTHROPIC_CUSTOM_HEADERS"])
    command.extend([
        "-e", "DISABLE_AUTOUPDATER=1",
        image,
        "claude",
        "-p", prompt,
        "--model", model,
        "--dangerously-skip-permissions",
        "--max-turns", "50",
        "--output-format", "json",
    ])
    proc = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        env=child_env,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=os.sys.stderr)

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        if proc.returncode != 0:
            return proc.returncode
        raise ValueError(
            "Claude Code returned exit 0 but no valid JSON result"
        ) from exc
    if not isinstance(result, dict):
        if proc.returncode != 0:
            return proc.returncode
        raise ValueError("Claude Code JSON result must be an object")
    # Exhausting the turn budget is a legitimate experimental outcome: the run
    # consumed real usage and left a (possibly partial) patch for the verifier.
    # Only infrastructure failures such as API or billing errors abort.
    turn_limited = result.get("subtype") == "error_max_turns"
    if proc.returncode != 0 and not turn_limited:
        return proc.returncode
    if (
        result.get("terminal_reason") == "api_error"
        or result.get("api_error_status") is not None
        or (result.get("is_error") is True and not turn_limited)
    ):
        detail = str(result.get("result") or result.get("terminal_reason") or "API error")
        raise ValueError(f"Claude Code API failure: {detail}")
    usage = result.get("usage")
    if not isinstance(usage, dict) or sum(
        int(usage.get(key) or 0)
        for key in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        )
    ) <= 0:
        raise ValueError("Claude Code returned no billable model usage")

    try:
        paths = sorted((claude_home / "projects").rglob("*.jsonl"))
        if not paths:
            raise ValueError(
                "Claude Code produced no transcript; the run cannot be costed"
            )
        transcript.parent.mkdir(parents=True, exist_ok=True)
        with transcript.open("wb") as output:
            for path in paths:
                body = path.read_bytes()
                output.write(body)
                if body and not body.endswith(b"\n"):
                    output.write(b"\n")
    finally:
        # Keep only the evidence needed for accounting. Claude's private config
        # and session-home contents are not benchmark artifacts.
        shutil.rmtree(claude_home, ignore_errors=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--auth", choices=AUTH_MODES, default="api")
    parser.add_argument(
        "--task-image",
        default="",
        help="run the agent inside this SWE-bench task image instead of --image",
    )
    args = parser.parse_args(argv)
    try:
        return run(
            worktree=Path(args.worktree),
            transcript=Path(args.transcript),
            prompt_file=Path(args.prompt_file),
            model=args.model,
            condition=args.condition,
            image=args.image,
            auth=args.auth,
            task_image=args.task_image or None,
        )
    except (OSError, ValueError) as exc:
        print(f"isolated Claude runner error: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
