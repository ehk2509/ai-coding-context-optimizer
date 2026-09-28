# Configuration

ACCO has two configuration layers:

1. the nearest project `.acco.toml`;
2. `ACCO_*` environment variables, which override project values.

Host integration files are managed separately by `acco setup`.

## Project config discovery

Starting from the active repository path, ACCO walks toward the
filesystem root and loads the nearest `.acco.toml`.

A default file created by `acco setup` is:

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
task_checklist = true
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
knowledge_read_avoidance = false
cache_economics = false
cache_expected_reuses = 2
cache_write_factor = 1.25
cache_read_factor = 0.10
cache_min_relative_savings = 0.05

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

[context_budget]
enabled = false
total_tokens = 12000

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

## Hook settings

| TOML key | Default | Meaning |
|---|---:|---|
| `hooks.guard` | `true` | Enable the large source Read/`cat` guard. |
| `hooks.read_max_lines` | `220` | Maximum unbounded source read before guarding. |
| `hooks.reread` | `false` | Block unchanged repeated full reads in a session. |
| `hooks.delta` | `false` | Enable graph-aware diagnostic Delta where supported. |
| `hooks.min_lines` | `40` | Minimum Bash output size before normal compression is considered. |
| `hooks.max_lines` | unset | Explicit retained-line cap; otherwise ACCO derives one. |
| `hooks.keep_tail` | `15` | Tail lines retained by output compaction. |
| `hooks.allow` | `[]` | Filename, absolute-path, or repository-relative guard globs. |
| `hooks.disabled` | `false` | Disable ACCO hook behavior without uninstalling it. |

## Generation output policy

Claude Code's `UserPromptSubmit` hook can automatically classify the current
task and inject the generation-time response policy before the model answers.
The classifier is deterministic and conservative: strong debugging/review/
coding/planning/explanation language selects a task class, while ambiguous
follow-ups inherit the current session class without another policy injection.

| TOML key | Default | Meaning |
|---|---:|---|
| `output.enabled` | `true` | Enable automatic generation-policy injection where the host supports prompt hooks. |
| `output.task_checklist` | `true` | When a prompt explicitly names another affected path or API ("also reproduces with `scatterplot`"), inject a short checklist of the named items to verify before finishing. Requires `output.enabled`. |
| `output.mode` | `"normal"` | Default response mode: `terse`, `normal`, or `detailed`. |
| `output.task` | `"auto"` | Task policy: `auto`, `general`, `coding`, `debugging`, `review`, `explanation`, or `planning`. |
| `output.adaptive` | `true` | Scale the task/mode base budget using deterministic prompt-complexity signals. |
| `output.min_tokens` | unset | Optional project floor for adaptive budgets, still bounded by the selected mode's safety range. |
| `output.max_tokens` | unset | Optional project ceiling for adaptive budgets, still bounded by the selected mode's safety range. |
| `output.calibration_file` | `".acco.output-calibration.json"` | Optional learned-budget artifact produced by `output-calibrate`; missing/invalid files fall back to built-in bases. |
| `output.telemetry` | `true` | Record local content-free turn usage at Claude `Stop`/`StopFailure` for budget-effectiveness reporting. |

The full policy is injected only when the resolved task/mode changes, on the
first prompt in a session, or after a clear/compact context reset. ACCO
stores only the resolved task, mode, and budget in local session state; it does
not persist the user prompt for this feature. Explicit requests such as
"keep it short" or "give a comprehensive explanation" override the configured
mode for the active task.

Adaptive budgets use only visible prompt structure: request length, multi-part
lists, code/diagnostic evidence, and broad repository/architecture scope. A
vague follow-up inherits the current budget exactly instead of being rescored.
Built-in mode safety bounds prevent unbounded expansion or collapse. When a
valid calibration artifact is present, its quality-verified task/mode budget
becomes the learned base before complexity scaling.

With telemetry enabled, the Claude prompt hook checkpoints only the transcript
byte offset and resolved policy metadata. The `Stop`/`StopFailure` hook then
reads only transcript bytes appended during that turn and stores usage counters
plus policy metadata under the private ACCO state directory. Prompt text,
assistant text, tool payloads, and transcript content are not copied into the
telemetry log. Disable temporarily with
`ACCO_OUTPUT_TELEMETRY=0`.

Example allowlist:

```toml
[hooks]
allow = ["generated/*", "*.gen.ts", "vendor/special.py"]
```

## Session efficiency

The efficiency layer is local, bounded, and independent from repository ranking.
It observes host hook events but never copies raw user prompts, assistant
responses, or tool output into its continuity snapshot.

| TOML key | Default | Meaning |
|---|---:|---|
| `efficiency.enabled` | `true` | Master switch for continuity, dedup evidence, and behavior tracking. |
| `efficiency.continuity` | `true` | Restore structured working-state orientation on Claude resume/compact events. |
| `efficiency.dedup` | `true` | Collapse exact repeated Bash output and block unchanged repeated full-file Reads. |
| `efficiency.waste_detection` | `true` | Surface bounded repeated-command, identical-failure retry-loop, and no-edit tool-cascade signals. |
| `efficiency.knowledge_read_avoidance` | `false` | Opt in to replacing full-file Reads with current verified findings anchored to that exact source file. Stale/non-verified findings never block reads. |
| `efficiency.cache_economics` | `false` | Require the cache-aware relative-cost policy to approve knowledge read avoidance. |
| `efficiency.cache_expected_reuses` | `2` | Expected later cache reads used by the relative-cost model. |
| `efficiency.cache_write_factor` | `1.25` | Relative cache-write input cost used for planning; override for the active provider/model. |
| `efficiency.cache_read_factor` | `0.10` | Relative cache-read input cost used for planning; override for the active provider/model. |
| `efficiency.cache_min_relative_savings` | `0.05` | Minimum projected lifetime input-cost reduction required when cache economics is enabled. |

Continuity stores only task class, working file paths, bounded redacted command
labels/fingerprints, validation outcomes, failure fingerprints, and counters.
Command labels apply best-effort credential redaction before persistence.
Compressed Bash output keeps the legacy paged-output store for compatibility and
also receives a universal `tsr_...` recovery handle when the hook replaces stdout.

`/clear` resets the active working checkpoint. `/compact` and resume retain
the structured working set but reset transient per-turn counters. Cross-turn
dedup never substitutes approximate output: it requires the same normalized
command and exact output digest.

Knowledge-assisted read avoidance is disabled by default while its frozen
end-to-end holdout remains unexecuted. When enabled, it only considers
`verified`, non-stale findings whose anchors match the exact requested file.
The replacement must save at least a bounded token floor; if cache economics is
also enabled it must additionally clear the configured projected-cost threshold.
The model can always request a bounded `Read` range when exact implementation
bytes are needed.

## MCP tool disclosure

The MCP server defaults to the backward-compatible `full` tool surface.
Projects can opt into smaller static profiles or deterministic per-task
disclosure:

| TOML key | Default | Meaning |
|---|---:|---|
| `mcp.profile` | `"full"` | Advertised tool profile: `minimal`, `context`, `memory`, `adaptive`, or `full`. |
| `mcp.adaptive_max_tools` | `12` | Maximum schemas selected by one adaptive discovery pass; the seven core tools are always retained. |
| `mcp.compress_schemas` | `false` | Compress selected MCP schema annotations/descriptions conservatively and store the exact original catalog in recovery. |

With `profile = "adaptive"`, the initial surface contains only
`discover_tools`, core repository context tools, `memory_index`,
`recover_context`, and `route_task`. Calling `discover_tools` with the current task returns the
selected specialist schemas and expands subsequent `tools/list` responses.
The protocol advertises MCP `listChanged=true` in this mode. Selection is
local and deterministic; it does not call an LLM.

Persistent memory itself remains explicit. `memory_index` is the cheap metadata
layer, `memory_search` adds bounded snippets, and `memory_get` returns full
records by id. No raw conversation text is automatically persisted.

## Whole-context budget

The whole-context allocator is opt-in. It plans one model-context envelope
across exact source, history, durable memory, historical tool results, tool
schemas, and uncommitted reserve.

| TOML key | Default | Meaning |
|---|---:|---|
| `context_budget.enabled` | `false` | Enable the planner for repository source packs and provider proxy transforms. |
| `context_budget.total_tokens` | `12000` | Total model-context envelope used to derive component slices; minimum 1000. |

Environment overrides:

- `ACCO_CONTEXT_BUDGET=1`
- `ACCO_CONTEXT_BUDGET_TOTAL_TOKENS=N`

When enabled, source retrieval uses only the plan's `source` slice, while any
explicit pack `max_tokens` remains an additional hard source ceiling. Provider
interception uses observed schema and historical tool-output demand to decide
whether those existing recoverable compressors should activate. It does not
automatically rewrite arbitrary conversation history or inject project memory.

Use `acco context-budget --total-tokens N` to inspect a plan before enabling
runtime use.

## Provider prefix evidence and local proxy

Provider-prefix tracking stores only a SHA-256 fingerprint, estimated size,
component labels, and hit/miss counters for the **post-transform** stable
request prefix. Raw provider request text is not copied into this state.

| TOML key | Default | Meaning |
|---|---:|---|
| `provider.prefix_tracking` | `true` | Keep content-free stable-prefix reuse counters when provider request transformation is active. |

The network-facing proxy itself is intentionally not auto-started from project
configuration. Start it explicitly with `acco provider-proxy
--upstream ...`. It binds to loopback by default, requires HTTPS for non-local
upstreams, forwards provider responses unchanged, and fails closed to the
original request whenever a lossy transform cannot store exact recovery bytes.

## Prompt ingress

Prompt ingress is a separate opt-in persistence boundary from the ordinary
output-policy hook.

| TOML key | Default | Meaning |
|---|---:|---|
| `ingress.enabled` | `false` | Block/stage prompts that exceed the threshold before Claude processes them. |
| `ingress.threshold_tokens` | `12000` | Offline-estimated prompt size at which staging activates. |
| `ingress.packet_tokens` | `1600` | Maximum target size for the bounded exact-excerpt stage packet. |

Claude Code's `UserPromptSubmit` hook cannot replace the prompt. ACCO
therefore blocks the oversized turn, stores the exact original locally with a
SHA-256 integrity digest, and asks for a small follow-up using the stage id.
There is no automatic prefix-only truncation fallback.

## Smart Tool Proxy

Smart Tool Proxy applies only to verified, unbounded repository source Reads.
It is disabled by default. With `provider = "ollama"`, a free/local model
selects relevant source ranges from a bounded structural/exact candidate packet.
ACCO validates those ranges and delivers exact source bytes from the
original file. If the model cannot be reached or returns unusable output,
deterministic selection is used instead.

| TOML key | Default | Meaning |
|---|---:|---|
| `tool_proxy.enabled` | `false` | Enable PostToolUse replacement for eligible large full-file source Reads. |
| `tool_proxy.provider` | `"ollama"` | Selector backend: `ollama` or `deterministic`. |
| `tool_proxy.model` | `"qwen2.5-coder:7b"` | Ollama model name used only for range/orientation selection. |
| `tool_proxy.endpoint` | `"http://127.0.0.1:11434"` | Ollama base URL. A non-loopback endpoint changes the privacy boundary. |
| `tool_proxy.min_tokens` | `2500` | Minimum estimated full-file size eligible for proxying. |
| `tool_proxy.target_tokens` | `1800` | Target upper size for the packet returned to Claude. |
| `tool_proxy.model_input_tokens` | `12000` | Maximum estimated candidate-evidence budget sent to the selector. |
| `tool_proxy.timeout_seconds` | `6.0` | Selector HTTP timeout before deterministic fallback. |
| `tool_proxy.max_ranges` | `4` | Maximum validated ranges selected for exact delivery. |
| `tool_proxy.max_range_lines` | `80` | Maximum lines in any selected range. |

Bounded Reads bypass this feature and remain the exact-byte path for edits and
verification. The current user task is read transiently from the Claude
transcript tail when available; it is not persisted by the proxy.

## Retrieval cache

| TOML key | Default | Meaning |
|---|---:|---|
| `retrieval.cache` | `true` | Reuse completed context packs only when repository content and all keyed retrieval evidence match. |
| `retrieval.cache_max_entries` | `64` | Maximum project-local cached packs retained before oldest-entry pruning. |

Cache keys include indexed source digests/index version, query/budget options,
changed and constrained file sets, feedback, and session working-set state.
Embedding reranking and custom ranking-stage registries bypass this cache version
because their external identities are not yet included in the key.

The optional Rust extension has no TOML switch because fallback is automatic.
Set `ACCO_RUST_FASTPATH=0` to force Python for diagnosis/parity checks.

## Environment overrides

Environment variables take precedence over TOML:

| Variable | Project equivalent |
|---|---|
| `ACCO_DISABLED` | `hooks.disabled` |
| `ACCO_GUARD` | `hooks.guard` |
| `ACCO_READ_MAX_LINES` | `hooks.read_max_lines` |
| `ACCO_REREAD` | `hooks.reread` |
| `ACCO_ALLOW` | `hooks.allow` (colon-separated) |
| `ACCO_DELTA` | `hooks.delta` |
| `ACCO_MIN_LINES` | `hooks.min_lines` |
| `ACCO_MAX_LINES` | `hooks.max_lines` |
| `ACCO_KEEP_TAIL` | `hooks.keep_tail` |
| `ACCO_OUTPUT_POLICY` | `output.enabled` |
| `ACCO_TASK_CHECKLIST` | `output.task_checklist` |
| `ACCO_OUTPUT_MODE` | `output.mode` |
| `ACCO_OUTPUT_TASK` | `output.task` |
| `ACCO_OUTPUT_ADAPTIVE` | `output.adaptive` |
| `ACCO_OUTPUT_MIN_TOKENS` | `output.min_tokens` |
| `ACCO_OUTPUT_MAX_TOKENS` | `output.max_tokens` |
| `ACCO_OUTPUT_CALIBRATION_FILE` | `output.calibration_file` |
| `ACCO_OUTPUT_TELEMETRY` | `output.telemetry` |
| `ACCO_MODEL_ROUTING` | `model_routing.enabled` |
| `ACCO_MODEL_ROUTING_MODE` | `model_routing.mode` |
| `ACCO_MODEL_ROUTING_CURRENT_MODEL` | `model_routing.current_model` |
| `ACCO_MODEL_ROUTING_ALLOWED` | `model_routing.allowed_models` (colon-separated) |
| `ACCO_MODEL_ROUTING_MIN_SAVINGS` | `model_routing.min_savings` |
| `ACCO_MODEL_ROUTING_CONSERVATIVE` | `model_routing.conservative` |
| `ACCO_MODEL_ROUTING_CALIBRATION_FILE` | `model_routing.calibration_file` |
| `ACCO_EFFICIENCY` | `efficiency.enabled` |
| `ACCO_CONTINUITY` | `efficiency.continuity` |
| `ACCO_CROSS_TURN_DEDUP` | `efficiency.dedup` |
| `ACCO_WASTE_DETECTION` | `efficiency.waste_detection` |
| `ACCO_KNOWLEDGE_READ_AVOIDANCE` | `efficiency.knowledge_read_avoidance` |
| `ACCO_CACHE_ECONOMICS` | `efficiency.cache_economics` |
| `ACCO_CACHE_EXPECTED_REUSES` | `efficiency.cache_expected_reuses` |
| `ACCO_CACHE_WRITE_FACTOR` | `efficiency.cache_write_factor` |
| `ACCO_CACHE_READ_FACTOR` | `efficiency.cache_read_factor` |
| `ACCO_CACHE_MIN_RELATIVE_SAVINGS` | `efficiency.cache_min_relative_savings` |
| `ACCO_INGRESS_OPTIMIZER` | `ingress.enabled` |
| `ACCO_INGRESS_THRESHOLD_TOKENS` | `ingress.threshold_tokens` |
| `ACCO_INGRESS_PACKET_TOKENS` | `ingress.packet_tokens` |
| `ACCO_RETRIEVAL_CACHE` | `retrieval.cache` |
| `ACCO_RETRIEVAL_CACHE_MAX_ENTRIES` | `retrieval.cache_max_entries` |
| `ACCO_MCP_PROFILE` | `mcp.profile` |
| `ACCO_MCP_ADAPTIVE_MAX_TOOLS` | `mcp.adaptive_max_tools` |
| `ACCO_MCP_COMPRESS_SCHEMAS` | `mcp.compress_schemas` |
| `ACCO_PREFIX_TRACKING` | `provider.prefix_tracking` |
| `ACCO_TOOL_PROXY` | `tool_proxy.enabled` |
| `ACCO_TOOL_PROXY_PROVIDER` | `tool_proxy.provider` |
| `ACCO_TOOL_PROXY_MODEL` | `tool_proxy.model` |
| `ACCO_TOOL_PROXY_ENDPOINT` | `tool_proxy.endpoint` |
| `ACCO_TOOL_PROXY_MIN_TOKENS` | `tool_proxy.min_tokens` |
| `ACCO_TOOL_PROXY_TARGET_TOKENS` | `tool_proxy.target_tokens` |
| `ACCO_TOOL_PROXY_MODEL_INPUT_TOKENS` | `tool_proxy.model_input_tokens` |
| `ACCO_TOOL_PROXY_TIMEOUT_SECONDS` | `tool_proxy.timeout_seconds` |
| `ACCO_TOOL_PROXY_MAX_RANGES` | `tool_proxy.max_ranges` |
| `ACCO_TOOL_PROXY_MAX_RANGE_LINES` | `tool_proxy.max_range_lines` |
| `ACCO_RUST_FASTPATH` | native acceleration override (no TOML equivalent) |

Boolean overrides accept `1/true/yes/on`; other values resolve to false.

Example temporary override:

```bash
ACCO_DELTA=1 ACCO_READ_MAX_LINES=150 claude

# Disable automatic generation-policy injection temporarily:
ACCO_OUTPUT_POLICY=0 claude

# Force a fixed terse review policy instead of auto-classification:
ACCO_OUTPUT_MODE=terse ACCO_OUTPUT_TASK=review claude
```

## Managed host files

### Claude Code

Setup manages:

- `.claude/settings.json`: only hook commands equal to `acco hook`;
- `.mcp.json`: only `mcpServers.acco`;
- `.claude/skills/token-budget/SKILL.md`: generated template.

Uninstall removes the generated skill only if it is still byte-identical to the
ACCO template. A user-edited skill is preserved.

### Cursor

Setup manages:

```text
.cursor/mcp.json   → mcpServers.acco
.cursor/hooks.json → only commands prefixed with "acco hook --host cursor --event "
```

Other MCP servers and user hook entries remain untouched.

### Gemini CLI

Setup merges only ACCO command hooks into:

```text
.gemini/settings.json → hooks.*
```

Unrelated Gemini settings and hooks are preserved.

### Qwen Code

Setup merges only ACCO command hooks into:

```text
.qwen/settings.json → hooks.*
```

Unrelated Qwen settings and hooks are preserved.

### GitHub Copilot CLI

When the Copilot CLI surface is detected, setup creates the dedicated repository
hook file:

```text
.github/hooks/acco.json
```

ACCO owns that whole file and refuses to overwrite it if the path already
contains a non-ACCO hook document. Existing Copilot MCP setup remains managed
through the host's native MCP registry; the VS Code workspace MCP surface remains
`.vscode/mcp.json`.

### Codex

Setup manages only the block between:

```toml
# >>> acco managed >>>
...
# <<< acco managed <<<
```

If an unmanaged `[mcp_servers.acco]` already exists, setup refuses to
overwrite it.

## Mutation safety

For multi-host setup, ACCO preflights every selected managed file before
the first write. Invalid JSON or a conflicting Codex block therefore fails
before any earlier host is partially configured.

All JSON writes are atomic.

## Semantic model revision

Semantic retrieval loads local SentenceTransformer weights only. By default,
the configured model name identifies the semantic vector store. For a
reproducible benchmark or a deployment that pins model weights, also set:

```bash
export ACCO_SEMANTIC_MODEL_REVISION=<immutable-model-revision>
```

The revision is passed to SentenceTransformers and is included in the semantic
SQLite path, persisted metadata, and exact-query vector cache key. Changing the
revision therefore creates separate semantic state instead of reusing vectors
from another set of weights.

This is an environment-only expert/reproducibility control; ordinary project
configuration does not need to pin a model revision.

## State and saved output

Session state defaults to:

```text
~/.claude/acco/
```

Override it with:

```bash
export ACCO_STATE_DIR=/another/private/path
```

Saved original command output is local and can be paged with `acco
output` or pruned with `acco outputs-prune`. New lossy optimization
surfaces also use the project-scoped content-addressed recovery store and emit
`tsr_...` handles recoverable with `acco recover` or MCP
`recover_context`. The recovery store refuses new transforms rather than
evicting old source when its hard capacity would be exceeded.

See [Security & privacy](../SECURITY.md) for persistence boundaries.

## Model routing

Automatic model routing is opt-in:

```toml
[model_routing]
enabled = true
mode = "advisory" # advisory | observe
current_model = "" # optional exact model id when the host does not supply one
allowed_models = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"]
min_savings = 0.05
conservative = true
calibration_file = ".acco.routing-calibration.json"
```

Environment overrides:

- `ACCO_MODEL_ROUTING`
- `ACCO_MODEL_ROUTING_MODE`
- `ACCO_MODEL_ROUTING_CURRENT_MODEL`
- `ACCO_MODEL_ROUTING_ALLOWED` (colon-separated exact model ids)
- `ACCO_MODEL_ROUTING_MIN_SAVINGS`
- `ACCO_MODEL_ROUTING_CONSERVATIVE`
- `ACCO_MODEL_ROUTING_CALIBRATION_FILE`

`observe` computes/stores decisions without prompt injection. `advisory`
also injects a bounded host-neutral recommendation. The Claude prompt hook
cannot change the active top-level model; use MCP `route_task` from an
orchestrator that can actually select a model.



Routing calibration can only make policy more aggressive when a generated
artifact passes the runtime safety floors. Create it from a frozen paired
experiment with identical arm configuration except model choice, independent
post-agent verification, and complete blind A/B quality grading:

```bash
acco experiment routing-suite.json --out routing-runs.json
acco blind-grade routing-runs.json
acco model-route-calibrate routing-runs.json
```

Accepted recommendations are exact-bucket exceptions, not global model
downgrades. A missing, malformed, or below-floor artifact falls back to the
static conservative router.
