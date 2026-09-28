# `acco uninstall`

Remove only ACCO-owned host integration entries.

## Synopsis

```bash
acco uninstall [path] [--host HOST|all ...] [--remove-config] [--json]
```

## Arguments and options

- `path` default `.`.
- `--host` repeatable; default is all supported hosts: `claude`, `cursor`, `codex`, `opencode`, `openclaw`, `hermes`, `copilot`, `antigravity`, `gemini`, and `qwen`.
- `--remove-config` also removes `.acco.toml`.
- `--json` emits lifecycle result.

## Exit codes

`0` success; `2` invalid/conflicting managed config.

## Output contract

Human removal summary or JSON. Shared Codex/Cursor/Gemini/Qwen hook files keep unrelated entries, while the dedicated Copilot `acco.json` hook file is removed only if it is still ACCO-owned; see [Machine-readable contracts](../JSON_OUTPUTS.md#uninstall-json).

## Authoritative runtime help

Run `acco uninstall --help` for argparse's exact usage text for the installed version.
