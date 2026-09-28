# `acco hook`

Coding-agent hook stdin/stdout adapter. Claude remains the default protocol;
managed integrations use the same command with an explicit native host/event.

## Synopsis

```bash
acco hook
acco hook --host cursor --event preToolUse
acco hook --host gemini --event AfterTool
acco hook --host qwen --event PreToolUse
acco hook --host copilot --event PostToolUse
```

## Arguments and options

- `--host {claude,cursor,gemini,qwen,copilot}` selects the hook protocol.
  Default: `claude`.
- `--event EVENT` supplies the native lifecycle event. It is required for
  non-Claude hosts and rejected for the default Claude adapter.
- Hook JSON is read from stdin. The adapter writes only the selected host's
  valid JSON response to stdout; diagnostics go to stderr.

Normally users do not invoke native variants manually. `acco setup` writes the
project hook configuration for supported detected hosts.

## Exit codes

`0` is normal pass-through/replacement. Native adapters intentionally fail open
as an optimization layer: malformed or unsupported runtime input emits `{}`
rather than turning an ACCO failure into a tool denial. Host-enforced ACCO
decisions such as the large-source read guard are represented inside the valid
host response JSON.

Argparse usage errors return the standard nonzero argparse exit code.

## Output contract

- Claude: Claude Code hook JSON.
- Cursor: native `permission` / `continue` / `additional_context` fields.
- Gemini CLI: native decision/reason and event-specific context fields; accepted
  large replaceable tool results use AfterTool result hiding with ACCO's compact
  recoverable representation as the replacement reason.
- Qwen Code: native `hookSpecificOutput` for pre-tool, prompt, and session
  control. ACCO does not claim general PostToolUse result replacement.
- Copilot CLI: native `permissionDecision` and `modifiedResult`; successful
  large tool results can be replaced before they enter model context.

ACCO normalizes these transports into one `HookRuntime`; compression, read
guard, recovery, continuity, ingress, and telemetry policy are not duplicated in
host adapters.

## Authoritative runtime help

Run `acco hook --help` for argparse's exact usage text for the installed version.
