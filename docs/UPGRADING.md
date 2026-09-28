# Upgrading and migration

## 1.20 native package ownership and standalone updates

Version 1.20 makes `acco update` installation-aware across all supported native
distributions:

- `uv`, `pipx`, and pip installations keep using their Python package manager;
- Homebrew-managed frozen binaries delegate to `brew upgrade acco`;
- WinGet-managed frozen binaries delegate to
  `winget upgrade --id ehk2509.ACCO --exact`;
- raw Linux/macOS/Windows standalone binaries detect x86_64 versus ARM64,
  download the matching release asset and checksum, smoke-test it, and replace
  safely.

This avoids silently mutating package-manager-owned files while still giving
raw standalone installs an in-product update path.

ACCO treats setup as an idempotent repair/migration operation.

## 1.15 ACCO package identity

Version 1.15 completes the product rename to **ACCO — AI Coding Context Optimizer**.

Canonical identifiers are now:

- PyPI distribution: `acco`
- Python package/import: `acco`
- CLI: `acco` and `acco-pack`
- project config: `.acco.toml`
- environment namespace: `ACCO_*`
- source package: `src/acco`
- optional Rust package/module: `acco-fast` / `_acco_fast`

Inspect or apply the recommended upgrade for the way ACCO is installed:

```bash
acco update
acco update --apply
```

ACCO prefers `uv tool upgrade acco`, then `pipx upgrade acco`, and falls
back to `python -m pip install --upgrade acco`. No mutation happens unless
`--apply` is explicit.

The GitHub repository remains `ehk2509/ai-coding-context-optimizer`.
Checked-in benchmark identifiers use the canonical ACCO namespace.

## 1.14 expanded coding-agent integration matrix

Version 1.14 extends managed setup, doctor, and uninstall support across Claude
Code, Cursor, Codex, OpenCode, OpenClaw, Hermes Agent, GitHub Copilot CLI /
VS Code, and Google Antigravity.

Existing Claude/Cursor/Codex users do not need to change configuration. Re-run:

```bash
acco setup .
acco doctor .
```

to refresh ACCO-owned entries after upgrading. Setup now performs its own
index warm-up and readiness check, so a separate `acco doctor` is optional.

New host-specific behavior:

- OpenCode uses project `.opencode/opencode.json`; ACCO refuses to
  create a competing sibling JSON file when only `.opencode/opencode.jsonc`
  exists.
- OpenClaw is configured through its own `openclaw mcp set/unset` commands.
- Hermes receives a marked ACCO block under top-level `mcp_servers`
  in `~/.hermes/config.yaml`; unmanaged same-name entries are preserved and
  cause setup to fail closed.
- Copilot CLI is managed through `copilot mcp add/remove`. VS Code Copilot
  continues to use the workspace `.vscode/mcp.json` surface when present.
- Antigravity uses workspace `.agents/mcp_config.json`; the current CLI is
  detected through the `agy` executable.

`acco setup . --host all` now means all detected supported hosts,
rather than every host ACCO knows about.

## 1.13 recoverable optimization platform

Version 1.13 adds persistent typed project memory, adaptive MCP disclosure,
recoverable MCP schema compression, universal `tsr_...` recovery handles, the
measured keep-or-revert optimizer, provider-prefix reuse telemetry, an opt-in
local provider proxy, and focused browser-context compression.

Existing projects remain compatible without editing `.acco.toml`:

- `mcp.profile` still defaults to `"full"`;
- `mcp.compress_schemas` defaults to `false`;
- `provider.prefix_tracking` defaults to `true`, but it records data only
  when provider request transformation is actually used;
- the provider proxy never starts automatically;
- persistent memory is explicit and does not auto-harvest conversation text.

Newly generated configs include the current `[mcp]` and `[provider]` keys.
Setup does not overwrite an existing project-owned config, so add those keys
manually only when you want to opt in.

Lossy v1.13 surfaces can emit `tsr_...` handles. Recover them with
`acco recover` or MCP `recover_context`. The older
`acco output OUTPUT_ID` path remains supported for saved Bash output.

The local provider proxy is a new trust boundary. It is loopback-only by
default, requires HTTPS for non-local upstreams, and is never installed into a
host automatically. Read [Security & privacy](../SECURITY.md) before pointing a
client at it.

## 1.12 routing and cost intelligence

Version 1.12 adds the centralized pricing registry, cost advisor, automatic
model-routing policy, and quality-gated routing calibration. Model routing
remains opt-in. Existing projects therefore keep their prior model behavior
until `[model_routing] enabled = true` or the corresponding environment
override is set.

Historical benchmark rate files remain frozen. Do not replace old benchmark
prices with the current built-in registry when reproducing a historical result.

## 1.11 output, Smart Tool Proxy, and semantic retrieval

Version 1.11 expands command-output processors, adds the opt-in Smart Tool Proxy
for large Claude Reads, and strengthens semantic retrieval. Smart Tool Proxy is
disabled by default. Existing configs do not need migration unless you want to
enable `[tool_proxy]`.

If project-managed Claude hooks were created by an older version, rerun
`acco setup .` so managed hook definitions match the installed package.

## 1.10 persistent semantic index

Version 1.10 introduces persistent chunk-level semantic retrieval and optional
HNSW acceleration. Semantic retrieval remains opt-in and uses local model
weights only. Existing lexical/structural workflows require no migration.

Changing `ACCO_SEMANTIC_MODEL_REVISION` intentionally creates distinct
semantic state instead of reusing vectors produced by different weights.

## 1.9 ingress, retrieval cache, knowledge, and marketplace packaging

Version 1.9 adds safe oversized-prompt staging, persistent retrieval-result
caching, the optional Rust fastpath, durable evidence-backed project knowledge,
static MCP profiles, and Claude Code marketplace packaging.

Prompt staging and knowledge-assisted read avoidance remain opt-in. Existing
projects can keep their current config; rerun setup when you want the current
managed Claude/Cursor/Codex representation or marketplace-compatible generated
plugin assets.

## 1.8 frozen session-efficiency holdout

Version 1.8 adds benchmark/evaluation commands and a paid workflow; it does not
change the default 1.7 runtime session-efficiency switches.

New commands:

- `acco session-holdout` — run/resume the two-phase frozen experiment,
  blind grading, and effectiveness report;
- `acco session-holdout-evaluate` — evaluate already merged evidence
  without rerunning agents.

The new frozen manifest reuses the existing 24 SWE-bench Verified task cohort
but changes the runner protocol, so it has its own independent task-definition
hash. Do not edit that manifest in place and continue calling the result the
same holdout.

The control label `v1.6-session-baseline` means **1.6 session behavior emulated
by the current binary with session efficiency disabled**. It is intentionally
not a historical package checkout.

## 1.7 session-efficiency control plane

Version 1.7 widens Claude `PostToolUse` from `Bash|Read` to
`Bash|Read|Edit|Write` so structured continuity can observe edits without
rewriting their tool result. Rerun `acco setup` after upgrading so the
managed project hook matcher is refreshed.

A new `[efficiency]` config table defaults on for continuity, exact cross-turn
dedup, and bounded waste detection. Existing configs without the table keep
working and receive the safe defaults. Use the documented
`ACCO_EFFICIENCY`, `ACCO_CONTINUITY`,
`ACCO_CROSS_TURN_DEDUP`, or `ACCO_WASTE_DETECTION` overrides
for temporary rollback.

The new efficiency snapshot/event files live under the existing private Token
Saver state directory. They do not alter repository files, ranking indexes, or
frozen benchmark definitions.

## 1.6 evidence pipeline

Version 1.6 adds `blind-grade` and `evidence-run`, plus cache-TTL-aware
experiment telemetry. Existing project integrations should rerun setup so the
managed Claude hooks stay current. Historical experiment files remain readable;
new publishable output-cost evidence should use the full frozen/graded pipeline.

## Standard upgrade

```bash
python -m pip install --upgrade acco
cd /path/to/project
acco setup .
acco doctor .
```

This refreshes ACCO-owned host entries without duplicating them.

## Why rerun setup?

New releases can change:

- Claude hook matchers/events (including the `Stop`/`StopFailure` hooks used
  for output-budget telemetry);
- MCP command arguments;
- generated project defaults;
- managed host MCP/config block contents;
- generated on-demand skills.

Setup re-applies the current managed representation while preserving unrelated
configuration.

## Project configuration upgrades

`.acco.toml` is user/project-owned after creation. Setup does not replace
an existing file.

When a release adds new optional keys, existing projects continue to use code
defaults until you add those keys. Output telemetry therefore defaults to
enabled even for an older config that does not yet contain `telemetry = true`;
set `output.telemetry = false` or `ACCO_OUTPUT_TELEMETRY=0` to opt out.

Environment variables remain higher-priority overrides.

## From manual integrations to managed setup

If Claude/Cursor already has a normal `mcpServers.acco` entry, setup can
refresh that owned key. Other hosts use the host-specific ownership rules in
[Integrations](../INTEGRATIONS.md).

Codex is stricter: an unmanaged `[mcp_servers.acco]` section is not
silently converted. Remove or rename it yourself before using managed setup.

## Legacy `acco install`

The lower-level Claude-only installer remains supported for compatibility.

New projects should prefer:

```bash
acco setup . --host claude
```

because setup configures both hooks and MCP and participates in the unified
doctor/uninstall lifecycle.

## Rollback

1. Install the desired older package version.
2. Re-run that version's setup/install command.
3. Run the matching doctor/host checks.
4. Do not reuse a newer benchmark claim as evidence for an older binary.

Example:

```bash
python -m pip install "acco==1.15.0"
```

If that version predates unified setup, follow its release documentation and
use the legacy installer where required.

## Remove managed integration before a clean reinstall

```bash
acco uninstall . --host all
python -m pip install --force-reinstall acco
acco setup .
acco doctor .
```

Add `--remove-config` only if you also want to delete
`.acco.toml`.

## Release provenance

Project versions are immutable. The release workflow refuses to reuse an
existing version tag for a different commit, builds/validates distributions
before publication, and creates the GitHub release only after PyPI publication
succeeds.

See [CHANGELOG.md](../CHANGELOG.md) for version-specific behavior.
