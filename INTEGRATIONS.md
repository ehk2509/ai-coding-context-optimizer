# Agent integrations

Install ACCO in the environment that launches the coding agent, then let
one setup command detect, configure, index, and verify supported hosts:

```bash
uv tool install acco
cd /absolute/path/to/project
acco setup
acco start
```

`pipx install acco` and `python -m pip install --upgrade acco` remain
supported alternatives. Setup is the normal repair command too; `doctor` is
reserved for deeper troubleshooting.

## Claude Code marketplace install

Claude-only users on Claude Code **2.1.229+** can install through the repository
marketplace without first placing the `acco` console script on `PATH`:

```text
/plugin marketplace add ehk2509/ai-coding-context-optimizer
/plugin install acco@acco-tools
```

The marketplace uses Claude Code's command-source installation flow. Claude
shows the bootstrap command for user approval before it runs. The command
installs the current GitHub package quietly, then prints the one absolute plugin
directory produced by `acco claude-plugin-path`.

The generated plugin owns only its own plugin directory and invokes ACCO
as `python -m acco.entry`. It includes:

- the normal PreToolUse/PostToolUse/SessionStart/UserPromptSubmit/Stop hooks;
- the local ACCO MCP server;
- `/acco:ingress <stage-id>` for resuming a safely staged oversized prompt.

For mixed-host projects, editable installs, or environments where you want
explicit project config management, continue to use pip + `acco setup`.

Supported automatic setup now covers:

| Host | Managed integration |
|---|---|
| **Claude Code** | project hooks + project `.mcp.json` |
| **Cursor** | project `.cursor/mcp.json` + `.cursor/hooks.json` native pre-tool/prompt/session hooks |
| **Codex** | marked ACCO block in `~/.codex/config.toml` |
| **OpenCode** | project `.opencode/opencode.json` using `mcp.servers` |
| **OpenClaw** | native `openclaw mcp set/unset` registry |
| **Hermes Agent** | marked entry under `mcp_servers` in `~/.hermes/config.yaml` |
| **GitHub Copilot** | native Copilot CLI MCP registry + owned `.github/hooks/acco.json`; VS Code workspace `.vscode/mcp.json` when present |
| **Google Antigravity** | workspace `.agents/mcp_config.json` using `mcpServers` |
| **Gemini CLI** | project `.gemini/settings.json` native hooks |
| **Qwen Code** | project `.qwen/settings.json` native hooks |

Only ACCO-owned entries are changed. Setup is idempotent, so rerunning it
after upgrades repairs/migrates managed entries without duplicating them. For
Claude it also installs the managed ACCO Lean skill when that path is absent or
still ACCO-owned; a user-modified skill is preserved.
`acco uninstall` reverses those entries while preserving unrelated host
configuration.

Use repeatable `--host` flags for explicit selection, for example:

```bash
acco setup . --host codex --host cursor --host opencode
acco setup . --host openclaw --host hermes
acco setup . --host copilot --host antigravity
acco setup . --host gemini --host qwen
acco setup . --host all
```

OpenClaw is mutated through its own validated MCP registry command rather than
by parsing JSON5 directly. Copilot CLI is likewise managed through `copilot mcp`
with a user-level `acco` entry that launches `acco serve .`; the
VS Code Copilot surface remains workspace-scoped in `.vscode/mcp.json`. OpenCode uses a strict-JSON project layer and fails
closed instead of creating a second sibling config when
`.opencode/opencode.jsonc` already exists. Hermes uses a clearly marked YAML
block and refuses to overwrite an unowned `acco` entry.

### Native hook interception

ACCO now uses one host-neutral `HookRuntime` behind native project hooks for
Claude Code, Cursor, Gemini CLI, Qwen Code, and Copilot CLI. The adapters
translate only event/tool/result schemas; output compression, exact recovery,
read guarding, prompt ingress, continuity, and efficiency policy remain
single-sourced.

The enforced capabilities intentionally differ by host:

| Host | Large Read / `cat` guard | Prompt ingress / lifecycle | Automatic successful tool-result replacement |
|---|---|---|---|
| Claude Code | yes | yes | Bash + eligible Read |
| Cursor | yes via `preToolUse` | prompt block + session/compact/stop | not for general built-in results; Cursor only documents replacement for MCP results |
| Gemini CLI | yes via `BeforeTool` | yes via `BeforeAgent` / session hooks | yes; `AfterTool` can hide the original and use ACCO's compact result as replacement |
| Qwen Code | yes via `PreToolUse` | yes via `UserPromptSubmit` / session hooks | not claimed; documented PostToolUse is used for context/decisions, not a general success-result rewrite |
| Copilot CLI | yes via `PreToolUse` | session/compact/stop; command prompt hooks cannot inject/modify the prompt | yes via `modifiedResult` |

For Gemini and Copilot, the replacement-capable post-tool adapter is deliberately
broader than shell output: textual Grep/WebFetch/WebSearch/MCP-style results can
flow through ACCO's generic/failure-aware output pipeline too. Read/Edit/Write
results are not treated as generic command output. Oversized accepted
transformations still receive the ordinary local `tsr_...` exact-recovery
handle.

Cursor's `beforeSubmitPrompt` can block an oversized prompt, so ACCO can enforce
lossless ingress staging there. It cannot inject ACCO's generation-policy text;
the adapter therefore disables that non-enforceable behavior instead of claiming
it reached the model. Copilot command `userPromptSubmitted` output is likewise
not used for ACCO prompt injection.

Native configuration is idempotent and ownership-safe. Cursor/Gemini/Qwen merge
only ACCO command entries into shared JSON. Copilot uses the dedicated
`.github/hooks/acco.json` path and refuses to overwrite a non-ACCO file at that
location. `acco uninstall` removes only those owned entries.

The files under `integrations/` remain manual fallback/reference templates.

The MCP process is local and uses newline-delimited JSON-RPC over stdio:

```bash
acco serve /absolute/path/to/project
```

The default `full` profile exposes repository context, ranking/impact,
semantic-index, patch review, output policy, model routing, and persistent-memory
tools. Persistent memory uses a progressive contract:

- `memory_index` — compact ids/claims/types/scores;
- `memory_search` — bounded snippets for relevance confirmation;
- `memory_get` — full records by selected id;
- `remember_memory` — typed evidence-backed project memory.

Existing `remember_finding`, `recall_findings`, and `knowledge_status`
remain supported.

For lower recurring tool-schema cost, set `[mcp] profile = "adaptive"` in
`.acco.toml` or export `ACCO_MCP_PROFILE=adaptive`. The initial
surface stays small and includes `discover_tools` plus exact
`recover_context`; a discovery call selects bounded specialist groups for the
current task, returns their exact schemas, and replaces the specialist portion
of subsequent `tools/list` responses.

Set `mcp.compress_schemas = true` to additionally remove annotation-only
schema metadata and shorten long descriptions conservatively. When compression
is beneficial, the exact original catalog is stored under a `tsr_...` recovery
handle. Set `profile = "full"` and/or `compress_schemas = false` as the
compatibility fallback for hosts with limited dynamic-tool support.

Call `refresh_index` after external file changes when a long-running server must
see the new source immediately. Context generation otherwise reuses the current
in-memory snapshot for predictable low latency.

The GitHub Actions example is intentionally a reporting/validation workflow. It
does not modify a pull request or publish benchmark claims.


## Provider base-URL integration

The provider proxy is separate from MCP/setup integration. `acco wrap` now
layers host-specific launch adapters over the same local reverse proxy:

- GitHub Copilot CLI uses its documented `COPILOT_PROVIDER_*` BYOK variables;
- OpenClaw direct `openai/*`, `anthropic/*`, and `google/*` API routes use
  an ephemeral sibling config overlay and leave the real config unchanged;
- Cursor starts a local proxy session and prints the documented OpenAI BYOK
  base-URL setting, because Cursor does not publish a stable machine-writable
  provider setting and ACCO will not edit private state.

Generic clients that honor standard provider base-URL environment variables can
still use `acco wrap COMMAND` directly. The lower-level proxy remains available:

```bash
acco provider-proxy . \
  --provider anthropic \
  --upstream https://api.anthropic.com
```

Point the client at the printed loopback URL using that client's supported
base-URL setting. ACCO does not rewrite host configuration to enable the
proxy automatically.

The proxy can combine recoverable tool-schema compression, large historical
tool-result compression, captured browser-context focusing, and stable-prefix
reuse accounting before the request reaches the configured upstream. Provider
responses are forwarded unchanged. Non-local plaintext upstreams, embedded URL
credentials, cross-origin absolute-form targets, and automatic redirect
following are refused by design.

Use:

```bash
acco prefix-status .
acco recovery-status .
```

to inspect content-free prefix evidence and recovery capacity. See
[Security & privacy](SECURITY.md) before enabling this network boundary.

## Claude Code output optimization

Install the hooks after installing or upgrading ACCO:

```bash
acco install /absolute/path/to/project --templates
```

For a user-wide hook installation:

```bash
acco install . --user
```

The Claude Code integration uses five distinct boundaries:

- `UserPromptSubmit` automatically selects and injects a generation-time output
  policy when the task/mode changes, so completion tokens can be avoided before
  they are generated;
- `PreToolUse` protects against unbounded large source reads and lone
  `cat <large-source>` dumps; when the opt-in Smart Tool Proxy is enabled,
  eligible large Reads are delegated to PostToolUse instead of denied;
- `PostToolUse` can reduce large Bash stdout through the failure-aware output
  processor registry, collapse exact repeated command output, and replace an
  eligible full-file Read with local/free-model-guided **exact source ranges**.
  Selector-generated prose is not forwarded; delivered code is re-read from
  the source file, and bounded Reads remain untouched for edit-grade bytes;
- `SessionStart` resume/compact can inject a bounded structured continuity
  checkpoint containing working files, redacted recent commands, and validation
  status without copying conversation text;
- `Stop` and `StopFailure` read the current turn's appended transcript usage
  counters and record content-free budget telemetry locally.

The prompt classifier is deterministic and conservative. Ambiguous follow-ups
inherit the current session policy without another full policy injection.
`clear`/compaction session events reset the remembered policy because the host
may have rebuilt context. User prompt text is not persisted by this feature. Adaptive budgeting changes
the token target only when a task/mode/new-task signal warrants recalculation;
vague follow-ups keep the current budget exactly. If a quality-gated calibration
artifact is present, its task/mode recommendation becomes the learned base.
Claude's documented per-turn `Stop` event supplies the transcript path used for
measurement; ACCO never persists the hook's `last_assistant_message`.

Inspect which processor would handle a command:

```bash
acco output-explain "pytest -q"
acco output-explain "npm install" --exit-code 1
```

Graph-aware diagnostic Delta is opt-in:

```bash
export ACCO_DELTA=1
```

It currently applies to supported repeated pytest and Ruff diagnostics within a
Claude Code session. See [OUTPUT_OPTIMIZATION.md](OUTPUT_OPTIMIZATION.md) for
failure routing, critical-line recovery, quality replay, Delta state, and graph
mapping details.


## Project configuration

Setup creates `.acco.toml`. The nearest file is discovered by walking
from the active project directory toward the filesystem root. Environment
variables override the TOML values for temporary/CI changes.

```toml
version = 1

[hooks]
guard = true
read_max_lines = 220
reread = false
delta = false
min_lines = 40
keep_tail = 15
allow = []

[output]
enabled = true
mode = "normal"
task = "auto"
adaptive = true
calibration_file = ".acco.output-calibration.json"
telemetry = true

[model_routing]
enabled = false
mode = "advisory"
current_model = ""
allowed_models = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"]
min_savings = 0.05
conservative = true
calibration_file = ".acco.routing-calibration.json"

[efficiency]
enabled = true
continuity = true
dedup = true
waste_detection = true

[ingress]
enabled = false
threshold_tokens = 12000
packet_tokens = 1600

[retrieval]
cache = true
cache_max_entries = 64

[mcp]
profile = "full"
adaptive_max_tools = 12
compress_schemas = false

[provider]
prefix_tracking = true

[tool_proxy]
enabled = false
provider = "ollama"
model = "qwen2.5-coder:7b"
endpoint = "http://127.0.0.1:11434"
min_tokens = 2500
target_tokens = 1800
model_input_tokens = 12000
timeout_seconds = 6.0
max_ranges = 4
max_range_lines = 80
```

Automatic generation-policy injection uses native prompt hooks where the host
can actually inject model context: Claude Code, Gemini CLI, and Qwen Code.
Cursor's prompt hook is used only for enforceable ingress blocking, and Copilot
CLI command prompt-hook output is not treated as injectable. Use
`acco client-capabilities --client HOST` for the exact guarantee level of each
runtime surface.

Automatic model routing is opt-in. When enabled, ACCO classifies the task,
derives a complexity/risk capability floor, then chooses the cheapest eligible
model from the freshness-gated pricing registry. Claude Code's prompt hook can
record and inject the decision but cannot replace the active top-level model.
Model-selectable orchestrators should call the MCP `route_task` tool and execute
its `selected_model` / `action` decision directly. The default capability
profiles are conservative product policy, not model-quality benchmark results.

A quality-gated calibration artifact may admit a cheaper model outside the
static capability profile for one exact bucket. Generate that artifact only
from paired arms that differ by model choice alone, after independent
verification and `blind-grade`:

```bash
acco experiment routing-suite.json --out routing-runs.json
acco blind-grade routing-runs.json
acco model-route-calibrate routing-runs.json
```

The runtime rechecks hard evidence floors before using any recommendation.
Invalid calibration falls back to the static conservative router.

## Troubleshooting and repair

```bash
acco doctor .
acco doctor . --json
acco setup .        # idempotent repair / upgrade migration
acco commands
```

For Claude Code, the existing lower-level `acco host-check` remains
available when you need transport/live-host evidence beyond the consolidated
configuration health report.
