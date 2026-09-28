"""Evaluate a frozen real-output corpus with ACCO and a pinned peer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from acco.estimate import estimate_tokens
from acco.output.text import critical_lines
from acco.output_processors import process_output


def _load_and_verify(corpus: Path) -> tuple[dict, list[tuple[dict, str]]]:
    """Load a frozen corpus and verify its metadata and raw-output hashes."""
    manifest_path = corpus / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    protocol = payload.get("protocol", {})
    if protocol.get("frozen") is not True:
        raise ValueError("real-output corpus must be frozen")

    canonical = json.dumps(
        {
            "environment": payload["environment"],
            "summary": payload["summary"],
            "captures": payload["captures"],
            "skipped": payload["skipped"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    computed_freeze = hashlib.sha256(canonical).hexdigest()
    if computed_freeze != protocol.get("freeze_sha256"):
        raise ValueError(
            "real-output corpus freeze mismatch: "
            f"computed={computed_freeze} declared={protocol.get('freeze_sha256')}"
        )

    cases: list[tuple[dict, str]] = []
    for case in payload["captures"]:
        raw = (corpus / case["output_path"]).read_text(encoding="utf-8")
        encoded = raw.encode()
        digest = hashlib.sha256(encoded).hexdigest()
        if digest != case["output_sha256"]:
            raise ValueError(
                f"raw capture hash mismatch for {case['id']}: "
                f"computed={digest} declared={case['output_sha256']}"
            )
        if len(encoded) != case["output_bytes"]:
            raise ValueError(f"raw capture byte mismatch for {case['id']}")
        if len(raw.splitlines()) != case["output_lines"]:
            raise ValueError(f"raw capture line mismatch for {case['id']}")
        cases.append((case, raw))
    return payload, cases


def _score_case(case: dict, raw: str, output: str, processor: str, changed: bool) -> dict:
    """Score one transformed output with shared preservation metrics."""
    original_tokens = estimate_tokens(raw)
    output_tokens = estimate_tokens(output)
    required = critical_lines(raw)
    present = {line.strip() for line in output.splitlines() if line.strip()}
    missing = [line for line in required if line.strip() not in present]
    return {
        "id": case["id"],
        "tool": case["tool"],
        "command": case["command"],
        "exit_code": case["exit_code"],
        "processor": processor,
        "changed": changed,
        "original_bytes": len(raw.encode()),
        "output_bytes": len(output.encode()),
        "original_tokens": original_tokens,
        "output_tokens": output_tokens,
        "token_reduction": (
            0.0
            if original_tokens <= 0
            else 1.0 - output_tokens / original_tokens
        ),
        "critical_lines": len(required),
        "missing_critical": missing,
        "critical_survival": not missing,
    }


def _summarize(rows: list[dict]) -> dict:
    """Aggregate one engine's per-case results."""
    original_tokens = sum(row["original_tokens"] for row in rows)
    output_tokens = sum(row["output_tokens"] for row in rows)
    original_bytes = sum(row["original_bytes"] for row in rows)
    output_bytes = sum(row["output_bytes"] for row in rows)
    critical_cases = [row for row in rows if row["critical_lines"]]
    return {
        "cases": len(rows),
        "changed_cases": sum(row["changed"] for row in rows),
        "original_tokens": original_tokens,
        "output_tokens": output_tokens,
        "weighted_token_reduction": (
            0.0
            if original_tokens <= 0
            else 1.0 - output_tokens / original_tokens
        ),
        "original_bytes": original_bytes,
        "output_bytes": output_bytes,
        "weighted_byte_reduction": (
            0.0
            if original_bytes <= 0
            else 1.0 - output_bytes / original_bytes
        ),
        "critical_cases": len(critical_cases),
        "critical_survival_rate": (
            1.0
            if not critical_cases
            else sum(row["critical_survival"] for row in critical_cases)
            / len(critical_cases)
        ),
    }


def _evaluate_local(cases: list[tuple[dict, str]]) -> dict:
    """Evaluate the current ACCO implementation."""
    rows = []
    for case, raw in cases:
        result = process_output(
            raw,
            case["command"],
            exit_code=case["exit_code"],
            min_reduction=0.0,
        )
        rows.append(
            _score_case(
                case,
                raw,
                result.text,
                result.processor,
                result.compressed,
            )
        )
    return {"summary": _summarize(rows), "cases": rows}


_PEER_RUNNER = r"""
import json
import pathlib
import sys

from src.engine import CompressionEngine

corpus = pathlib.Path(sys.argv[1])
manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
engine = CompressionEngine()
rows = []
for case in manifest["captures"]:
    raw = (corpus / case["output_path"]).read_text(encoding="utf-8")
    output, processor, changed = engine.compress(
        case["command"],
        raw,
        exit_code=case["exit_code"],
    )
    rows.append(
        {
            "id": case["id"],
            "processor": processor,
            "changed": bool(changed),
            "output": output,
        }
    )
print(json.dumps(rows))
"""


def _evaluate_peer(
    cases: list[tuple[dict, str]],
    corpus: Path,
    peer_path: Path,
) -> dict:
    """Evaluate a checked-out ppgranger/token-saver revision in isolation."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(peer_path)
    completed = subprocess.run(
        [sys.executable, "-c", _PEER_RUNNER, str(corpus.resolve())],
        cwd=peer_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "peer evaluation failed: "
            + completed.stderr[-2000:]
        )
    peer_rows = json.loads(completed.stdout)
    indexed = {row["id"]: row for row in peer_rows}
    rows = []
    for case, raw in cases:
        peer = indexed[case["id"]]
        rows.append(
            _score_case(
                case,
                raw,
                peer["output"],
                peer["processor"],
                peer["changed"],
            )
        )
    return {"summary": _summarize(rows), "cases": rows}


def main() -> int:
    """Verify the corpus and emit same-input engine comparison evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        default="benchmarks/cli-output-real-v1",
    )
    parser.add_argument("--ppgranger-path")
    parser.add_argument("--ppgranger-sha")
    parser.add_argument("--out")
    args = parser.parse_args()

    try:
        corpus = Path(args.corpus).resolve()
        manifest, cases = _load_and_verify(corpus)
        report = {
            "corpus": {
                "path": str(corpus),
                "freeze_sha256": manifest["protocol"]["freeze_sha256"],
                "source_workflow_run_id": manifest["protocol"][
                    "source_workflow_run_id"
                ],
                "captured_cases": len(cases),
                "claim_boundary": manifest["protocol"]["claim_boundary"],
            },
            "ehk2509": _evaluate_local(cases),
        }
        if args.ppgranger_path:
            report["ppgranger"] = _evaluate_peer(
                cases,
                corpus,
                Path(args.ppgranger_path).resolve(),
            )
            report["ppgranger"]["revision"] = args.ppgranger_sha
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    rendered = json.dumps(report, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    local = report["ehk2509"]["summary"]
    print(
        "real corpus: "
        f"{local['cases']} cases, "
        f"{local['weighted_token_reduction'] * 100:.2f}% local reduction, "
        f"{local['critical_survival_rate'] * 100:.2f}% critical survival",
        file=sys.stderr,
    )
    if "ppgranger" in report:
        peer = report["ppgranger"]["summary"]
        print(
            "peer corpus: "
            f"{peer['weighted_token_reduction'] * 100:.2f}% reduction, "
            f"{peer['critical_survival_rate'] * 100:.2f}% critical survival",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
