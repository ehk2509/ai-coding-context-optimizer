"""Coverage for the six everyday-efficiency product moves."""

from __future__ import annotations

from pathlib import Path

from acco.context_audit import context_audit_report
from acco.efficiency.guardian import capture_guardian, guardian_context, guardian_report
from acco.efficiency.store import update_snapshot
from acco.install import merge_hooks
from acco.lean_skill import SKILL_TEXT, install_lean_skill
from acco.live_status import render_status
from acco.output import OutputPipeline
from acco.wrapper import build_wrap_plan


def test_compaction_guardian_captures_and_restores_structured_state(tmp_path: Path):
    def seed(payload: dict) -> None:
        payload["last_session"] = "abc"
        payload["sessions"] = {
            "abc": {
                "task": "debugging",
                "working_files": [{"path": "src/app.py", "action": "edit"}],
                "commands": [{"label": "pytest tests/test_app.py -q"}],
                "failures": [{"label": "pytest tests/test_app.py -q"}],
                "validations": [
                    {
                        "kind": "test",
                        "label": "pytest tests/test_app.py -q",
                        "status": "failed",
                    }
                ],
                "last_activity": 123,
            }
        }

    update_snapshot(tmp_path, seed)
    checkpoint = capture_guardian(
        tmp_path,
        session_id="different-host-session",
        source="precompact:auto",
    )
    assert checkpoint is not None
    assert checkpoint["task"] == "debugging"
    assert checkpoint["working_files"][0]["path"] == "src/app.py"

    report = guardian_report(tmp_path)
    assert report["available"] is True
    restored = guardian_context(
        tmp_path,
        session_id="new-session",
        source="resume",
    )
    assert restored is not None
    assert "src/app.py" in restored
    assert "pytest tests/test_app.py -q" in restored
    assert "raw prompts" in report["privacy"]


def test_install_registers_precompact_hook():
    merged = merge_hooks({})
    assert "PreCompact" in merged["hooks"]
    commands = merged["hooks"]["PreCompact"][0]["hooks"]
    assert commands[0]["command"] == "acco hook"


def test_wrapper_presets_keep_provider_specific_base_paths():
    claude = build_wrap_plan("claude", [], port=8123)
    codex = build_wrap_plan("codex", ["--help"], port=8124)
    gemini = build_wrap_plan("gemini", [], port=8125)

    assert claude.base_url_env == "ANTHROPIC_BASE_URL"
    assert claude.local_base_url == "http://127.0.0.1:8123"
    assert codex.base_url_env == "OPENAI_BASE_URL"
    assert codex.local_base_url == "http://127.0.0.1:8124/v1"
    assert gemini.base_url_env == "GOOGLE_GEMINI_BASE_URL"


def test_unknown_wrapper_without_provider_signal_requires_explicit_boundary():
    try:
        build_wrap_plan("custom-agent", [], port=8126, env={})
    except ValueError as exc:
        assert "--provider" in str(exc)
    else:
        raise AssertionError("unknown wrapper should require explicit boundary")


def test_portable_lean_skill_is_safe_and_installable(tmp_path: Path):
    paths = install_lean_skill(tmp_path, host="all")
    assert len(paths) == 2
    for path in paths:
        assert path.read_text(encoding="utf-8") == SKILL_TEXT
    assert "Never skip investigation or verification" in SKILL_TEXT


def test_payload_json_is_selected_for_unknown_command():
    payload = "[\n" + ",\n".join(
        f'{{"id": {index}, "value": "same"}}' for index in range(100)
    ) + "\n]\n"
    result = OutputPipeline().process(payload, command="custom-tool dump")
    assert result.processor == "payload-json"
    assert result.compressed is True
    assert "_acco_omitted_items" in result.text


def test_payload_page_is_selected_for_unknown_browser_dump():
    text = (
        "<html><body><main><h1>Settings</h1>"
        + "".join(f"<div>noise {index}</div>" for index in range(300))
        + "<button aria-label='Save'>Save</button></main></body></html>"
    )
    result = OutputPipeline().process(text, command="custom-browser-dump")
    assert result.processor == "payload-page"
    assert result.compressed is True
    assert "Save" in result.text


def test_payload_diff_preserves_every_changed_line():
    context = "\n".join(f" context {index}" for index in range(50))
    text = (
        "diff --git a/a.py b/a.py\n"
        "index 111..222 100644\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,52 +1,52 @@\n"
        f"{context}\n"
        "-old value\n"
        "+new value\n"
    )
    result = OutputPipeline().process(text, command="custom-diff-source")
    assert result.processor == "payload-diff"
    assert "-old value" in result.text
    assert "+new value" in result.text
    assert "unchanged diff context" in result.text


def test_context_audit_finds_cross_host_instruction_bloat(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("rule\n" * 250, encoding="utf-8")
    skill = tmp_path / ".agents" / "skills" / "demo"
    skill.mkdir(parents=True)
    skill.joinpath("SKILL.md").write_text("portable skill\n", encoding="utf-8")

    report = context_audit_report(tmp_path, user_scope=False)
    kinds = {item["kind"] for item in report["items"]}
    assert "agents_md" in kinds
    assert "skill" in kinds
    assert report["oversized"]
    assert report["mutates_files"] is False


def test_live_status_renderer_is_one_line():
    rendered = render_status(
        {
            "estimated_saved_tokens": 1250,
            "waste_signals": 2,
            "prefix_reuse_rate": 0.8,
            "working_files": 3,
            "health": "HEALTHY",
        }
    )
    assert "\n" not in rendered
    assert "saved~1.2Kt" in rendered
    assert "prefix 80%" in rendered
