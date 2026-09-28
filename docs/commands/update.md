# `acco update`

Inspect or apply the recommended package-manager upgrade for ACCO.

## Synopsis

```bash
acco update [--apply] [--json]
```

## Arguments and options

- `--apply` — execute the detected upgrade command.
- `--json` — emit package-manager, command, apply state, and return code.

ACCO preserves the installation owner:

- `uv` installations use `uv tool upgrade acco`;
- `pipx` installations use `pipx upgrade acco`;
- ordinary Python installs fall back to the current interpreter's
  `pip install --upgrade acco`;
- Homebrew-managed frozen binaries use `brew upgrade acco`;
- WinGet-managed frozen binaries use
  `winget upgrade --id ehk2509.ACCO --exact`;
- raw standalone Linux/macOS/Windows binaries use ACCO's checksum-verified
  native updater for the current OS and architecture.

No package-manager or standalone mutation occurs unless `--apply` is explicit.

## Exit codes

Without `--apply`, returns `0`. With `--apply`, returns the selected package
manager's exit code.

## Output contract

JSON fields are `schema`, `manager`, `command`, `applied`,
`returncode`, and `standalone_state`. The command does not edit project
configuration; rerun
`acco setup` after an upgrade to repair/migrate integrations idempotently.

## Authoritative runtime help

Run `acco update --help` for the installed version.
