import json

from acco.output_saver import (
    build_output_policy,
    compact_output,
    compact_structured_result,
)


def test_output_policy_has_mode_budget_and_stop_rules():
    policy = build_output_policy("terse")
    assert policy.max_tokens == 300
    assert "target <= 300 tokens" in policy.instructions
    assert "Do not restate the task" in policy.instructions
    assert (
        "Stop once the acceptance criteria are satisfied and the relevant tests pass"
        in policy.instructions
    )


def test_output_policy_never_budgets_away_verification():
    policy = build_output_policy("normal", task="coding")
    assert "limits prose only, never tool use, investigation, or verification" in (
        policy.instructions
    )
    assert "run the project's existing tests for the code you touched" in (
        policy.instructions
    )
    assert "a passing reproduction alone is not sufficient" in policy.instructions
    assert "smallest existing test, lint, typecheck, or build target" in policy.instructions
    assert "Do not rerun an unchanged failing command" in policy.instructions


def test_output_policy_requires_covering_every_reported_path():
    # Focused verification must not turn "fixed the first path" into "done".
    policy = build_output_policy("normal", task="coding")
    assert "re-read the task" in policy.instructions
    assert "every reported symptom, code path, API, and reproduction" in policy.instructions
    assert "not only the first one fixed" in policy.instructions


def test_output_policy_accepts_explicit_budget():
    policy = build_output_policy("normal", 123)
    assert policy.max_tokens == 123


def test_output_policy_adapts_budget_and_rules_to_coding():
    policy = build_output_policy("normal", task="coding")

    assert policy.task == "coding"
    assert policy.max_tokens == 600
    assert "OUTPUT TASK: coding." in policy.instructions
    assert "skip conversational preambles" in policy.instructions
    assert "Do not reproduce unchanged code" in policy.instructions
    assert "Do not add a recap" in policy.instructions


def test_output_policy_debugging_separates_evidence_from_hypothesis():
    policy = build_output_policy("terse", task="debugging")

    assert policy.max_tokens == 350
    assert "Separate facts from hypotheses" in policy.instructions
    assert "do not invent a root cause" in policy.instructions
    assert "manufacturing a confident explanation" in policy.instructions


def test_output_policy_explicit_budget_overrides_task_default():
    policy = build_output_policy("normal", 123, "explanation")

    assert policy.task == "explanation"
    assert policy.max_tokens == 123


def test_output_policy_rejects_unknown_task():
    import pytest

    with pytest.raises(ValueError, match="unknown output task"):
        build_output_policy("normal", task="side-quest")


def test_compaction_removes_filler_and_exact_duplicate_prose_but_preserves_code():
    code = """```diff
- const enabled = false;
+ const enabled = true;
```"""
    text = f"""Sure!

Implemented the fix.

Implemented the fix.

{code}

Tests: 42 passed, 0 failed.

Tests: 42 passed, 0 failed.
"""
    result = compact_output(text, mode="normal")

    assert "Sure!" not in result.text
    assert result.text.count("Implemented the fix.") == 1
    assert result.text.count("Tests: 42 passed, 0 failed.") == 1
    assert code in result.text
    assert result.code_preserved is True
    assert result.output_tokens < result.original_tokens
    assert result.removed_units >= 3


def test_enforced_budget_trims_prose_without_cutting_code():
    prose = " ".join(
        f"Sentence number {n} explains an implementation detail." for n in range(80)
    )
    code = """```python
def keep_exactly():
    return "unchanged"
```"""
    result = compact_output(
        prose + "\n\n" + code,
        mode="terse",
        max_tokens=120,
        enforce_budget=True,
    )

    assert code in result.text
    assert result.code_preserved is True
    assert result.output_tokens <= 120


def test_code_larger_than_budget_is_preserved_and_reported():
    code = "```text\n" + ("important-output\n" * 50) + "```"
    result = compact_output(
        code,
        mode="terse",
        max_tokens=20,
        enforce_budget=True,
    )

    assert code in result.text
    assert result.code_preserved is True
    assert result.budget_exceeded is True


def test_structured_agent_state_uses_compact_deterministic_json():
    payload = {
        "status": "success",
        "tests": {"failed": 0, "passed": 42},
        "changed_files": ["src/auth.ts"],
    }
    compact = compact_structured_result(payload)

    assert compact == json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    assert "\n" not in compact
    assert ": " not in compact
