# `acco client-capabilities`

Inspect ACCO's conservative capability contract for supported agent hosts.

## Synopsis

```bash
acco client-capabilities [--client CLIENT] [--json]
```

## Arguments and options

- `--client CLIENT` — show one host in detail. Accepted canonical names include `claude-code`, `codex`, `cursor`, `opencode`, `openclaw`, `hermes`, `copilot`, `antigravity`, `gemini-cli`, `qwen-code`, and `generic-mcp`; common aliases are normalized.
- `--json` — emit the machine-readable registry or selected-client report.

Capabilities are intentionally conservative. `yes` means ACCO may rely on the
boundary without fallback; `conditional` and `advisory` remain non-guaranteed;
`unknown` is never treated as support.

## Exit codes

- `0` — capability report produced successfully.
- `2` — argparse usage error.

## Output contract

Per-client JSON contains a `client` record and feature-level `features` evidence.
Each feature reports exact prerequisite capability levels, whether support is
`guaranteed`, and whether a compatibility fallback remains available.

See [Machine-readable contracts](../JSON_OUTPUTS.md#client-capabilities---json).

## Authoritative runtime help

Run `acco client-capabilities --help` for the installed version.


## Native-hook interpretation

A `yes` for `pre_tool_intercept` or `session_hooks` means `acco setup`
installs and verifies a native host hook surface rather than merely exposing MCP.
Result-replacement guarantees remain host-specific: Gemini CLI and Copilot CLI
can replace accepted successful tool results; Cursor is conditional because only MCP output has a documented replacement field; Qwen Code is reported as `no` for general successful-result replacement. Qwen prompt ingress is conditional because reliable user provenance depends on the optional `submitted_prompt` boundary.
