"""The PostToolUse hook that makes `filter` fire without being remembered."""

import io
import json

import pytest

from acco.hook import cap_for, main, run
from acco.output_telemetry import load_output_telemetry


def _payload(response, tool="Bash", command="npm test"):
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": {"command": command},
        "tool_response": ({"stdout": response, "stderr": "", "interrupted": False, "isImage": False}
                          if isinstance(response, str) else response),
    }


def _updated(payload):
    code, response = run(payload)
    assert code == 0
    return response["hookSpecificOutput"]["updatedToolOutput"]["stdout"] if response else None



def test_hook_kill_switch_makes_all_events_noops(monkeypatch):
    monkeypatch.setenv("ACCO_DISABLED", "1")
    noisy = "\n".join(f"line {i}" for i in range(500))
    assert run(_payload(noisy)) == (0, None)
    assert run({
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/example.py"},
    }) == (0, None)


def test_large_bash_output_is_filtered():
    noisy = "\n".join(f"line {i}" for i in range(500))
    out = _updated(_payload(noisy))
    assert out is not None
    assert len(out.splitlines()) < 120
    assert "acco: filtered" in out


def test_session_start_resume_does_not_treat_matcher_as_clear(tmp_path):
    from acco.state import record_read, load as load_state

    p = tmp_path / "a.py"
    p.write_text("x = 1\n")
    record_read(tmp_path, p, "deadbeef")
    code, response = run({
        "hook_event_name": "SessionStart",
        "cwd": str(tmp_path),
        "source": "resume",
        "matcher": "startup|resume|clear",
    })
    assert code == 0
    assert response is None
    assert load_state(tmp_path).get("reads")


def test_session_start_without_transcripts_is_silent(tmp_path):
    code, response = run({"hook_event_name": "SessionStart", "cwd": str(tmp_path)})
    assert code == 0
    assert response is None


def test_user_prompt_auto_policy_injects_once_per_task(tmp_path, monkeypatch):
    """Claude prompt hooks should inject a task policy once, then inherit it silently."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "cwd": str(tmp_path),
        "session_id": "session-1",
        "prompt": "Implement automatic output policy injection",
    }

    code, response = run(payload)
    assert code == 0
    assert response is not None
    context = response["hookSpecificOutput"]["additionalContext"]
    assert "OUTPUT TASK: coding." in context

    followup = dict(payload, prompt="go for the next move")
    assert run(followup) == (0, None)


def test_user_prompt_auto_policy_can_be_disabled(tmp_path, monkeypatch):
    """The generation-policy hook should have an independent project/env kill switch."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ACCO_OUTPUT_POLICY", "0")

    assert run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "session_id": "session-1",
            "prompt": "Implement automatic output policy injection",
        }
    ) == (0, None)


_MULTI_PATH_PROMPT = (
    "Implement a fix for wrong legend values.\n"
    "```python\nso.Plot(df, x='a').add(so.Dot())\n```\n"
    "The issue also reproduces if you use `scatterplot`."
)


def test_user_prompt_injects_task_checklist_by_default(tmp_path, monkeypatch):
    """Multi-path prompts get a checklist next to the generation policy."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ACCO_TASK_CHECKLIST", raising=False)

    code, response = run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "session_id": "session-1",
            "prompt": _MULTI_PATH_PROMPT,
        }
    )

    context = response["hookSpecificOutput"]["additionalContext"]
    assert code == 0
    assert "ACCO GENERATION POLICY" in context
    assert "ACCO TASK CHECKLIST" in context
    assert "`scatterplot`" in context


def test_user_prompt_task_checklist_env_switch(tmp_path, monkeypatch):
    """ACCO_TASK_CHECKLIST=0 removes only the checklist."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ACCO_TASK_CHECKLIST", "0")

    code, response = run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "session_id": "session-1",
            "prompt": _MULTI_PATH_PROMPT,
        }
    )

    context = response["hookSpecificOutput"]["additionalContext"]
    assert code == 0
    assert "ACCO GENERATION POLICY" in context
    assert "ACCO TASK CHECKLIST" not in context


def test_prompt_and_stop_hooks_capture_real_usage_without_content(
    tmp_path, monkeypatch
):
    """Claude prompt/Stop hooks should produce content-free usage telemetry."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")
    prompt = {
        "hook_event_name": "UserPromptSubmit",
        "cwd": str(tmp_path),
        "session_id": "s1",
        "prompt_id": "p1",
        "transcript_path": str(transcript),
        "prompt": "Implement caching",
    }
    assert run(prompt)[0] == 0

    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "model": "claude-test",
                    "usage": {
                        "input_tokens": 11,
                        "cache_creation_input_tokens": 22,
                        "cache_read_input_tokens": 33,
                        "output_tokens": 123,
                    },
                    "content": [{"type": "text", "text": "SECRET RESPONSE"}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert run(
        {
            "hook_event_name": "Stop",
            "cwd": str(tmp_path),
            "session_id": "s1",
            "transcript_path": str(transcript),
            "last_assistant_message": "SECRET RESPONSE",
        }
    ) == (0, None)

    records = load_output_telemetry(tmp_path)
    assert len(records) == 1
    assert records[0]["output_tokens"] == 123
    assert records[0]["selected_budget"] == 420
    assert "SECRET RESPONSE" not in json.dumps(records[0])


def test_output_telemetry_can_be_disabled_independently(tmp_path, monkeypatch):
    """Telemetry opt-out should not disable generation policy injection."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ACCO_OUTPUT_TELEMETRY", "0")
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")

    code, response = run(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "session_id": "s1",
            "transcript_path": str(transcript),
            "prompt": "Implement caching",
        }
    )
    assert code == 0
    assert response is not None
    assert "additionalContext" in response["hookSpecificOutput"]

    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {
            "id": "m1",
            "usage": {"output_tokens": 50},
            "content": [],
        },
    }) + "\n", encoding="utf-8")
    assert run(
        {
            "hook_event_name": "Stop",
            "cwd": str(tmp_path),
            "session_id": "s1",
            "transcript_path": str(transcript),
        }
    ) == (0, None)
    assert load_output_telemetry(tmp_path) == []


def test_small_output_is_left_alone():
    """Rewriting a short result risks losing detail for no gain."""
    assert _updated(_payload("\n".join(f"line {i}" for i in range(30)))) is None


def test_non_bash_tools_are_never_rewritten():
    """Outlining a Read would break Edit, which matches on exact file content."""
    body = "\n".join(f"line {i}" for i in range(500))
    assert _updated(_payload(body, tool="Read")) is None
    assert _updated(_payload(body, tool="Edit")) is None
    assert _updated(_payload(body, tool="Grep")) is None
    assert _updated(_payload(body, tool="WebFetch")) is None
    assert _updated(_payload(body, tool="mcp__github__search")) is None


def test_output_is_never_replaced_with_something_larger():
    noisy = "\n".join("error!" for _ in range(200))
    out = _updated(_payload(noisy))
    if out is not None:
        assert len(out) < len(noisy) + 200


def test_empty_response_is_ignored():
    assert _updated(_payload("")) is None
    assert _updated(_payload("   \n  ")) is None


def test_missing_fields_do_not_crash():
    assert run({}) == (0, None)
    assert run({"tool_name": "Bash"}) == (0, None)


def _log(n, width=90):
    """n lines of realistic width — real build output is not `line 7`."""
    return "\n".join(f"{i:04d} {'compiling module ' + str(i):<{width}}" for i in range(n))


def test_short_output_is_left_alone():
    """Median real Bash output is 8 lines. It must never be touched."""
    assert _updated(_payload(_log(8))) is None
    assert _updated(_payload(_log(39))) is None


def test_default_floor_filters_moderate_output():
    """The old 120-line floor fired on 2.8% of real calls. 40 is the point."""
    out = _updated(_payload(_log(60)))
    assert out is not None
    assert len(out.splitlines()) < 60


def test_cap_scales_with_input():
    """A huge log keeps more lines than a merely large one."""
    assert cap_for(50) < cap_for(500) < cap_for(5000)
    big = _updated(_payload(_log(1500)))
    assert big is not None
    # the 90-line cap for huge logs, plus banners/errors/tail markers
    assert 60 < len(big.splitlines()) < 160


def test_marginal_saving_is_refused(monkeypatch):
    """The note costs ~30 tokens. Filtering must not be a net loss."""
    monkeypatch.setenv("ACCO_MIN_LINES", "10")
    monkeypatch.setenv("ACCO_MAX_LINES", "8")
    tiny = "\n".join(f"{i}" for i in range(12))
    assert _updated(_payload(tiny)) is None, "saved less than the note it adds"


def test_thresholds_are_configurable(monkeypatch):
    """Env overrides still win over the defaults."""
    body = _log(60)
    monkeypatch.setenv("ACCO_MIN_LINES", "500")
    assert _updated(_payload(body)) is None, "floor raised above the input"

    monkeypatch.setenv("ACCO_MIN_LINES", "10")
    monkeypatch.setenv("ACCO_MAX_LINES", "8")
    out = _updated(_payload(body))
    assert out is not None
    assert len(out.splitlines()) < len(body.splitlines())


def test_main_passes_through_invalid_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    assert main() == 0
    assert capsys.readouterr().out == "", "no output means Claude keeps the original"


def test_main_emits_valid_json_for_a_big_payload(monkeypatch, capsys):
    noisy = "\n".join(f"line {i}" for i in range(500))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_payload(noisy))))
    assert main() == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "updatedToolOutput" in parsed["hookSpecificOutput"]


def test_a_hook_crash_never_breaks_the_tool_call(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_payload("x\n" * 500))))
    monkeypatch.setattr(
        "acco.hook.OutputPipeline.process",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert main() == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad", ["[]", '"a string"', "null"])
def test_non_object_payloads_pass_through(monkeypatch, capsys, bad):
    monkeypatch.setattr("sys.stdin", io.StringIO(bad))
    assert main() == 0
    assert capsys.readouterr().out == ""
