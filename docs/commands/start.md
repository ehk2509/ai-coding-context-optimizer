# `acco start`

Warm ACCO's structural index and launch the coding agent for the current project.

## Synopsis

```bash
acco start [path] [--agent NAME] [--remember] [--no-index]
  [--dry-run] [--json] [-- AGENT_ARGS...]
```

## Arguments and options

- `path` — project root; defaults to `.`.
- `--agent` — explicitly select `claude`, `codex`, `gemini`, `qwen`, `cursor`,
  `opencode`, `openclaw`, `hermes`, `copilot`, or `antigravity`.
- `--remember` — persist an explicit agent choice in private ACCO user state.
- `--no-index` — skip the normal structural-index warm-up.
- `--dry-run` — resolve the launch and index without starting the agent.
- `--json` — with `--dry-run`, emit the resolved launch plan as JSON.
- arguments after `--` are forwarded unchanged to the selected agent.

With one detected agent, no selection is required. With several agents ACCO
uses a remembered preference, otherwise prompts on a TTY or asks for
`--agent` in non-interactive use.

Claude, Codex, and Gemini launch through ACCO's ephemeral provider wrapper.
Other supported agents use their installed ACCO integration directly.

## Exit codes

- live mode returns the selected coding agent's exit code.
- `0` — successful dry-run.
- `2` — no supported agent, invalid selection, indexing failure, or launch failure.

## Output contract

Dry-run JSON returns the selected agent, executable, integration/wrapper state,
forwarded argv, and structural-index metadata. Launch preferences are stored in
private ACCO state, not in the repository.

## Authoritative runtime help

Run `acco start --help` for the installed version.
