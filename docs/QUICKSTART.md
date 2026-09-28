# Quickstart

This guide gets **ACCO — AI Coding Context Optimizer** from installation to a verified local integration in about one minute for an ordinary project.

## 1. Install

ACCO supports Python 3.10+. The preferred isolated CLI install is:

```bash
uv tool install acco
```

For a one-command persistent bootstrap:

```bash
cd /path/to/project
uvx acco bootstrap
```

The temporary `uvx` process first installs ACCO persistently through
`uv tool`, then runs setup. It does not leave host integrations pointing at an
ephemeral environment.

Alternatives are `pipx install acco` and
`python -m pip install --upgrade acco`.

On Windows x86_64 or ARM64, the standalone PowerShell installer requires no
Python and adds ACCO to the user PATH:

```powershell
irm https://raw.githubusercontent.com/ehk2509/ai-coding-context-optimizer/main/scripts/install-standalone.ps1 | iex
```

The shell/PowerShell standalone installers also support Linux ARM64 and
macOS Intel in addition to the existing x86_64/Apple-Silicon paths.

The PyPI distribution and executable are both `acco`. Running `acco` with
no arguments shows the project-aware home screen instead of the full expert
command catalog.

## 2. Configure a project

From the repository you want your coding agent to work on:

```bash
cd /path/to/project
acco setup
```

Setup auto-detects supported hosts, configures only ACCO-owned entries,
installs the safe local defaults, installs managed Claude Lean when applicable,
warms the structural index, and verifies readiness. A healthy run ends with
`ACCO SETUP — READY`.

Explicit host selection is also available:

```bash
acco setup . --host claude
acco setup . --host cursor --host codex
acco setup . --host opencode --host hermes
acco setup . --host copilot --host antigravity
acco setup . --host gemini --host qwen
acco setup . --host openclaw
acco setup . --host all
```

Setup is idempotent. `--host all` means all detected supported hosts, not every
product ACCO knows about. Re-running setup after an upgrade is the
supported repair/migration path. Native host hooks are installed for Codex, Cursor, Gemini CLI, Qwen Code, and Copilot CLI when those surfaces are selected or detected. Codex still requires its own project-hook trust review.

## 3. Start coding

```bash
acco start
```

With one detected coding agent ACCO launches it directly. With several, ACCO
uses a remembered choice or asks once. Claude, Codex, and Gemini are launched
through ACCO's ephemeral provider wrapper; other supported agents use their
managed integrations.

Check the simple product health view at any time:

```bash
acco status
```

`acco doctor` remains the deeper troubleshooting command.

## 4. See ACCO work without spending provider tokens

```bash
acco demo
```

The demo builds a real bounded repository pack but makes no provider request.

## 5. Try retrieval directly

Inspect ranked context without involving an agent:

```bash
acco browse . --query "refresh session token"
```

Build a bounded context pack:

```bash
acco pack . --query "refresh session token" --max-tokens 6000
```

Explain a surprising rank:

```bash
acco ranking-explain . --query "refresh session token"
```

## 6. Measure your existing context

```bash
acco audit .
acco sessions .
```

`audit` measures always-on project/user context. `sessions` reads Claude
Code transcripts and reports recorded API token fields plus estimated tool-result
sizes. These are measurements, not universal savings claims.

## 7. Optional project configuration

Setup creates a project-owned `.acco.toml`. A small excerpt of the
current defaults is:

```toml
version = 1

[profile]
mode = "safe"

[hooks]
guard = true
read_max_lines = 220

[mcp]
profile = "full"
adaptive_max_tools = 12
compress_schemas = false

[provider]
prefix_tracking = true
history_dedup = true
model_routing = "off"
```

The generated file contains additional output, routing, efficiency, ingress,
retrieval, and Smart Tool Proxy defaults. Setup does not overwrite an existing
project-owned config on upgrade; missing keys use runtime defaults until you add
them. Environment variables take precedence. See
[Configuration](CONFIGURATION.md) for the complete file and migration rules.

## 8. Upgrade, repair, or remove

Inspect the preferred package-manager upgrade:

```bash
acco update
acco update --apply
```

Repair after changing host configuration or upgrading:

```bash
acco setup
```

Setup is idempotent and includes its own readiness check. Use `acco doctor`
only when you want deeper troubleshooting detail.

Remove ACCO-owned host entries:

```bash
acco uninstall . --host all
```

Also remove the project config:

```bash
acco uninstall . --host all --remove-config
```

Uninstall preserves unrelated MCP servers, unrelated Claude hooks, unmanaged
Codex configuration, and a user-modified generated Claude skill.

## Next

- [Worked end-to-end example](WORKED_EXAMPLE.md)
- [CLI reference](CLI_REFERENCE.md)
- [Machine-readable CLI contracts](JSON_OUTPUTS.md)
- [Integrations](../INTEGRATIONS.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Validation](../VALIDATION.md)
