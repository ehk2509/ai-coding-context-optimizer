# Installation

ACCO's default install path is intentionally short:

```bash
uv tool install acco
cd /path/to/project
acco setup
acco start
```

`uv` keeps ACCO isolated from project virtual environments and gives
`acco update` a clean upgrade path.

## One-command bootstrap

Use `uvx` to run ACCO's bootstrap entry once:

```bash
cd /path/to/project
uvx acco bootstrap
```

Bootstrap first creates a persistent isolated ACCO installation with
`uv tool install acco` (or `pipx` when available), then runs the
normal project setup. This avoids creating host integrations that depend on the
temporary `uvx` environment.

## pipx

```bash
pipx install acco
acco setup
```

## pip compatibility path

```bash
python -m pip install --upgrade acco
acco setup
```

This remains fully supported, but isolated CLI installers are preferred because
they avoid project-environment and PATH confusion.

## Claude Code marketplace

Claude Code 2.1.229+ can install ACCO's generated plugin directly:

```text
/plugin marketplace add elyeshkiri/ai-coding-context-optimizer
/plugin install acco@acco-tools
```

The plugin contains ACCO hooks, MCP integration, Compaction Guardian support,
the ingress skill, and ACCO Lean.

## Standalone release binaries

Tagged releases publish smoke-tested single-file executables for both major
64-bit architectures:

- `acco-linux-x86_64`
- `acco-linux-arm64`
- `acco-macos-arm64`
- `acco-macos-x86_64`
- `acco-windows-x86_64.exe`
- `acco-windows-arm64.exe`

Each binary has a matching SHA-256 sidecar and GitHub build-provenance
attestation. The six targets are built natively from the immutable release tag
and run `acco --help` plus a provider-free `acco demo` smoke test before
upload. Windows Authenticode and macOS Developer ID/notarization are applied
automatically when the corresponding repository signing credentials are
configured.

Linux/macOS users can use the repository installer after a release containing
standalone assets:

```bash
curl -fsSL https://raw.githubusercontent.com/elyeshkiri/ai-coding-context-optimizer/main/scripts/install-standalone.sh | sh
```

This path is optional. Review the script first if your environment does not
permit piped shell installers.

### Windows

Windows x86_64 and ARM64 have native standalone installations that do not
require Python:

```powershell
irm https://raw.githubusercontent.com/elyeshkiri/ai-coding-context-optimizer/main/scripts/install-standalone.ps1 | iex
```

The PowerShell installer:

- detects x86_64 versus ARM64 and downloads the matching Windows asset;
- verifies its SHA-256 sidecar before installation;
- installs it under `%LOCALAPPDATA%\ACCO\bin` by default;
- smoke-tests `acco.exe --help`;
- adds the install directory to the user's `PATH` idempotently.

Open a new PowerShell terminal after the first install, then:

```powershell
cd C:\path\to\project
acco setup
acco start
```

PowerShell completion is available with:

```powershell
acco completion powershell | Out-String | Invoke-Expression
```

For persistent completion, add the generated script to `$PROFILE`.

Native Windows state is stored under `%LOCALAPPDATA%\ACCO` (falling back to
`%APPDATA%\ACCO`). `ACCO_STATE_DIR` still overrides the location.

Linux/macOS installers and the Windows installer all verify the downloaded
SHA-256 checksum before installation.

## Homebrew

Tagged releases publish an `acco.rb` formula generated from the verified
Linux/macOS x86_64 and ARM64 checksums. The release formula works directly:

```bash
brew install --formula \
  https://github.com/elyeshkiri/ai-coding-context-optimizer/releases/latest/download/acco.rb
```

The repository also contains a secret-gated publisher that can create/update
`elyeshkiri/homebrew-acco`. Once that external tap has actually been
published, the normal flow is:

```bash
brew tap elyeshkiri/acco
brew install acco
```

## WinGet

Each release also includes `winget-manifests.zip` containing schema 1.12
multi-file manifests for x64 and ARM64 portable executables. ACCO includes an
optional publisher workflow that can submit those manifests with
`wingetcreate` when `WINGET_TOKEN` is configured. Microsoft still controls
acceptance into the public WinGet community repository; only after that
upstream PR is accepted should users expect:

```powershell
winget install --id ElyesHkiri.ACCO
```

See [Native release signing and package publication](RELEASE_SIGNING.md).

## Persistent provider proxy (optional)

After normal setup, Claude Code and Codex can use a durable background ACCO provider proxy instead of launching through `acco wrap` each time:

```bash
acco proxy install . --host claude --host codex
acco proxy status .
```

Linux uses a `systemd --user` service, macOS uses a user LaunchAgent, and Windows uses a current-user logon task. Persistent profile/service files contain no API keys; native service metadata contains only runtime paths/ids needed to find the credential-free profile, and client authentication continues to flow in the provider request itself. Host routing is changed only after ACCO verifies the expected local proxy instance is actually listening.

Remove the durable routing and autostart services with:

```bash
acco proxy uninstall .
```

See [persistent proxy lifecycle](commands/proxy.md) for host limitations, custom upstreams, stable ports, and rollback behavior.

## Upgrade and repair

Inspect the package-manager command ACCO would use:

```bash
acco update
```

Apply it explicitly:

```bash
acco update --apply
acco setup
```

For raw standalone installs on Linux, macOS, or Windows,
`acco update --apply` detects the current OS/architecture, downloads the
matching release asset and SHA-256 sidecar, verifies integrity, and smoke-tests
the replacement. Linux/macOS replace atomically; Windows schedules replacement
after the current `acco.exe` exits.

When the frozen executable belongs to Homebrew or WinGet, ACCO deliberately
delegates the upgrade back to that package manager instead of overwriting
managed files.

`setup` is idempotent and doubles as the integration repair/migration command.
It also refreshes the structural index and verifies readiness.

## Remove

```bash
acco uninstall . --host all
acco uninstall . --host all --remove-config
```

Only ACCO-owned integration entries are removed.
