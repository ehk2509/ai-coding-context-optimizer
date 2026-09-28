# ACCO — AI Coding Context Optimizer 1.23.0

**ACCO (AI Coding Context Optimizer)** is a local context-optimization layer for AI coding agents. It reduces unnecessary source, tool-output, and always-on context while preserving exact code where the model needs it.

The project is deliberately conservative: **smaller context is useful only when the task still succeeds**. ACCO does not claim a universal percentage reduction in task cost. It measures input size, preserves diagnostics, and keeps omitted command output recoverable.

## What's new in 1.23.0

ACCO 1.23 closes two major context-efficiency gaps while keeping its
retrieval-first design:

- **Out-of-context programmable execution.** Agents can run bounded local
  analysis over explicit repository text files and return only a small JSON
  result instead of loading large logs, JSON, reports, or fixtures into model
  context. The same implementation is available through MCP, Python, the
  loopback SDK bridge, TypeScript, and standalone binaries. Oversized computed
  results remain exactly recoverable through `tsr_...` handles.
- **Native coding-host interception.** The shared `HookRuntime` now powers
  native project hooks for Codex, Cursor, Gemini CLI, Qwen Code, and Copilot
  CLI in addition to Claude Code. ACCO advertises only what each host can
  actually enforce; Codex interception remains conditional on the host's
  project-hook trust boundary.
- **Stronger completion discipline.** A prompt-derived task checklist protects
  focused verification from stopping after only the first API/path named in a
  multi-path issue.
- **Broader end-to-end evidence.** A 144-run paired SWE-bench development study
  measured fewer model calls/tokens and lower equivalent cost per solved task,
  but ACCO withholds a general savings claim because the suite was adapted
  rather than frozen and ACCO solved 55/72 runs versus 56/72 for plain Claude
  Code.

The release still makes no universal token, API-cost, or cost-per-success claim;
see [Validation evidence](VALIDATION.md) and
[Benchmarking methodology](BENCHMARKING.md).

## Install

### Fast path

For any supported coding agent, install ACCO as an isolated CLI and let one
command detect, configure, index, and verify the current project:

```bash
uv tool install acco
cd /path/to/project
acco setup
acco start
```

For a genuine one-command bootstrap from a machine that already has `uv`:

```bash
cd /path/to/project
uvx acco bootstrap
```

`bootstrap` first installs ACCO persistently with `uv tool` (or `pipx`),
then performs the normal safe project setup, so host integrations never depend
on an ephemeral `uvx` environment.

Running bare `acco` shows a project-aware home screen; `acco status` shows
health/savings evidence; `acco advanced` keeps the full expert command surface
available without crowding onboarding.

### Claude Code marketplace

The repository also exposes a Claude-only marketplace:

```text
/plugin marketplace add ehk2509/ai-coding-context-optimizer
/plugin install acco@acco-tools
```

Claude shows the command-source bootstrap for approval before running it. The
command-source marketplace path requires Claude Code **2.1.229+**. Older Claude
Code versions can use the pip + setup path below. The generated plugin calls
`python -m acco.entry`, so it does not depend on the `acco`
console script being on `PATH`.

For environments without `uv`, `pipx install acco` is the next preferred
isolated install, with `python -m pip install --upgrade acco` retained as the
compatibility path. Tagged releases also publish smoke-tested standalone executables for x86_64
and ARM64 on Linux, macOS, and Windows, with SHA-256 sidecars, GitHub build
provenance, release-scoped Homebrew/WinGet metadata, and optional native
code-signing/notarization when publisher credentials are configured; see
[Installation options](docs/INSTALL.md).

`setup` now auto-detects supported coding-agent hosts, writes only ACCO-owned
integration entries, installs the safe local profile, adds Claude Lean when it
can do so without overwriting user content, warms the structural repository
index, and runs its own readiness check. Native project hooks are installed for
Claude Code, Codex, Cursor, Gemini CLI, Qwen Code, and Copilot CLI where their public
hook contracts support enforceable interception. It is safe to rerun after
upgrades as a repair/migration step. Configure hosts explicitly when needed:

```bash
acco setup . --host claude --host cursor
acco setup . --host codex
acco setup . --host gemini --host qwen
acco setup . --host copilot
acco setup . --host all

# Optional: keep provider interception active across future Claude/Codex sessions.
acco proxy install . --host claude --host codex
acco proxy status .
```

`doctor` consolidates CLI, project-config, host-integration, repository-index,
and available Claude transcript evidence in one health report. Remove only
ACCO-owned entries with:

```bash
acco uninstall . --host all
acco uninstall . --host all --remove-config
```

The ordinary product flow is intentionally small:

```bash
acco
acco bootstrap
acco setup
acco start
acco status
acco demo
acco savings
acco update
```

Discover the complete expert surface and enable shell completion with:

```bash
acco advanced
acco commands
acco completion bash
acco completion zsh
acco completion fish
acco completion powershell
```

The distribution, command, and Python import now use the ACCO identity:

| | Name |
|---|---|
| Install | `acco` |
| Command | `acco` |
| Import | `acco` |

This is an independent project and is not affiliated with or endorsed by
Anthropic.

## Documentation

Start with the task-oriented docs instead of searching this README:

- [Installation options](docs/INSTALL.md)
- [Native release signing and package publication](docs/RELEASE_SIGNING.md)
- [1-minute quickstart](docs/QUICKSTART.md)
- [Worked end-to-end example](docs/WORKED_EXAMPLE.md)
- [CLI reference](docs/CLI_REFERENCE.md)
- [Machine-readable CLI contracts](docs/JSON_OUTPUTS.md)
- [Middleware SDKs for custom agents](docs/SDK.md)
- [Everyday efficiency surfaces](docs/EVERYDAY_EFFICIENCY.md)
- [Configuration reference](docs/CONFIGURATION.md)
- [Coding-agent integrations](INTEGRATIONS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Upgrading and migration](docs/UPGRADING.md)
- [Architecture](ARCHITECTURE.md)
- [Benchmarking methodology](BENCHMARKING.md)
- [Validation evidence](VALIDATION.md)
- [Security and privacy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

The complete documentation map is [docs/README.md](docs/README.md).

## Everyday efficiency surfaces

ACCO now exposes six low-friction surfaces around the retrieval core:

```bash
acco guardian .
acco wrap claude
acco wrap aider -- --model gpt-4.1
OPENAI_API_KEY=... acco wrap opencode
COPILOT_PROVIDER_TYPE=anthropic COPILOT_MODEL=claude-sonnet-5 acco wrap copilot
acco wrap cursor --provider openai
OPENAI_API_KEY=... acco wrap openclaw
acco proxy install . --host claude --host codex
acco lean-skill . --install --host all
acco context-audit .
acco statusline .
```

Claude integrations capture a bounded structured checkpoint before compaction,
`wrap` can launch Claude/Codex/Gemini or infer the provider for arbitrary provider-aware CLIs through the loopback provider boundary,
Persistent proxy profiles can auto-start at user login and attach Claude/Codex
without requiring acco wrap on each launch. Copilot CLI has a documented BYOK-env adapter, OpenClaw direct API routes use
a temporary config overlay, and Cursor uses a safe manual BYOK bridge rather
than undocumented private-state edits. The portable Lean skill constrains final prose without reducing verification,
unknown tool outputs can fall back to payload-aware JSON/diff/log/table
processors, the context auditor covers cross-host instruction bloat, and the
status line surfaces local efficiency signals continuously. See
[Everyday efficiency surfaces](docs/EVERYDAY_EFFICIENCY.md).

Native hook adapters now make a second layer automatic. Codex/Cursor/Gemini/
Qwen/Copilot project hooks reuse the same host-neutral runtime as Claude rather
than duplicating compression policy. Copilot and Gemini provide direct successful
result-replacement fields; trusted Codex project hooks use the documented
PostToolUse continue/additional-context path to suppress large local Bash/MCP
results and deliver ACCO's compact recoverable representation. Cursor and Qwen
remain limited to the controls their public hook contracts actually expose.
See [Coding-agent integrations](INTEGRATIONS.md).

These mechanisms remain independently measurable. Operational token estimates
are not presented as a universal API-cost or cost-per-success claim.

## Embed ACCO in custom agents

ACCO's optimization engine is available outside coding CLIs.

Python agents can call the engine directly:

```python
from acco.sdk import AccoEngine

acco = AccoEngine(".")
middleware = acco.middleware("anthropic")

prepared = middleware.before_request(request_body)
tool = middleware.after_tool_result(
    raw_tool_output,
    query=user_prompt,
    command="pytest -q",
)
browser = middleware.after_browser_result(
    raw_browser_snapshot,
    query=user_prompt,
)
```

TypeScript/JavaScript agents use the typed, dependency-free client in
`sdk/typescript` against the same Python engine:

```bash
acco sdk-serve .
```

```ts
import { AccoClient } from "@acco-ai/sdk";

const middleware = new AccoClient().middleware("anthropic");
const prepared = await middleware.beforeRequest(requestBody);
```

Both SDKs share the production provider transform, context router,
command-output processors, deterministic model routing, and content-addressed
exact recovery. The TypeScript path deliberately does not duplicate those
algorithms in JavaScript.

Optional structured-data adapters reuse that same engine without changing the
coding-first product flow:

```python
rag = acco.rag().optimize(retrieved_documents, query=user_prompt)
api = acco.api().optimize(api_json, query=user_prompt)
rows = acco.database().optimize(
    database_rows,
    columns=["id", "name", "status"],
    query=user_prompt,
)
```

### Out-of-context programmable execution

For large repository-local logs, JSON, generated reports, fixtures, or other
text data, ACCO can compute over the bytes **without putting those bytes into the
model context**:

```python
analysis = acco.execute(
    """
lines = data["artifacts/test.log"].splitlines()
result = {
    "total": len(lines),
    "errors": sum("ERROR" in line for line in lines),
}
""",
    ["artifacts/test.log"],
)
```

The same primitive is MCP tool `execute` (typically rendered by clients as
`mcp__acco__execute`) and TypeScript `AccoClient.execute(...)`. Adaptive MCP
disclosure reveals it for data-heavy analysis tasks rather than adding its
schema to the default core.

Execution uses a restricted Python subprocess with explicit repository-contained
text inputs, no imports, no shell/process API, no arbitrary filesystem access,
no private/dunder traversal, hard input/time/result bounds, and JSON-only
results. Oversized computed results receive a `tsr_...` handle so the exact
result remains recoverable instead of being silently truncated. This is a
defensive local execution boundary, not a hardened container for hostile code;
see [Security & privacy](SECURITY.md).

These adapters operate only on caller-supplied data already in memory: they do
not retrieve documents, fetch APIs, open databases, or execute SQL. See
[Middleware SDKs](docs/SDK.md).

## Cost intelligence and efficiency advisor

Turn local ACCO evidence into a practical optimization report:

```bash
acco cost-advisor .
acco cost-advisor . --project-only --json
acco learn . --days 30
acco trial . --prompt-file task.md --verify "pytest -q"
acco pricing --model claude-sonnet-5
acco model-route "Debug this failing authentication handler" --json
acco cost-advisor . \
  --rates benchmarks/claude-sonnet-5-rates-2026-09-19.json
```

The advisor scores only categories with enough evidence and reports score
coverage separately. It combines measured always-on context, Claude transcript
usage/cache counters, output-budget fit, continuity/waste signals, and observed
before/after tool-context reductions. `acco learn` turns historical project
sessions into a ranked list of evidence-backed token/context opportunities,
while `acco trial` runs a history-isolated baseline-vs-ACCO comparison on
committed `HEAD` and requires an independent post-agent verifier. Local trial
deltas remain workload evidence, not a general savings claim.

Automatic model-routing intelligence is available through the CLI, MCP
`route_task`, and the opt-in Claude prompt hook. Routing first applies a
deterministic task/complexity/risk capability floor, then selects the cheapest
eligible profiled model from the fresh built-in pricing registry. Claude's hook
can advise and measure the decision; model-selectable orchestrators can execute
it directly through MCP. The built-in capability profiles are conservative
product policy, not a benchmark ranking of model quality.

Routing can become more aggressive only through a generated quality-gated
calibration artifact. Calibrate a cheaper arm against the current static-policy
model on frozen paired tasks, keep all non-model arm settings identical, verify
task success independently, blind-grade the final responses, then run:

```bash
acco model-route-calibrate routing-runs.json
```

The default gate requires at least 10 pairs across 5 tasks, at least 80%
baseline success, zero lost baseline successes, blind correctness/safety/
weighted-quality parity within 0.10 points, and transcript-confirmed actual
models. Accepted evidence relaxes only the exact task/complexity/risk bucket.

Pricing is deliberately explicit: dollar usage is calculated only from an
explicit exact-model rates source. Pass `--rates builtin` to use ACCO's
source-attributed, freshness-gated packaged registry, or supply a frozen JSON
rate file for reproducible historical evidence. Mixed-model turns, missing model prices,
or unknown cache-write TTLs stay visibly unpriced instead of being allocated by
assumption. Estimated tool-context savings may be shown under a clearly labeled
fresh-input-once scenario, but are **not** presented as measured API savings or
cost-per-success evidence.

## Adaptive whole-context budgets

ACCO can optionally plan the **entire model-context envelope**, not only the
source pack:

```bash
acco context-budget "Debug the failing auth handler" --total-tokens 12000

# Apply the derived source slice to repository retrieval.
acco pack . --query "Debug the failing auth handler" \
  --max-tokens 9000 \
  --context-budget 12000
```

The deterministic plan allocates tokens across exact source, prior history,
durable project memory, historical tool results, tool schemas, and reserve.
Existing behavior remains the default; projects opt in with
`[context_budget] enabled = true`.

Repository packing enforces the exact-source slice. Provider interception uses
the schema/tool-result slices to decide when its existing recoverable
compressors should activate. History and memory slices are exposed to custom
agents through the Python/TypeScript SDK rather than being silently rewritten.
See [context-budget](docs/commands/context-budget.md).

## Safe oversized-prompt ingress

Claude Code's `UserPromptSubmit` hook can block a prompt or add context, but
cannot replace the submitted text. ACCO therefore does **not** claim to
rewrite a huge prompt before the model.

Instead, an explicit opt-in can stage very large prompts losslessly:

```toml
[ingress]
enabled = true
threshold_tokens = 12000
packet_tokens = 1600
```

When the threshold fires, ACCO stores the exact prompt locally with a
SHA-256 integrity digest and returns a blocking stage id before Claude processes
the prompt. Resume with the generated plugin skill:

```text
/acco:ingress STAGE_ID
```

or manually:

```bash
acco ingress-show STAGE_ID --path .
acco ingress-read STAGE_ID --path . --start-line 80 --end-line 140
```

The packet contains exact bounded head/tail excerpts plus explicit omitted line
ranges. **There is no silent first-N-words truncation fallback.**

## Smart Tool Proxy for large Reads

Claude Code can opt in to routing large unbounded source Reads through ACCO
before the result reaches Claude:

```toml
[tool_proxy]
enabled = true
provider = "ollama"
model = "qwen2.5-coder:7b"
endpoint = "http://127.0.0.1:11434"
min_tokens = 2500
target_tokens = 1800
```

The free/local model is a **range selector, not a source of truth**. ACCO
builds bounded structural/exact candidate evidence, asks the selector which
ranges matter for the current task, validates those ranges, then rehydrates the
delivered excerpts from the real file bytes. Selector prose is explicitly
marked non-authoritative. If Ollama is unavailable, times out, or returns invalid
JSON, ACCO falls back to deterministic structural/lexical range
selection.

```text
Claude Read(large source)
        ↓
PreToolUse delegates eligible read
        ↓
local Ollama selector (optional)
        ↓
validated line ranges
        ↓
exact excerpts from original source
        ↓
PostToolUse updatedToolOutput
        ↓
Claude receives bounded evidence
```

Bounded Reads remain untouched and are the exact-byte recovery path for edits.
The feature is disabled by default; no source is sent to a model unless it is
explicitly enabled. See [Configuration](docs/CONFIGURATION.md) and
[Security & privacy](SECURITY.md).

## Multi-repository workspaces

ACCO can federate retrieval across related repositories without merging them
into one giant index:

```bash
acco workspace init ~/projects/product \
  --repo frontend=~/projects/frontend \
  --repo backend=~/projects/backend \
  --repo shared=~/projects/shared

acco workspace pack ~/projects/product \
  --query "change the shared authentication response" \
  --max-tokens 10000
```

Each repository keeps its normal structural/semantic index and exact-source
ranking authority. The workspace layer scores repositories for the task,
reserves a bounded slot for direct package dependencies, allocates one global
token budget, and emits repository-prefixed provenance. See
[Multi-repository workspaces](docs/commands/workspace.md).

## Hybrid semantic retrieval

ACCO 1.10 adds opt-in **chunk-level semantic discovery** without turning
semantic summaries into edit context. Enable it with either spelling:

```bash
acco pack . --query "where do stale sessions get rejected?" --semantic
acco pack . --query "where do stale sessions get rejected?" --embeddings
```

The flow is:

```text
versioned structural index
        ↓
symbol-aware chunks + overlapping fallback windows
        ↓
persistent local vectors
        ↓
exact cosine or optional HNSW
        ↓
multi-hit semantic file ranking
        ↓
bounded semantic → graph/peer/artifact expansion
        ↓
pre-semantic confidence gate
        ↓
existing exact-source symbol/window selector
        ↓
live exact source bytes
```

Install the one-step semantic extra, then explicitly download the local model
once:

```bash
pip install 'acco[semantic]'
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
acco semantic-index .
acco semantic-status .
```

At ACCO runtime the model loader uses `local_files_only=True`; semantic
retrieval does not silently fetch a model from the network. For reproducible
evaluation or controlled deployments, set
`ACCO_SEMANTIC_MODEL_REVISION=<immutable-model-revision>`. The revision
participates in vector-store and cached-query identity, so different model
weights cannot silently share semantic state. The SQLite index
stores vectors plus repository-relative path/line/symbol coordinates, **not
source text**. If `hnswlib` is unavailable the same vectors use exact cosine
scan instead of changing retrieval semantics.

Semantic retrieval is a discovery layer, not the authority layer. ACCO snapshots
pre-semantic evidence before embeddings run: undiscounted parser/provider
authority, implementation-vs-low-value source class, graph corroboration,
direct path-or-symbol identity, and lexical presence. Raw semantic boosts remain
independent of lexical rank so genuinely weak-overlap candidates can still be
found.

After direct semantic and bounded graph/peer/artifact expansion, a monotonic
confidence gate prevents semantic evidence from jumping over an equally direct
or stronger pre-semantic predecessor. Pure topical candidates can still reorder
freely. This specifically keeps source-quality and exact structural evidence
from being undone by a later embedding boost without introducing
repository-specific rules or a similarity threshold. Ranking explanations
record any clamp as `semantic-confidence-gate:...`. Within a retained file,
parser-backed exact symbol windows are also rendered before semantic ranges, so
a tight per-file budget clips embedding evidence before structural source.

## Persistent retrieval cache and optional Rust fastpath

Application-level context building now caches completed packs across processes
when the repository content fingerprint and retrieval configuration are
identical. Source digests, index version, changed-file state, ranking feedback,
working-set state, and budget/query settings are part of cache identity.
Embeddings/custom ranking plugins bypass caching until their external state can
be fingerprinted safely.

```toml
[retrieval]
cache = true
cache_max_entries = 64
```

ACCO also has a separately buildable optional PyO3 accelerator under
`rust/acco_fast`. Python remains the reference implementation and
automatic fallback. Inspect the active backend with:

```bash
acco fastpath-status
```

CI builds the Rust wheel and reruns pack/retrieval/context-quality checks with
the native backend required before accepting fastpath changes.

The normal `acco` wheel remains pure Python. To try the optional
native accelerator from a source checkout:

```bash
python -m pip install maturin
python -m pip install ./rust/acco_fast
acco fastpath-status
```

If the extension is absent or fails to import, ACCO automatically uses
the Python reference implementation.

## Failure-aware tool output and diagnostic Delta

Bash output now goes through a pluggable processor registry rather than one
monolithic filter. Format-specific processors currently cover pytest, Jest/Vitest,
`git log`, and npm/pnpm/yarn/bun installs, with a conservative generic fallback.
A processor must explicitly opt into failed-command handling; unknown failures
pass through unchanged. After every processor, a shared critical-line recovery
pass restores omitted error/location lines, and a ratio gate rejects marginal or
larger rewrites.

Inspect routing without running a command:

```bash
acco output-explain "pytest -q"
acco output-explain "npm install" --exit-code 1
```

Replay captured output against explicit preservation and savings contracts:

```bash
acco output-replay benchmarks/output-quality.example.json
```

Each case can require exact diagnostic strings, a maximum output-token budget,
and a minimum reduction. A failed contract exits non-zero, so the same fixtures
can guard CI.

Repeated pytest and Ruff diagnostics can optionally use **graph-aware Delta**:

```bash
export ACCO_DELTA=1
```

See [OUTPUT_OPTIMIZATION.md](OUTPUT_OPTIMIZATION.md) for the processor contract,
failure-routing rules, critical-line recovery, replay manifest schema, Delta
state model, and graph-enrichment behavior.

Within one Claude Code session, subsequent runs classify diagnostics as
`NEW`, `CHANGED`, `UNCHANGED`, or `RESOLVED`. New and changed diagnostics
are mapped through ACCO's repository index to the containing symbol and
nearby dependency/call-graph edges. Only bounded structured diagnostics are
stored in session state; raw command output is not persisted by Delta. Delta
replaces the normal compressed output only when the rendered delta is smaller.

## Frozen session-efficiency holdout

Version 1.8 adds a dedicated causal benchmark for the 1.7 session layer. It
reuses the already-frozen **24 SWE-bench Verified tasks × 3 trials** but compares
two condition profiles of the **same current ACCO binary**:

```text
v1.6 session-behavior baseline
  ACCO installed
  continuity=off
  cross-turn dedup=off
  waste detection=off

v1.7 session-efficiency treatment
  ACCO installed
  continuity=on
  cross-turn dedup=on
  waste detection=on
```

This isolates the session-efficiency bundle from unrelated 1.7 changes such as
new output processors. It is a behavioral baseline, **not** execution of the
historical 1.6 package.

Each arm is deliberately split into two fresh Claude sessions: an
investigation-only phase, then a real `SessionStart:resume` boundary, then a
fresh implementation phase. The control gets no continuity context; the
treatment can receive the structured checkpoint. The benchmark independently
derives tool calls, repeated commands, identical-failure retries, duplicate
Reads, and token usage from raw transcripts. ACCO's own efficiency events
are used only to prove which mechanisms activated.

Run/resume locally:

```bash
acco session-holdout \
  benchmarks/session-efficiency-swebench-24.frozen.json \
  --out session-holdout-runs.json \
  --require-publishable
```

Evaluate already merged/blind-graded evidence without rerunning agents:

```bash
acco session-holdout-evaluate session-holdout-runs.json \
  --rates benchmarks/claude-sonnet-5-rates-2026-09-19.json \
  --json --require-publishable
```

The frozen publication gate requires ≥20 tasks, ≥3 trials/task, isolated arm
profiles, independent task success, blind response-quality parity, no manual
intervention, complete cache-TTL-aware cost evidence, zero session-efficiency
events in the control, one forced continuity restore per treatment run, and
observed dedup + continuity + waste signals somewhere in the treatment. A
cost-per-success claim additionally requires a positive point estimate and a
task-cluster 95% confidence interval whose lower bound is above zero.

The checked-in paid workflow represents **144 arm-runs / 288 Claude task
phases**, plus blind grading. It is manual/explicitly confirmed. No session-
efficiency savings percentage is claimed until that workflow is actually run
and passes its publication gate.

## Session efficiency: preserve work, not conversation

ACCO 1.7 adds a host-neutral session-efficiency layer around the existing
repository/retrieval and output pipelines.

With Claude Code project hooks installed it now:

- restores a compact **structured continuity checkpoint** after resume/compaction;
- collapses exact repeated Bash output for the same command and blocks unchanged
  repeated full-file Reads;
- detects bounded retry loops, repeated commands, and long no-edit tool cascades;
- tracks working files plus recent test/lint/typecheck/build outcomes without
  storing raw prompt or assistant text;
- records accepted tool-context reductions in a private local event ledger.

Inspect the current working checkpoint:

```bash
acco continuity .
acco continuity . --json
```

Inspect local efficiency telemetry in the terminal/JSON or generate a
dependency-free HTML dashboard:

```bash
acco dashboard . --days 7
acco dashboard . --json
acco dashboard . --html .acco-dashboard.html
```

The dashboard deliberately separates exact available Claude usage counters from
**estimated before/after tool-context tokens saved**. It does not turn those
operational estimates into a cost-per-success or quality claim; the frozen
`evidence-run` pipeline remains the publication-grade surface.

Command compression also expands beyond pytest/Jest/git-log/package installs to
git status, grep/ripgrep/find, Ruff/ESLint/Pylint/Clippy, tsc/mypy/pyright,
Go/Cargo tests, common build systems, Python package installs, and
Docker/Kubernetes logs. Unknown failures still pass through conservatively and
critical-diagnostic recovery remains registry-wide.

## Durable project knowledge: reuse conclusions, not just context

ACCO can now keep explicit, evidence-backed findings across sessions without
turning session continuity into a transcript memory system. A finding must include
a claim, concrete evidence, an applicability rule, and at least one current
repository file anchor:

```bash
acco remember . \
  --claim "Session refresh is implemented in the auth service" \
  --anchor src/auth.py::refresh_session \
  --evidence "refresh_session delegates the rotation path" \
  --applicability "Use when changing login or refresh behavior"

acco recall . --query "debug session refresh"
acco knowledge-status .
```

Each anchor stores the source-file digest that existed when the finding was
recorded. If that file changes or disappears, the finding becomes `stale` and
ordinary recall excludes it. New findings may explicitly supersede older ones,
and exact claim/anchor duplicates update one record instead of multiplying
context. Storage is local, private, project-scoped, bounded, and contains only
the finding fields the caller explicitly submits.

This first layer is deliberately conservative: findings are **not** automatically
generated from model conversation and are **not** silently injected into every
context pack. CLI/MCP callers explicitly write and recall them, which keeps the
existing retrieval holdouts unchanged while creating a measurable path to future
cross-session read/reasoning avoidance.

The original surface remains available through MCP as `remember_finding`,
`recall_findings`, and `knowledge_status`.

The richer project-memory layer builds on the same evidence store rather than a
second database. Memories can be typed as `decision`, `bugfix`,
`convention`, `guardrail`, `architecture`, `fact`, or `finding`, with
tags, importance, related-memory ids, bounded reuse counters, and gentle
time-decay in ranking. Source digests still win over memory: changed or missing
anchors make a record stale regardless of its importance or reuse.

Agents use progressive disclosure rather than loading full memory records into
every turn:

```text
memory_index(query)     # compact ids / claims / types / scores
        ↓
memory_search(query)    # bounded applicability/evidence snippets
        ↓
memory_get(ids)         # full records only after relevance is confirmed
```

`remember_memory` performs bounded near-duplicate detection within the same
memory type and source anchors; a close replacement supersedes the older active
record instead of leaving two competing memories. ACCO still does not
auto-harvest raw conversation text or silently inject project memory into normal
context packs.

### Adaptive MCP tool disclosure

ACCO can advertise a smaller MCP schema instead of paying for every tool
definition on every request:

```bash
ACCO_MCP_PROFILE=minimal acco serve .
ACCO_MCP_PROFILE=context acco serve .
ACCO_MCP_PROFILE=memory acco serve .
ACCO_MCP_PROFILE=adaptive acco serve .
ACCO_MCP_PROFILE=full acco serve .
```

`full` remains the default and explicit compatibility fallback. `adaptive`
starts with seven core tools, including `discover_tools` and exact `recover_context`. The agent supplies the
current task description; ACCO deterministically maps it to bounded
memory, retrieval, review, output, and routing groups, returns the exact selected
schemas, expands the live `tools/list` surface, and advertises MCP
`listChanged=true`.

Project configuration can opt in without changing host MCP files:

```toml
[mcp]
profile = "adaptive"
adaptive_max_tools = 12
compress_schemas = true
```

The selector uses task vocabulary only, makes no model call, and defaults to
repository-retrieval specialists when the task is ambiguous. Unknown profile
names fail closed instead of silently selecting another surface.

## Recoverable optimization platform

ACCO can now apply the same fail-closed recovery rule across several
lossy context surfaces. When an optimization omits source, the exact original
can be stored under a content-addressed `tsr_...` handle and recovered with:

```bash
acco recover tsr_...
acco recovery-status .
```

MCP exposes the same path through `recover_context`. Recovery is
project-scoped, SHA-256 verified, capacity bounded, and non-evicting: if the
original cannot be retained, the lossy transform is not served.

Adaptive MCP disclosure can be combined with recoverable schema compression:
first advertise fewer task-relevant tools, then remove annotation-only schema
cost and shorten long descriptions while preserving argument-construction
fields and recognized constraints. The complete original tool catalog remains
recoverable.

A local closed-loop optimizer turns ACCO's existing telemetry into
reversible experiments:

```bash
acco optimize .
acco optimize . --apply adaptive-mcp
# do normal measured work
acco optimize . --evaluate opt_...
```

It only mutates ACCO-owned project configuration, backs up the exact
previous bytes first, and by default restores them when enough
provider-reported post-change turns fail to improve the requested
tokens-per-turn threshold. This operational decision is not treated as
task-success or quality evidence.

For clients that can point at a custom provider base URL, the opt-in local
reverse proxy moves request optimization closer to the actual API boundary:

```bash
acco provider-proxy . --upstream https://api.anthropic.com
```

Provider auto-detection recognizes Anthropic Messages, OpenAI Chat Completions /
Responses, and Gemini generateContent/streamGenerateContent. The boundary keeps
ACCO's retrieval-first design: current user instructions and fresh source
evidence are never rewritten there; only tool schemas and historical
tool/function outputs are eligible for recoverable reduction.

The proxy is loopback-only by default, requires HTTPS for non-local upstreams,
does not automatically follow upstream redirects, and forwards provider
responses byte-for-byte, including streaming responses. It can observe
provider-reported input/output/cache token counters as content-free local
telemetry. Disable that with `--no-usage-telemetry`. Inspect stable-prefix
reuse with `acco prefix-status .`.

TypeScript applications can intercept provider `fetch` calls without changing
the provider base URL:

```ts
const providerFetch = acco.interceptFetch("openai");
```

The interceptor optimizes supported JSON request bodies through the local ACCO
SDK bridge, then calls the original provider fetch. It fails open to the
untouched request by default if the local ACCO bridge is unavailable.

Large browser payloads captured by another tool can be focused locally without
giving ACCO arbitrary browsing authority:

```bash
acco browser-context page.html --query "ORD-0173 save"
acco browser-context ax.txt --format ax --query "checkout save"
acco browser-context snapshot.json --format json --query "buy product-42"
```

Auto mode recognizes HTML, accessibility/ARIA snapshots, and browser-shaped
role/name/children JSON. It keeps query neighborhoods plus a bounded
structural/actionable skeleton, ignores hidden/script/style HTML noise, and
stores exact omitted bytes for recovery. Generic tool routing and the Python/TS
middleware SDKs use the same specialization when a payload naturally matches
these browser shapes. ACCO never fetches the URL, executes page JavaScript, or
treats browser context as repository truth.

These mechanisms have regression/safety coverage, but no new end-to-end savings
percentage is claimed until a fresh paired-agent experiment verifies treatment
exposure, independent task success, blind quality parity, provider usage/cache
evidence, and cost per successful task.

## Knowledge-assisted read avoidance and cache economics

The durable finding store can now participate in the source-read guard, but only
behind an explicit opt-in:

```bash
ACCO_KNOWLEDGE_READ_AVOIDANCE=1 claude
ACCO_KNOWLEDGE_READ_AVOIDANCE=1 \
ACCO_CACHE_ECONOMICS=1 claude
```

For an unbounded source `Read`, ACCO checks for `verified`, active
findings anchored to that exact file. A changed/missing anchor, a probable or
speculative finding, an allowlisted/non-source file, or a bounded range never
qualifies. The replacement must be materially smaller than the file and tells
the agent to request an exact `offset+limit` range whenever implementation
bytes are needed.

The optional cache-economics gate evaluates projected relative input cost rather
than assuming that fewer raw tokens are always cheaper. It models an already
cached prefix separately from the new frontier and charges prefix recreation
when a proposed transformation invalidates cached history:

```bash
acco cache-economics \
  --original-frontier-tokens 4000 \
  --replacement-frontier-tokens 800 \
  --cached-prefix-tokens 12000 \
  --invalidates-cached-prefix \
  --expected-reuses 2
```

The default 1.25 cache-write and 0.10 cache-read factors are planning defaults,
not universal provider pricing. Override them for the active provider/model.

### Frozen knowledge-efficiency holdout

The feature is **not enabled by default and no end-to-end savings percentage is
claimed yet**. A separate frozen causal experiment reuses the 24 SWE-bench
Verified tasks at three trials per task. Both arms run the same current ACCO
binary, disable continuity/dedup/waste features, perform the same
investigation phase, and explicitly persist verified findings. A fresh
implementation session then compares memory-control against knowledge-assisted
read avoidance plus the cache-economics gate.

```bash
acco knowledge-holdout \
  benchmarks/knowledge-efficiency-swebench-24.frozen.json \
  --out knowledge-holdout-runs.json \
  --require-publishable
```

Publication requires independent task success, blind response-quality parity,
complete cache-TTL-aware pricing, verified knowledge seeding in every arm-run,
zero control read-avoidance activation, observed treatment activation, and a
strictly positive task-cluster 95% confidence interval for cost-per-success
reduction.

## Output Saver: reduce generated tokens too

ACCO can now control the other side of the bill: model output. The output
layer is deliberately split into **generation-time policy** and **safe
post-generation compaction**.

With Claude Code hooks installed, ACCO now applies this policy
automatically at `UserPromptSubmit`. It deterministically classifies strong
coding, debugging, review, planning, and explanation prompts, while ambiguous
follow-ups inherit the active task. The full policy is injected only when the
task or verbosity mode changes, on the first task in a session, or after a
clear/compact reset, avoiding repetitive policy-token overhead.

Manual policy generation remains available for orchestrators and hosts without
a prompt-hook surface:

```bash
acco output-policy --mode terse --task coding
acco output-policy --mode normal --task debugging --max-tokens 700 --json
```

The policy tells the agent to lead with the useful result, avoid conversational
preambles, task restatement, tool narration, repeated logs/context, tangents,
unchanged full-file reproduction, verbose test output, recaps, and closing
filler. `--task` adapts both wording and default budgets for coding, debugging,
review, explanation, and planning while preserving the historical
300/800/2,000-token defaults when no task is selected.

Debugging policy explicitly separates observations from hypotheses so brevity
does not pressure the model into inventing a root cause. Explicit user output
contracts, required code/diffs, diagnostics, safety information, and material
caveats always override the token target. Explicit requests such as "briefly"
or "in detail" also override the configured automatic verbosity for that task.
Automatic classification stores only resolved policy metadata (task/mode/budget),
not the user's prompt text.

Automatic budgets are adaptive by default. Small/simple tasks can receive less
than the static task budget, while multi-part, repository-wide, code-heavy, or
diagnostic-heavy prompts receive more room within hard mode-specific bounds.
Ambiguous follow-ups keep the active budget unchanged.

ACCO can also learn safer task/mode bases from real paired experiments:

```bash
acco output-calibrate benchmarks/agent-runs.json \
  --out .acco.output-calibration.json
```

Calibration accepts only blinded paired evidence, ignores failed/blocked or
quality-regressing ACCO runs, and requires at least three valid samples from three distinct task IDs
for a task/mode recommendation. The automatic hook consumes that artifact on
future tasks; absent or invalid calibration falls back to built-in defaults.

Claude Code can also record real turn-level usage automatically:

```bash
acco output-telemetry .
acco output-telemetry . --json
```

The prompt hook checkpoints the transcript byte offset and active policy. At
`Stop` or `StopFailure`, ACCO reads only transcript bytes appended for
that turn and records input/cache/output token counters, model calls, selected
budget, task/mode, and adaptive/calibration metadata. It does **not** copy prompt
text, assistant text, tool payloads, or transcript content. Telemetry reports
budget-utilization patterns but deliberately does not treat a finished model
turn as verified task success or response quality.

For a complete frozen evaluation, one resumable command now runs the full
evidence chain:

```bash
acco evidence-run benchmarks/e2e-swebench-24.frozen.json \
  --out benchmark-runs.json \
  --require-publishable
```

It performs randomized baseline/ACCO trials, independent hidden
verification, deterministic blind A/B grading, cache-TTL-aware cost-per-success
analysis, and quality-gated adaptive-budget calibration. The shipped frozen
suite contains **24 SWE-bench Verified tasks × 3 paired trials** (144 agent
runs). The GitHub workflow remains explicitly paid/manual and must be executed
before any new savings percentage is claimed.

For paired experiments with independent verification and blind response grades,
join all four evidence layers:

```bash
acco output-effectiveness benchmark-runs.json \
  --fresh-input-per-million <rate> \
  --cache-creation-5m-per-million <rate> \
  --cache-creation-1h-per-million <rate> \
  --cache-creation-unknown-per-million <rate> \
  --cache-read-per-million <rate> \
  --output-per-million <rate> \
  --require-publishable
```

The report measures **cost per successful task**, checks blind quality parity,
verifies policy telemetry against the copied transcript, clusters confidence
intervals by task, and identifies task/mode/budget cohorts that have enough
quality-preserving cross-task evidence to be candidates for calibration.

Compact an already-generated response:

```bash
cat response.md | acco output-save --mode terse
acco output-save response.md --max-tokens 500 --enforce-budget --json
```

Safe compaction removes exact repeated prose/status echoes and trivial filler.
Fenced code and diffs are preserved byte-for-byte. `--enforce-budget` may trim
prose, but **never truncates a fenced code/diff block**; if preserved code alone
cannot fit, the result reports `budget_exceeded: true` instead of corrupting
the answer.

For agent-to-agent state, compact JSON avoids prose and pretty-print overhead:

```bash
cat result.json | acco output-save --structured --mode terse
```

The same capabilities are exposed through MCP as `output_policy` and
`compact_output`. This lets an orchestrator inject the response policy before
the model generates tokens, which is the primary savings path; post-processing
cannot refund tokens that were already generated.


## Typo-tolerant retrieval and context browser

ACCO now has a conservative typo/fuzzy layer designed to complement,
not replace, structural retrieval.

Repository-level typo correction compares query words only against indexed
identifier vocabulary, uses strict similarity and ambiguity margins, and keeps
the original terms. Once a file has already survived retrieval, a slightly
broader fuzzy fallback can rescue a misspelled symbol identifier without
turning fuzzy similarity into a repository-wide ranking signal.

Inspect what the real packer is considering:

```bash
acco browse . --query "rendr template"
acco browse . --query "refresh sesion token" --show 1
acco browse . --query "cookie persistence" --interactive
acco browse . --query "redirect request" --json
```

Interactive mode supports `list`, `show N`, and `quit`. The browser reuses
the same file ranker, graph evidence, exact source-window selection, secret
redaction, and source-visible symbol accounting as `pack`; it is not a second
search engine. It also surfaces any high-confidence fuzzy corrections so a
human or agent can see why a typo matched an identifier.

The same inspection surface is available through MCP as `browse_context`.

### Explain ranking score decisions

Ranking observability is opt-in so ordinary packing does not pay for trace
collection. Ask for a stage-by-stage breakdown when diagnosing a surprising
candidate:

```bash
acco ranking-explain . --query "refresh session token"
acco ranking-explain . --query "refresh session token" --max-files 3 --json
```

Each candidate reports its final score plus exact score transitions such as
BM25, path/symbol evidence, structural authority, file-priority adjustments,
changed/working-set/feedback boosts, graph closure, embeddings, and custom
registered rerankers. Legacy `reasons` remain available unchanged.

The same structured payload is exposed through MCP as `explain_ranking`.
Third-party `RankingStage` implementations are traced automatically when an
explanation is requested; plugins do not need their own observability API.

### Diff ranking behavior across commits/configurations

Capture the same frozen task manifest on each revision or configuration:

```bash
acco ranking-snapshot benchmarks/context-quality.json \
  --path . --max-files 20 --out baseline-ranking.json

# after checking out or configuring the candidate
acco ranking-snapshot benchmarks/context-quality.json \
  --path . --max-files 20 --out candidate-ranking.json

# configuration experiments are captured in snapshot metadata too
acco ranking-snapshot benchmarks/context-quality.json \
  --path . --graph-hops 2 --closure-items 30 --out graph-v2-ranking.json
```

Then compare the artifacts:

```bash
acco ranking-diff baseline-ranking.json candidate-ranking.json
acco ranking-diff baseline-ranking.json candidate-ranking.json --json
```

The diff follows every expected file from the manifest, even when it falls below
the displayed top-N, and reports rank movement, score movement, and the
per-stage contribution changes that caused it. Snapshots with different
ground-truth hashes are rejected instead of producing misleading comparisons.

For CI, fail when an expected file disappears or drops farther than an allowed
amount:

```bash
acco ranking-diff baseline-ranking.json candidate-ranking.json \
  --fail-on-regression --allowed-rank-drop 1
```

This workflow intentionally separates snapshot capture from comparison, so the
same diff engine works across Git commits, feature flags, plugin registries,
model/embedding availability, or CI artifacts without managing hidden worktrees.

Pull requests run this comparison automatically against the protected base SHA.
CI checks out the base and candidate separately, uses the **base manifest for
both snapshots**, writes the Markdown comparison to the GitHub Actions job
summary, and uploads `baseline-ranking.json`, `candidate-ranking.json`, and
`ranking-diff.json` as a 14-day artifact.

Rank movement is intentionally informational for now: broken snapshot/diff
execution fails CI, but ranking regressions do not block merges until a
data-backed rank-drop threshold has been calibrated from real PR history.

### Calibrate a blocking policy from PR history

Each PR artifact now carries its pull-request number, workflow run/attempt, base
SHA, and candidate SHA. A separate **Ranking Calibration** workflow runs weekly
and on manual dispatch. It downloads the newest `ranking-regression-<PR>`
artifact per PR, so workflow reruns do not masquerade as independent evidence.

The workflow groups reports by frozen ground-truth hash and evaluates only the
current `benchmarks/context-quality.json` cohort. Old benchmark definitions are
kept separate instead of contaminating the current policy.

You can run the same calibration locally:

```bash
acco ranking-calibrate ./ranking-history \
  --ground-truth-sha <CURRENT_HASH> \
  --min-reports 20 \
  --markdown
```

The report includes report/observation counts, expected-file regressions,
disappearances, empirical positive rank-drop percentiles, and scoring-stage
activity. It also states whether the available history factually supports a
zero-rank-drop and/or no-disappearance policy after the configured minimum
sample count.

Calibration is deliberately descriptive: it does **not** call historical
regressions "noise" or automatically choose an allowed rank drop. That decision
remains a separate ratchet once enough representative PR history exists.


## Benchmark Output Saver compaction

Measure the deterministic post-generation layer with a reusable manifest:

```bash
acco output-benchmark benchmarks/output-saver.json
```

Each case can provide inline `text` or a response `path`, plus its response
mode, token budget, budget enforcement setting, and strings that must survive
compaction. The report measures original/output tokens, weighted reduction,
code-fence preservation, required-content preservation, and budget overflow.

This benchmark deliberately measures only deterministic **post-generation**
compaction. Generation-time policy savings must be measured from actual model
runs and can be compared with `acco cost-report`.


## Run broad end-to-end cost experiments

For publishable cost-per-success evidence, ACCO can execute frozen paired
coding experiments rather than relying on a handful of manually recorded runs.
The harness uses pinned detached worktrees, randomized baseline/enabled order,
independent verifier commands, repeated trials, real Claude Code transcripts,
and resumable checkpoints.

```bash
# freeze task/design definition before paid runs
acco experiment benchmarks/e2e-suite.json --print-task-definition-hash

# inspect the randomized 20-50 task schedule without calling a model
acco experiment benchmarks/e2e-suite.json --out benchmark-runs.json --dry-run

# execute, then require the broad-evidence protocol in analysis
acco experiment benchmarks/e2e-suite.json --out benchmark-runs.json
acco benchmark benchmark-runs.json --rates rates.json --require-publishable
```

The publication gate requires at least **20 distinct tasks** and **3 paired
trials per task**. Cost/success confidence intervals are bootstrapped by task,
so repeated trials of one task do not inflate the effective sample size. See
[BENCHMARKING.md](BENCHMARKING.md) for the frozen-suite protocol and runner
schema.

## Measure cost per successful task

Context reduction is not the same thing as invoice reduction. ACCO can
compare paired baseline and optimized agent runs directly:

```bash
acco cost-report baseline.json acco.json
acco cost-report baseline.json acco.json --json
```

Each run records a `task_id`, success outcome, input/output/cache tokens,
tool/model calls, latency, and optionally `cost_usd`. If the provider bill is
not already available, pass token pricing instead:

```bash
acco cost-report baseline.json acco.json \
  --input-per-million 10 \
  --output-per-million 30 \
  --cached-input-per-million 2
```

The report computes total cost, success rate, **cost per successful task**,
token/cost/latency reductions, call-count changes, and tasks whose outcome
improved or regressed. By default the two files must contain exactly the same
task IDs so cost comparisons cannot silently use different workloads.

The same paired manifest already used by `agent-evaluate` can be passed
directly as a single argument, so correctness and economics stay attached to
one experiment artifact:

```bash
acco agent-evaluate benchmarks/agent-runs.json
acco cost-report benchmarks/agent-runs.json
```

Paired manifests use `task` plus
`condition: baseline|acco`; `seconds` is accepted as latency and is
normalized to milliseconds in the cost report.


## Release history

Release-specific changes live in [CHANGELOG.md](CHANGELOG.md). Validation
results and evidence limitations live in [VALIDATION.md](VALIDATION.md), so this
README stays focused on current usage rather than duplicating historical release
notes.

## Automatic protections

The recommended Claude Code lifecycle is:

```bash
acco setup /path/to/project --host claude
acco doctor /path/to/project
```

This configures both project hooks and MCP. The lower-level `acco
install` command remains available for compatibility and specialized
Claude-only/user-wide hook installation; new projects should normally use
`setup`.

### Bounded source reads

A full `Read` of a large source file is denied before it enters context. So is a lone `cat <large source file>` through Bash, which is the same dump by another route; pipes, redirects, chains and globs are left alone. The denial contains a capped structural outline with line-number gutters so the agent can request an exact range instead.

This happens before the read rather than rewriting its result: editing tools need the original source bytes.

```text
large full read
    ↓
PreToolUse guard
    ↓
outline + exact ranges
    ↓
bounded Read
```

Duplicate-read blocking is optional and off by default.

### Recoverable command-output compression

Large successful Bash output is compressed only when the replacement is materially smaller. ACCO now also collapses long runs of identical successful log lines while retaining the repetition count.

Errors, exceptions, tracebacks, failed assertions, interrupted commands, images, unsupported structured responses, and stderr are treated conservatively. Test failures preserve diagnostic evidence.

Before replacing output, ACCO stores the original result locally. The
replacement keeps the legacy paged-output id and also emits a universal
`tsr_...` recovery handle when available:

```bash
acco output OUTPUT_ID --stream stdout --offset 1 --limit 80
acco recover tsr_... --path .
```

MCP clients can use `recover_context` for the same `tsr_...` handle. Prune
legacy paged-output originals explicitly:

```bash
acco outputs-prune --days 7
```

## Source navigation

```bash
# signatures/structure of one file
acco outline src/service.ts

# exact body of one symbol
acco snippet src/service.ts Service.fetchUser

# bounded structural map of a repo
acco map src --max-tokens 4000 -o CODEMAP.md

# task-aware working set
acco pack . -q "implement retry backoff for downloads" --max-tokens 5000
```

Python is parsed with `ast`. JavaScript, JSX, TypeScript, and TSX use Tree-sitter for structural extraction. Other supported languages retain conservative pattern-based outlines.

## Measure before claiming savings

ACCO separates observed API usage from offline estimates:

```bash
acco sessions /path/to/project
acco policy /path/to/project
acco audit /path/to/project
acco budget /path/to/project
acco check /path/to/project
```

Reports distinguish recorded usage, cache reads/writes, repeated reads, estimated tool-result size, always-on instructions, MCP schema cost, and hypothetical one-shot outline reductions.

For paired real-task benchmarking:

```bash
acco benchmark runs.json --rates rates.json
```

See [BENCHMARKING.md](BENCHMARKING.md). A smaller prompt or tool result is not automatically a cheaper successful task; follow-up reads, retries, model quality, and cache behavior all matter.

## Context audit and MCP cost

```bash
acco audit .
acco audit . --probe-mcp
acco mcp-prune .
```

The audit identifies instructions and rules that are injected repeatedly, and can measure MCP tool-schema payloads. `mcp-prune` is dry-run by default.

## Standalone filtering

```bash
npm test 2>&1 | acco filter --command "npm test"
pytest -q 2>&1 | acco filter --command "pytest -q"
```

The filter removes ANSI noise, compacts valid JSON, abbreviates huge hex blobs, collapses duplicate successful log lines, and applies command-aware reductions. Failure evidence is favored over aggressive compression.

## Configuration

`acco setup` creates `.acco.toml` in the project. Hook and
guard settings can be committed with the repository instead of being repeated
as shell environment variables:

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
```

Existing `ACCO_*` environment variables remain supported and take
precedence over project configuration, which keeps CI/temporary overrides
simple.

| Variable | Default | Purpose |
|---|---:|---|
| `ACCO_GUARD` | `1` | disable with `0` |
| `ACCO_READ_MAX_LINES` | `220` | maximum guarded source-read window |
| `ACCO_REREAD` | `0` | optional duplicate full-read denial |
| `ACCO_ALLOW` | empty | colon-separated source allowlist globs |
| `ACCO_MIN_LINES` | `40` | minimum Bash stdout lines considered for filtering |
| `ACCO_MAX_LINES` | adaptive | filtered output line target |
| `ACCO_KEEP_TAIL` | `15` | tail retained by generic filtering |
| `ACCO_DELTA` | `0` | opt-in graph-aware pytest/Ruff diagnostic Delta |
| `ACCO_INGRESS_OPTIMIZER` | `0` | opt-in lossless oversized-prompt staging before Claude processing |
| `ACCO_INGRESS_THRESHOLD_TOKENS` | `12000` | estimated prompt threshold for ingress staging |
| `ACCO_INGRESS_PACKET_TOKENS` | `1600` | bounded staged packet target |
| `ACCO_RETRIEVAL_CACHE` | `1` | persistent content-fingerprinted completed-pack cache |
| `ACCO_RETRIEVAL_CACHE_MAX_ENTRIES` | `64` | bounded cache entries per project |
| `ACCO_RUST_FASTPATH` | `1` | use optional native extension when installed; `0` forces Python |
| `ACCO_KNOWLEDGE_READ_AVOIDANCE` | `0` | opt-in verified-knowledge replacement for redundant full-file Reads |
| `ACCO_CACHE_ECONOMICS` | `0` | require cache-aware projected-cost approval for knowledge read avoidance |
| `ACCO_CACHE_EXPECTED_REUSES` | `2` | expected future cache reads in the planning model |
| `ACCO_CACHE_WRITE_FACTOR` | `1.25` | relative cache-write input factor; provider/model override recommended |
| `ACCO_CACHE_READ_FACTOR` | `0.10` | relative cache-read input factor; provider/model override recommended |
| `ACCO_CACHE_MIN_RELATIVE_SAVINGS` | `0.05` | minimum projected relative savings for the runtime cache gate |
| `ACCO_CACHE_TTL_MIN` | `5` | advisory cache-gap classification only |
| `ACCO_SEMANTIC_MODEL_REVISION` | unset | optional immutable SentenceTransformer revision; partitions semantic vector/query caches |
| `ACCO_STATE_DIR` | `~/.claude/acco` | local state and recoverable output storage |

## Design principles

ACCO follows six rules:

1. **Select before compressing.** The cheapest irrelevant context is context never loaded.
2. **Structure before bodies.** Outlines locate the small exact ranges worth reading.
3. **Exact bytes for edits.** Source windows are never semantic summaries.
4. **Failures are evidence.** Diagnostics are preserved rather than optimized away.
5. **Compression must be recoverable.** Omitted command output is stored locally.
6. **Measure task outcomes.** Token counts alone are not proof of end-to-end savings.

## Development

```bash
python -m pip install '.[dev]'
python -m pytest -q
```

CI runs the full suite on Python 3.10, 3.12, and 3.13.

See [INTEGRATIONS.md](INTEGRATIONS.md) for agent setup, [CHANGELOG.md](CHANGELOG.md)
for release history, and [VALIDATION.md](VALIDATION.md) for validation limits.
