import json
import textwrap

from acco.entry import main


def test_dispatcher_preserves_legacy_commands(capsys):
    assert main(["budget", ".", "--window", "1000", "--no-user-scope"]) == 0
    assert "TOTAL_PLANNED" in capsys.readouterr().out


def test_dispatcher_exposes_pack(tmp_path, capsys):
    (tmp_path / "auth.py").write_text(textwrap.dedent("""
        def refresh_session(token: str) -> str:
            return rotate_token(token)
    """))
    assert main([
        "pack", str(tmp_path), "--query", "refresh session", "--max-tokens", "500"
    ]) == 0
    out = capsys.readouterr().out
    assert "ACCO CONTEXT PACK" in out
    assert "auth.py" in out


def test_dispatcher_exposes_output_policy(capsys):
    assert main(["output-policy", "--mode", "terse", "--max-tokens", "250"]) == 0
    out = capsys.readouterr().out
    assert "target <= 250 tokens" in out
    assert "Do not restate the task" in out


def test_dispatcher_exposes_output_save(tmp_path, capsys):
    response = tmp_path / "response.txt"
    response.write_text(
        "Sure!\n\nImplemented.\n\nImplemented.\n",
        encoding="utf-8",
    )
    assert main(["output-save", str(response), "--mode", "terse"]) == 0
    out = capsys.readouterr().out
    assert "Sure!" not in out
    assert out.count("Implemented.") == 1



def test_dispatcher_exposes_context_browser(tmp_path, capsys):
    (tmp_path / "views.py").write_text(textwrap.dedent("""
        def renderTemplate(template):
            return template
    """))
    assert main([
        "browse", str(tmp_path), "--query", "rendr template",
        "--max-files", "3", "--no-changed-boost",
    ]) == 0
    out = capsys.readouterr().out
    assert "CONTEXT BROWSER" in out
    assert "views.py" in out
    assert "renderTemplate" in out



def test_dispatcher_exposes_output_benchmark(tmp_path, capsys):
    manifest = tmp_path / "output.json"
    manifest.write_text(json.dumps({
        "cases": [{
            "id": "duplicate",
            "text": "Done.\n\nDone.\n",
            "mode": "terse",
        }]
    }))

    assert main(["output-benchmark", str(manifest)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["case_count"] == 1
    assert payload["cases"][0]["removed_units"] >= 1



def test_dispatcher_exposes_cost_report(tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    optimized = tmp_path / "optimized.json"
    baseline.write_text(json.dumps([{
        "task_id": "task", "success": True,
        "input_tokens": 1000, "output_tokens": 200, "cost_usd": 1.0,
    }]))
    optimized.write_text(json.dumps([{
        "task_id": "task", "success": True,
        "input_tokens": 400, "output_tokens": 100, "cost_usd": 0.4,
    }]))

    assert main(["cost-report", str(baseline), str(optimized)]) == 0
    out = capsys.readouterr().out
    assert "PAIRED TASKS: 1" in out
    assert "cost/success:" in out
    assert "60.0% reduction" in out



def test_cost_report_accepts_single_paired_agent_manifest(tmp_path, capsys):
    manifest = tmp_path / "agent-runs.json"
    manifest.write_text(json.dumps({
        "runs": [
            {
                "task": "task", "condition": "baseline", "success": True,
                "input_tokens": 1000, "output_tokens": 200,
                "seconds": 2.0, "cost_usd": 1.0,
            },
            {
                "task": "task", "condition": "acco", "success": True,
                "input_tokens": 400, "output_tokens": 100,
                "seconds": 1.0, "cost_usd": 0.4,
            },
        ]
    }), encoding="utf-8")

    assert main(["cost-report", str(manifest)]) == 0
    out = capsys.readouterr().out
    assert "PAIRED TASKS: 1" in out
    assert "60.0% reduction" in out


def test_dispatcher_exposes_experiment_hash(tmp_path, capsys):
    import hashlib

    prompt = "Fix the fixture and make the independent verifier pass."
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({
        "suite_version": 1,
        "protocol": {
            "task_definitions_frozen": False,
            "condition_order_randomized": True,
            "independent_verification": True,
            "frozen_at": "",
            "task_definition_sha256": "",
        },
        "design": {"trials_per_task": 1, "condition_order_seed": 7},
        "repositories": {
            "repo": {"path": "repo", "revision": "a" * 40}
        },
        "runner": {
            "command": ["fake-agent", "{prompt}"],
            "model": "test-model",
            "transcript_mode": "path",
        },
        "tasks": [{
            "id": "fixture",
            "repository": "repo",
            "revision": "a" * 40,
            "prompt": prompt,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "verifier": [["python", "-c", "raise SystemExit(0)"]],
        }],
    }), encoding="utf-8")

    assert main([
        "experiment", str(suite), "--print-task-definition-hash",
    ]) == 0
    value = capsys.readouterr().out.strip()
    assert len(value) == 64
    assert all(ch in "0123456789abcdef" for ch in value)


def test_dispatcher_exposes_output_explain(capsys):
    assert main(["output-explain", "npm install", "--exit-code", "1"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processor"] == "generic"
    assert "package-install" in payload["failure_skipped_processors"]


def test_dispatcher_exposes_output_replay(tmp_path, capsys):
    manifest = tmp_path / "quality.json"
    manifest.write_text(json.dumps({
        "cases": [{
            "id": "git",
            "command": "git log --oneline",
            "text": "\n".join(f"{i:04x} change {i}" for i in range(80)),
            "must_preserve": ["change 0"],
            "min_reduction": 0.10,
        }]
    }), encoding="utf-8")
    assert main(["output-replay", str(manifest)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["failed"] == 0
    assert payload["cases"][0]["processor"] == "git-log"



def test_dispatcher_exposes_setup_doctor_and_uninstall(tmp_path, capsys):
    """Top-level product UX commands should work through the stable dispatcher."""
    assert main([
        "setup",
        str(tmp_path),
        "--host",
        "cursor",
        "--json",
    ]) == 0
    setup = json.loads(capsys.readouterr().out)
    assert setup["configured_hosts"] == ["cursor"]
    assert (tmp_path / ".cursor" / "mcp.json").is_file()
    assert (tmp_path / ".acco.toml").is_file()

    assert main([
        "doctor",
        str(tmp_path),
        "--json",
        "--no-index",
    ]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert "cursor" in doctor["configured_hosts"]
    assert doctor["config_path"].endswith(".acco.toml")

    assert main([
        "uninstall",
        str(tmp_path),
        "--host",
        "cursor",
        "--remove-config",
        "--json",
    ]) == 0
    removed = json.loads(capsys.readouterr().out)
    assert removed["removed_hosts"] == ["cursor"]
    assert removed["config_removed"] is True


def test_dispatcher_exposes_command_discovery(capsys):
    """Users should be able to discover registered commands without README lookup."""
    assert main(["commands"]) == 0
    output = capsys.readouterr().out
    assert "setup" in output
    assert "doctor" in output
    assert "completion" in output
    assert "proxy" in output
    assert "proxy-run" not in output



def test_top_level_help_merges_modern_and_legacy_commands(capsys):
    """A new user should discover setup and legacy tools from one help surface."""
    assert main(["--help"]) == 0
    output = capsys.readouterr().out
    for command in ("setup", "doctor", "pack", "browse", "uninstall", "audit", "map"):
        assert f"  {command}" in output
    assert "docs/CLI_REFERENCE.md" in output


def test_dispatcher_exposes_persistent_proxy_status_without_internal_runner(
    tmp_path,
    monkeypatch,
    capsys,
):
    """Public proxy lifecycle should dispatch while proxy-run stays internal."""
    state = tmp_path / "state"
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("ACCO_STATE_DIR", str(state))

    assert main(["proxy", "status", str(project), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["installed"] is False
    assert payload["profiles"] == []

    assert main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "  proxy" in output
    assert "proxy-run" not in output
