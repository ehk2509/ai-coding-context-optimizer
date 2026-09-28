# `acco setup`

Auto-detect/configure supported coding-agent integrations.

## Synopsis

```bash
acco setup [path] [--host HOST|all ...] [--no-index] [--no-lean]
  [--require-ready] [--json]
```

## Arguments and options

- `path` default `.`.
- `--host` repeatable; omitted means auto-detect. `--host all` means all detected supported hosts. Supported hosts: `claude`, `cursor`, `codex`, `opencode`, `openclaw`, `hermes`, `copilot`, `antigravity`, `gemini`, and `qwen`.
- `--no-index` skips the initial structural-index warm-up.
- `--no-lean` skips the managed ACCO Lean skill for Claude.
- `--require-ready` returns nonzero unless setup finishes fully ready.
- `--json` emits lifecycle, health, profile, Lean, and index results.

## Exit codes

`0` success; `2` invalid/conflicting host config or unsafe mutation refused.

## Output contract

Human setup summary or JSON. Normal setup configures detected hosts, writes the
safe local profile, installs Claude Lean when applicable without overwriting
user-modified skill content, warms the structural index, and runs the same
health checks as `doctor`. Codex, Cursor, Gemini CLI, Qwen Code, and Copilot CLI also receive native project hooks where their host contracts support them. Codex project hooks still require host trust review after first install or a definition change. A successful normal run ends with `READY` and suggests `acco start`.

See [Machine-readable contracts](../JSON_OUTPUTS.md#setup-json).

## Authoritative runtime help

Run `acco setup --help` for argparse's exact usage text for the installed version.
