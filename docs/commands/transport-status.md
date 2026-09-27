# `acco transport-status`

Report ACCO's provider-transport guarantees for supported coding hosts without
assuming that MCP detection implies provider interception.

## Synopsis

```bash
acco transport-status
acco transport-status --host claude
acco transport-status --host cursor --json
```

## Behavior

The registry distinguishes four materially different provider-routing states:

- `automatic` — ACCO can configure the documented surface itself.
- `environment-only` — the host documents environment-based routing, but ACCO
  will not mutate user shell/login files merely to make it persistent.
- `manual-setting` — the host exposes a documented user setting, but not a
  stable machine-writable contract ACCO is willing to own.
- `unsupported` — ACCO does not claim that provider transport is available.

Foreground and persistent support are reported separately.

## Arguments and options

- `--host NAME` — inspect one host. Known aliases such as `claude-code`,
  `cursor-agent`, and `copilot-cli` normalize to their registry entry.
- `--json` — emit the machine-readable record.

Without `--host`, ACCO prints the complete provider-transport registry.

## Exit codes

- `0` — registry/report generated successfully.
- `2` — unknown host name.

## Output contract

JSON for a single host has the shape:

```json
{
  "host": {
    "host": "cursor",
    "provider": "openai",
    "foreground": "manual-setting",
    "persistent": "manual-setting",
    "persistent_mode": null,
    "requires_model": false,
    "note": "..."
  }
}
```

The complete report uses a `hosts` object keyed by canonical host name.

This command describes provider-boundary transport only. It does not replace
`client-capabilities`, which reports broader MCP/hook/session capabilities.

## Authoritative runtime help

Run `acco transport-status --help` for the arguments supported by the installed
version.
