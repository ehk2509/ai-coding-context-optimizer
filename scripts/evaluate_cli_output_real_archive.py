"""Evaluate an immutable archived real-output corpus against both engines."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import evaluate_cli_output_real_corpus as base


def _extract_verified(archive_path: Path, freeze_path: Path, root: Path) -> dict:
    """Verify archive/freeze provenance and materialize raw captures safely."""
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    protocol = freeze.get("protocol", {})
    if protocol.get("frozen") is not True:
        raise ValueError("archived real-output corpus must be frozen")

    archive_bytes = archive_path.read_bytes()
    archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    if archive_sha != protocol.get("source_artifact_sha256"):
        raise ValueError(
            "corpus archive SHA-256 mismatch: "
            f"computed={archive_sha} declared={protocol.get('source_artifact_sha256')}"
        )

    root_resolved = root.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            destination = (root / member.filename).resolve()
            if not destination.is_relative_to(root_resolved):
                raise ValueError(f"unsafe archive member: {member.filename}")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)

    manifest_path = root / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        {
            "environment": raw["environment"],
            "summary": raw["summary"],
            "captures": raw["captures"],
            "skipped": raw["skipped"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    definition_sha = hashlib.sha256(canonical).hexdigest()
    if definition_sha != protocol.get("capture_definition_sha256"):
        raise ValueError(
            "capture definition mismatch: "
            f"computed={definition_sha} "
            f"declared={protocol.get('capture_definition_sha256')}"
        )
    if raw.get("protocol", {}).get("processor_lock_sha") != protocol.get(
        "processor_lock_sha"
    ):
        raise ValueError("capture processor lock does not match frozen sidecar")
    if raw["summary"] != freeze.get("summary"):
        raise ValueError("capture summary does not match frozen sidecar")

    # Derive a temporary frozen manifest only after the original ZIP and its
    # raw capture definition have been verified. Raw output files are unchanged.
    raw["protocol"] = {
        **raw.get("protocol", {}),
        "frozen": True,
        "frozen_at": protocol["frozen_at"],
        "definition_sha256": definition_sha,
        "freeze_sha256": definition_sha,
        "claim_boundary": protocol["claim_boundary"],
    }
    manifest_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return freeze


def main() -> int:
    """Compare both engines only after archived corpus provenance is verified."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--ppgranger-path")
    parser.add_argument("--ppgranger-sha")
    parser.add_argument("--out")
    args = parser.parse_args()

    try:
        with tempfile.TemporaryDirectory(prefix="acco-real-corpus-") as tmp:
            root = Path(tmp)
            freeze = _extract_verified(
                Path(args.archive).resolve(),
                Path(args.freeze).resolve(),
                root,
            )
            _, cases = base._load_and_verify(root)
            report = {
                "corpus": {
                    "kind": freeze["protocol"]["kind"],
                    "freeze_sha256": freeze["protocol"][
                        "capture_definition_sha256"
                    ],
                    "archive_sha256": freeze["protocol"]["source_artifact_sha256"],
                    "source_workflow_run_id": freeze["protocol"][
                        "source_workflow_run_id"
                    ],
                    "processor_lock_sha": freeze["protocol"]["processor_lock_sha"],
                    "captured_cases": len(cases),
                    "claim_boundary": freeze["protocol"]["claim_boundary"],
                },
                "ehk2509": base._evaluate_local(cases),
            }
            if args.ppgranger_path:
                report["ppgranger"] = base._evaluate_peer(
                    cases,
                    root,
                    Path(args.ppgranger_path).resolve(),
                )
                report["ppgranger"]["revision"] = args.ppgranger_sha
    except (
        OSError,
        ValueError,
        RuntimeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    rendered = json.dumps(report, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    local = report["ehk2509"]["summary"]
    print(
        "fresh real corpus: "
        f"{local['cases']} cases, "
        f"{local['weighted_token_reduction'] * 100:.2f}% local reduction, "
        f"{local['critical_survival_rate'] * 100:.2f}% critical survival",
        file=sys.stderr,
    )
    if "ppgranger" in report:
        peer = report["ppgranger"]["summary"]
        print(
            "fresh peer corpus: "
            f"{peer['weighted_token_reduction'] * 100:.2f}% reduction, "
            f"{peer['critical_survival_rate'] * 100:.2f}% critical survival",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
