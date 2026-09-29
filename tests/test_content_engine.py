"""Tests for formal content-compression safety contracts."""

from acco.output import SafetyClass, detect_content, process_output, validate_candidate
from acco.output.content_engine import ContentProfile


def test_content_detector_identifies_structured_payloads():
    """Content detection should be independent from the producing command."""
    assert detect_content('{"items":[1,2,3]}').kind == "json"
    assert detect_content(
        "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
    ).kind == "diff"
    assert detect_content(
        "| name | value |\n|---|---|\n" + "| a | 1 |\n" * 8
    ).kind == "markdown-table"


def test_diff_invariant_rejects_missing_changed_lines():
    """A generic compressor must not lose exact patch additions/deletions."""
    original = "diff --git a/a b/a\n@@ -1 +1 @@\n-old\n+new\n"
    profile = ContentProfile(
        "diff",
        1.0,
        SafetyClass.S4_LOSSY_RECOVERABLE,
    )

    valid, reason = validate_candidate(
        original,
        "diff --git a/a b/a\n@@ -1 +1 @@\n+new\n",
        profile,
    )

    assert valid is False
    assert reason == "changed-diff-lines-missing"


def test_output_result_reports_safety_and_validation():
    """Accepted compression should disclose content type and recovery contract."""
    text = "\n".join(
        [f"2026-01-01 INFO noise {index}" for index in range(160)]
        + ["2026-01-01 ERROR final failure"]
    )

    result = process_output(
        text,
        "unknown-runner",
        exit_code=0,
        min_reduction=0.0,
    )

    assert result.compressed is True
    assert result.content_kind == "log"
    assert result.safety_class == SafetyClass.S4_LOSSY_RECOVERABLE
    assert result.requires_recovery is True
    assert result.validation == "bounded-selective"
