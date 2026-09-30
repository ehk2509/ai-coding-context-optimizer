# Architecture

ACCO is organized around **small host-independent cores** and thin
integration adapters. The main rule is that adding a command, processor, or host
adapter should not require editing unrelated orchestration logic.

## Dependency direction

```text
CLI entry
  -> CommandRegistry
      -> command handlers
          -> application modules

Claude hook / replay / CLI
  -> OutputPipeline
      -> ProcessorRegistry
          -> OutputProcessor contracts
              -> built-in or custom processors
      -> preservation/text policy

CLI / MCP / future agent hosts
  -> RepositoryContextService
      -> repository index + ranking + graph + packing services
```

The dependency arrows point inward toward contracts and pure application logic.
Host-specific JSON, environment variables, persistence, and subprocess behavior
stay at the edges.

## Recoverable optimization boundary

Lossy context transformations now share one content-addressed recovery contract:

```text
caller / host / local provider proxy
        ↓
deterministic transform
  ├── MCP schema compression
  ├── historical tool-output compression
  ├── browser payload focusing
  ├── optional RAG/API/database context compression
  └── hook output compression
        ↓
RecoveryStore.put(exact original) ──→ tsr_<sha256-prefix>
        ↓
serve smaller representation + recovery handle
```

`RecoveryStore` is project-scoped persistence, not a ranking or compression
engine. Compressors decide whether a transform is safe/useful; recovery only
establishes exact source availability. Capacity exhaustion fails closed: the
caller keeps the original representation instead of evicting an older recovery
record and creating a dangling handle.

Browser/context payload optimization is another explicit edge, not a second
retrieval system. `browser_context.py` recognizes caller-supplied HTML,
accessibility/ARIA text snapshots, and browser-shaped JSON trees. It focuses
query neighborhoods plus bounded structural/actionable anchors and writes exact
source bytes to `RecoveryStore` before accepting a lossy result.
`context_router.py` selects this specialization only for recognized browser
shapes; ordinary JSON/log/table/search output continues through the general
router. The SDK bridge exposes the same implementation at
`/v1/browser/optimize`.

`domain_middleware.py` is another optional edge over caller-supplied
JSON-compatible data. It adapts already-retrieved RAG documents, API payloads,
or database/query rows into bounded model-context representations, then uses the
same token/byte reduction gates and `RecoveryStore`. It has no retrieval,
network, database, ORM, or SQL execution authority.

Provider interception is kept at an explicit edge.
`provider_boundary.py` classifies Anthropic/OpenAI/Gemini request shapes and
identifies only historical tool/function-result surfaces. `provider_transform.py`
then applies schema reduction and recoverable historical-result reduction while
leaving the current task, fresh repository/source evidence, and ordinary
assistant content untouched. Retrieval/ranking remains the authority for deciding
which source enters context.

`provider_proxy.py` owns HTTP/network behavior and remains opt-in. It binds to
loopback by default, forwards response bytes unchanged, and does not
automatically follow upstream redirects. `provider_usage.py` passively observes
JSON/SSE response bytes for provider-reported token/model counters and writes
only content-free telemetry; it is not allowed to rewrite provider responses.
The TypeScript SDK's `interceptFetch` is another thin edge adapter over the same
Python transform rather than a second optimization implementation.

`wrapper.py` and `wrap_adapters.py` own foreground host launch/interception
policy. `persistent_proxy.py` owns durable project/provider profiles, native
user-session supervisor lifecycle, stable port reservation, instance-identified
readiness, and reversible Claude/Codex routing. These modules do not gain
repository ranking authority; they only choose how supported host traffic
reaches the existing provider transform.

Stable-prefix accounting stores hashes/sizes/counters through
`prefix_cache.py`; it never becomes repository truth. The closed-loop
`optimizer.py` may propose and mutate only ACCO project configuration.
Every mutation is journaled with an exact recovery backup and is evaluated
against later provider-reported token evidence before it can be retained as a
measured local improvement.

## Runtime compression/cache v2 boundaries

Five newer surfaces keep their responsibilities separated rather than creating a
second orchestration stack:

```text
native host hook
  -> private project-local native runtime
      -> shared HookRuntime

OutputPipeline
  -> content detection
  -> format invariant gate
  -> S0-S4 safety contract
  -> exact RecoveryStore gate when selective/lossy

provider request
  -> stable-prefix conversation epoch
  -> provider cache economics plan
  -> optional safe provider-native cache marker
  -> provider-observed cache usage kept as separate evidence

prompt/tool lifecycle
  -> bounded Task Contract
  -> relevance-ranked session-ledger evidence
  -> live repository/tests remain authoritative
```

The native runtime is an optimization process, not a correctness dependency. It
binds to a random loopback port, requires a private per-project bearer token,
accepts bounded JSON events, emits no payload/access logs, and caches one
`HookRuntime` until project configuration changes. CLI hooks fall back to the
existing direct path when the runtime cannot be reached. A timeout does not
replay the event because the runtime may already have committed local
continuity/telemetry side effects.

Recovery Store v2 keeps existing byte-exact `tsr_...` handles and adds
canonical-JSON `tsr_obj_...` records. Typed records support RFC 6901 subtree
selection and explicit dependency edges. Existing recovery databases migrate in
place; stored payload digests are verified on retrieval and capacity remains
no-eviction/fail-closed.

`output.content_engine` classifies content separately from command routing and
assigns a formal safety class. Format-specific invariants currently protect JSON
syntax, changed diff lines, table headers/schema, and source declarations/syntax
before an accepted candidate can replace the original. This is an acceptance
gate over existing processors, not a parallel compressor registry.

Provider cache planning deliberately distinguishes **planned economics** from
**provider-observed hits**. `prefix_cache.py` stores independent bounded
conversation epochs so interleaved agents/subagents do not overwrite one
provider-level anchor. `provider_cache.py` can plan provider-specific break-even
behavior and, in apply mode, add only a conservative Anthropic/Bedrock
cache-control breakpoint when the existing request shape permits it. OpenAI
automatic caching and Gemini explicit cached-content resources remain
observation/planning surfaces unless their native lifecycle is controlled by the
caller.

Task Contract state is a bounded working-state projection over prompt/tool
events: goal, explicit decisions, working files, unresolved failures, validation
state, and named checks. Resume context combines that contract with
relevance-ranked older ledger events. Passing validation only resolves matching
validation-family failures; no remembered result supersedes live source or
tests.

## Learned runtime evidence loops

Four optional learning/measurement layers sit beside, not inside, ACCO's
correctness-critical transforms:

- `tool_field_learning.py` stores only bounded tool identities, structural JSON
  paths, exposure counts, and selective-recovery counts. Qualified hints may
  preserve repeatedly requested fields during recoverable JSON compaction.
  Exact recovery remains authoritative; learning failure is fail-open.
- `cache_ttl.py` consumes provider-observed cache counters plus stable-prefix
  reuse state. Missing cache counters produce no TTL evidence. A qualified TTL
  requires repeated observed hits and an exact-prefix post-hit miss, yielding
  conservative hit/miss bounds rather than a guessed provider constant.
- `output_holdout.py` assigns eligible conversations deterministically to
  control/treatment using opaque conversation hashes. Treatment only clamps an
  already-present provider output limit. Reports aggregate conversation-level
  means by provider/model/task/mode/limit-field and bootstrap the measured
  output-token delta. This is not a response-quality or cost-per-success gate.
- `observability.py` aggregates content-free provider and framework operation
  metadata. The provider proxy exposes local JSON and Prometheus surfaces, while
  Python/TypeScript SDKs expose the same report data.

These layers can influence optimization only where an explicit safe integration
exists: learned field hints affect recoverable JSON selection, and qualified TTL
estimates are attached to provider cache planning. Measurement never substitutes
for repository evidence, exact recovery, or frozen task-success evaluation.

## Command boundary

`acco.entry` no longer owns a branch for every top-level command. New
commands are composed in `acco.command_registry` as `CommandSpec` values.
`CommandRegistry` is independently testable and preserves fallback to the legacy
CLI for existing commands.

Command implementations are grouped vertically under
`acco.command_handlers`:

- `context.py` — repository browsing, ranking explanations, impact, and feedback;
- `efficiency.py` — local session continuity and operational dashboard surfaces;
- `evaluation.py` — context/agent evaluation plus ranking snapshot/diff/calibration workflows;
- `experiment.py` — paired experiments and cost-per-success reporting;
- `host.py` — host setup/doctor/uninstall, validation, completion, and MCP serving;
- `output.py` — output policy, compaction, replay, explain, and benchmarks;
- `optimization.py` — recovery, provider proxy, browser focusing, prefix evidence, and closed-loop optimization;
- `sdk.py` — loopback bridge lifecycle for non-Python agent SDK clients;
- `persistent_proxy.py` — persistent proxy install/status/start/stop/uninstall lifecycle;
- `patch.py` — diff-context packing and patch review.

The registry imports these handlers directly. `acco.commands` is retained
only as a compatibility facade for older imports and contains no command
implementation. This keeps command growth local to one user-facing capability
instead of rebuilding a central CLI monolith.

## Integration lifecycle boundary

`integration_setup.py` owns host discovery and safe MCP/setup configuration
mutation across supported coding agents. It only creates/replaces ACCO-owned
entries: JSON MCP configuration is merged by key, Claude hook removal preserves
unrelated commands, and managed TOML/registry surfaces retain unrelated host
state. Multi-host setup preflights target files before the first write so one
conflict cannot leave an earlier host partially configured.

Provider-boundary attachment is deliberately separate from MCP/setup lifecycle:
`wrap_adapters.py` uses documented host contracts for foreground Copilot,
Cursor, and OpenClaw interception, while `persistent_proxy.py` currently owns
durable automatic attachment only for Claude Code and Codex. Unsupported or
ambiguous provider routes fail closed instead of mutating undocumented host
state.

`runtime_config.py` resolves the nearest project `.acco.toml` and then
applies `ACCO_*` environment overrides. Claude's adapter and read guard
consume that shared resolver rather than maintaining independent configuration
parsers. Setup is idempotent and therefore doubles as the upgrade/repair path;
uninstall removes only managed integration state.

`doctor` composes host status with `RepositoryContextService.status()` and
available Claude transcript evidence. It diagnoses integration health without
moving host-specific policy into the repository application layer.

## Agent SDK boundary

Custom-agent integration has two layers that share the same application logic:

```text
Python agent
  -> acco.sdk.AccoEngine
      -> provider_transform / context_router / OutputPipeline / model_routing
      -> RecoveryStore

TypeScript/JS agent
  -> @acco-ai/sdk
      -> loopback /v1 SDK transport
          -> acco.sdk_server.SdkApplication
              -> the same AccoEngine
```

The TypeScript SDK is intentionally a typed transport client, not a second
implementation of ACCO's optimizer. This prevents recovery, compression, and
routing policy from diverging between languages. `sdk_server.py` owns only
bounded JSON transport and loopback network behavior; `sdk.py` owns the
framework-neutral application contract.

The SDK bridge is not a provider proxy and does not hold provider credentials.
Callers keep ownership of provider authentication, retries, streaming, and
execution. The bridge binds to loopback by default and requires an explicit
operator override for non-loopback exposure.

The optional `rag()`, `api()`, and `database()` facades are application
adapters over the same `AccoEngine`; they do not create a generic data-access
layer. Their input is data the caller already owns in memory, and accepted
lossy representations remain recovery-gated exactly like other SDK context
transforms.

## Workspace federation

`workspace.py` sits above `RepositoryContextService`; it does not create a
second source index. Each registered repository is scored through its existing
ranking pipeline, then receives a bounded share of one workspace token budget.
Package manifests contribute only cross-repository identity/dependency hints.
Final source remains exact repository-local pack output with repository
provenance retained in the combined context.

## Whole-context budget boundary

`context_budget.py` is a deterministic policy planner above individual ACCO
compressors. It allocates one caller-owned token envelope across source,
history, memory, historical tool results, tool schemas, and reserve using task,
complexity, risk, and optional observed component sizes.

The planner does not retrieve source, persist memory, or rewrite history itself.
`RepositoryContextService` consumes only the `source` slice. Provider
transformation consumes only the `schemas` and `tool_results` slices. The
remaining allocations are explicit orchestration guidance for hosts and SDK
clients until independently validated runtime mechanisms exist for them.

## Repository application boundary

`RepositoryContextService` is the shared application layer for repository-aware
operations. Host-facing code should use it instead of composing
`RepositoryIndex`, context packing, browsing, impact analysis, semantic
enrichment, and ranking feedback independently.

The service owns one repository scope and one reusable index lifecycle. It
provides `build_context`, `browse`, `explain_ranking`, `find_symbols`,
`impact`, `feedback`, `enrich_typescript`, `get`, `refresh`, and `status`.

The main pack CLI, context CLI commands, and repository-oriented MCP tools now
consume this same boundary. `mcp_server.IndexService` remains as a compatibility
subclass so existing imports and MCP index-status behavior stay stable.

This keeps retrieval policy single-sourced while leaving low-level modules such
as `pack.py`, `repo_index.py`, `context_browser.py`, and `impact.py`
independently testable.

## Durable project-knowledge boundary

`acco.knowledge.FindingStore` is a separate persistence/application
component for conclusions that were already established in prior work. It is not
part of repository ranking and does not mutate `RepositoryIndex`.

A finding contains a compact claim, concrete evidence, an applicability rule,
confidence, optional human-readable invalidators/supersession, and one or more
repository anchors. Each anchor captures the file content digest at write time.
Recall recomputes those digests: changed or missing source makes the finding
`stale`, while explicit replacement makes it `superseded`. Normal recall
serves only active findings.

`RepositoryContextService` owns the host-facing `remember_finding`,
`recall_findings`, and `knowledge_status` operations, so CLI and MCP share
one validation/invalidation policy. The durable store is private, local,
project-scoped, bounded to the newest records, and never stores raw conversation
history implicitly.

This boundary intentionally keeps memory out of the validated ranking path for
the first release. Future experiments can compare source retrieval alone against
source retrieval plus current findings without contaminating the frozen
retrieval baselines.

### Smart tool-proxy boundary

`acco.tool_proxy` is a host-independent application service for
large source Read results. The Claude adapter reaches it only through the
`HookServices.smart_read_proxy` contract. The ordinary source guard remains the
PreToolUse authority and delegates only eligible large, unbounded source Reads
when proxying is explicitly enabled.

The data path is evidence preserving:

```text
verified Read result + latest bounded user-task hint
        ↓
structural outline + deterministic candidate windows
        ↓
optional free/local selector (Ollama)
        ↓
validated/clamped line ranges
        ↓
exact excerpts rehydrated from original file content
        ↓
bounded updatedToolOutput
```

Model prose is never treated as source. A malformed response, timeout, or
unavailable local model falls back to deterministic range selection. Bounded
Reads bypass the proxy entirely so edits and verification can request exact
bytes. The prompt hint is read transiently from the Claude transcript tail and
is not copied into ACCO state.

### Safe prompt-ingress boundary

Claude's `UserPromptSubmit` hook can block a prompt or add context but cannot
replace the submitted prompt. ACCO therefore does not implement ingress
optimization by appending a summary (which would keep the large original in
context) or by returning an unsupported transformed-prompt field.

The opt-in path is instead:

```text
oversized prompt
  -> UserPromptSubmit threshold
  -> exact local stage + SHA-256
  -> decision=block, suppressOriginalPrompt=true
  -> small follow-up /acco:ingress <id>
  -> bounded exact head/tail packet
  -> exact ingress-read ranges only when needed
```

The original prompt never reaches the model on the blocked turn. No omission is
presented as complete content, and stage integrity is checked before range
recovery.

### Persistent chunk-semantic retrieval boundary

Semantic retrieval is an optional post-score discovery/reranking stage. It does
not replace the deterministic repository index and does not own final context
rendering.

```text
RepositoryIndex digests/definitions
        ↓
symbol-aware declaration chunks
        + 64-line / 12-line-overlap fallback windows
        ↓
local SentenceTransformer
        ↓
private SQLite vectors + source coordinates
        ├── exact cosine fallback
        └── optional persisted HNSW sidecar
        ↓
up to 3 non-overlapping hits per file
        ↓
semantic-only file rank + bounded similarity/corroboration boost
        ↓
bounded one-hop provider/peer/artifact expansion
        ↓
pre-semantic confidence gate
        ↓
normal exact-source symbol/window rendering
```

The SQLite store has separate `files`, `chunks`, `query_vectors`, metadata,
and ANN-label tables. A warm repository with a repeated exact query can serve
semantic ranking without loading the embedding model: file vectors and the query
vector are both persistent. Semantic state identity includes both model name and
the optional `ACCO_SEMANTIC_MODEL_REVISION`; the latter is also written
to metadata and included in exact-query vector keys.

Every file vector set is keyed by the content digest already present in
`RepositoryIndex`. Before embedding a changed file, ACCO hashes the live
bytes again; if they no longer match the structural index digest, semantic sync
fails and requires an index refresh rather than persisting cross-version
evidence.

HNSW is acceleration only. SQLite vectors are authoritative, the sidecar has a
chunk-identity signature, and missing/stale/unavailable HNSW falls back to exact
cosine scan. This keeps ANN availability out of retrieval correctness.

The fusion stage runs after deterministic BM25/structural scoring and the
ordinary graph closure. Symbol-aware chunks carry declaration kind, parent,
signature, and exact implementation bytes; fallback windows preserve coverage
for module-level behavior, prose/configuration, and parser gaps.

At file level, up to three non-overlapping hits are retained with diminishing
corroboration weight. The *raw* semantic boost is computed independently of
lexical rank so weak-overlap candidates can still be discovered. The stage
records `semantic-chunk:...` and `semantic-file-rank:...` evidence. Bounded
one-hop/provider, artifact-role, and implementation-family expansion can add
secondary semantic evidence.

Before semantic scoring starts, ACCO snapshots an ordinal confidence key from
evidence that already exists: undiscounted parser/provider authority,
implementation-vs-low-value source class, graph corroboration, direct
path-or-symbol identity, and finally whether any lexical overlap exists. Path
and symbol matches intentionally share one tier so embeddings cannot reinterpret
one kind of deterministic identity as inherently stronger than the other.
Term-frequency magnitude and BM25 score are deliberately excluded from that
key, so long/repetitive files cannot manufacture authority.

After all semantic and semantic-derived boosts, the **semantic confidence gate**
enforces a monotonic authority invariant. Pure topical candidates may reorder
freely. Once a baseline predecessor has direct path/symbol/graph/parser evidence,
a candidate with equal direct confidence may not jump over it, and a candidate
with weaker confidence may not jump over any stronger predecessor. Discounted
parent-mismatch structural credit is not treated as hard authority. A clamped
promotion records `semantic-confidence-gate:...` in ranking evidence.

This preserves semantic rescue as a discovery mechanism while making
deterministic lexical/structural evidence the authority layer. The gate is
ordinal and repository-agnostic: it contains no embedding-similarity threshold,
holdout identifier, repository name, or task-specific exception. The same
authority rule continues at rendering time: parser-backed symbol windows precede
semantic ranges inside a file, so tight per-file fitting clips embedding ranges
before exact structural source.

### Persistent retrieval-cache boundary

The application-level repository service enables a bounded persistent pack
cache. Its key covers the repository content fingerprint (sorted indexed source
digests + semantic refs + index version), query, retrieval/budget settings,
resolved changed/priority/exclusion sets, local ranking feedback, and any session
working-set state. This means a source/index/config/feedback change naturally
misses the old key.

The cache stores the final bounded context pack and ranking evidence but does
not duplicate hydrated full source text inside cached ranked-file objects.
Embedding reranking and custom ranking-stage registries bypass caching until
their external/model/plugin identities can be safely fingerprinted.

### Optional Rust acceleration boundary

`fastpath.py` is the only Python-to-native boundary. It first checks the
`ACCO_RUST_FASTPATH` kill switch, imports the optional
`_acco_fast` extension when available, and otherwise runs the exact
Python reference logic.

The first native primitives are deliberately pure:

- offline character-ratio token estimation;
- index identifier extraction;
- BM25 score accumulation;
- identifier-set Jaccard similarity;
- padded character n-grams.

Python AST and Tree-sitter structural symbol extraction remain the authoritative
path: those parsers are already native-backed or semantically sensitive. CI
builds the Rust wheel and reruns context-quality/retrieval tests with the native
backend required, making output parity—not mere compilation—the acceptance
criterion.

### Knowledge-assisted read boundary

The existing PreToolUse source guard is the only automatic consumer of durable
findings. Automatic use is separately opt-in and deliberately narrower than
manual `recall`:

1. the request must be an unbounded source-file `Read`;
2. the exact file must have at least one active `verified` finding;
3. current file digests must still match the stored anchors;
4. the compact finding replacement must clear a minimum net-token floor;
5. when cache economics is enabled, the replacement must also clear the
   configured projected-cost floor.

The guard never treats memory as edit bytes. Its denial text explicitly routes
agents to a bounded source range when exact implementation text is required.
This preserves the existing principle that edits operate on exact source while
allowing prior verified reasoning to prevent redundant whole-file ingestion.

`cache_economics.py` is a pure policy module. It separates an already-cached
prefix from the new frontier and can model both frontier-only rewrites and
transformations that invalidate cached history. Provider/model price ratios are
inputs to the policy rather than hard-coded dollar claims. The same primitive is
exposed through the `cache-economics` CLI for inspection.

### Knowledge-efficiency evaluation boundary

The frozen knowledge holdout is distinct from the existing session-efficiency
holdout. Both experiment arms explicitly seed verified findings during an
identical no-edit investigation phase. They then cross a real fresh-session
boundary. Continuity, output/read dedup, and behavioral waste detection stay off
in both arms; only knowledge read avoidance and its cache-economics gate differ.

The runtime event ledger proves feature exposure only. Tool calls, input tokens,
duplicate reads, success, blind response quality, and cache-TTL-aware billed
cost are derived independently from transcripts/verifiers/graders. The
publication gate uses task-cluster bootstrap intervals and does not publish a
savings claim merely because the mechanism activated.

### MCP schema profiles

The MCP registry supports bounded advertisement profiles without changing tool
implementations. `minimal` exposes the common context/knowledge loop,
`context` adds repository-analysis and index operations, and `full` preserves
the complete historical tool surface. The protocol resolves
`ACCO_MCP_PROFILE` only when the default registry is composed; injected
custom registries remain untouched for tests and embedders.

## Context-packing pipeline boundary

`acco.pack` is now the compatibility facade and final bounded-assembly
stage. Retrieval algorithms are split under `acco.packing`:

- `contracts.py` — `RankedFile` and `ContextPack` data contracts;
- `query_analysis.py` — query normalization, structural request hints,
  signature/overload intent, and conservative repository typo expansion;
- `file_scoring.py` — deterministic BM25, path/symbol/structural authority,
  changed/working-set/feedback boosts, candidate filtering, and final sort key;
- `graph_rerank.py` — dependency/semantic-ref closure plus optional
  persistent chunk-semantic/RRF fusion;
- `semantic_retrieval.py` — incremental vector persistence, query-vector
  caching, exact cosine/HNSW retrieval, and source-coordinate evidence;
- `ranking.py` — compatibility facade plus the `rank_files` stage orchestrator;
- `symbol_scoring.py` — within-file lexical/structural scoring, overload
  resolution, fuzzy/call-graph evidence, and parent/container credit;
- `symbol_windows.py` — selected-symbol source windows, evidence labels,
  lexical navigation windows, and file-section rendering;
- `symbols.py` — compatibility facade for the pre-split private import surface;
- `render.py` — section fingerprints, visible-symbol accounting, hard-budget
  fitting, and static retrieval-plan construction.

`pack.py` keeps `build_context_pack`, the historical `rank_files` entry point,
and private compatibility aliases used by existing tests/callers. Its
`rank_files` wrapper deliberately resolves changed files through the facade
before entering the extracted stage, preserving the established monkeypatch
seam while leaving the ranking implementation host-independent.

The extraction is behavior-preserving: ranking policy and weights remain in the
same order, and the frozen holdout remains the regression oracle for any future
changes to these stages.


Final pack assembly is **coverage-aware but rank-preserving**. After ranking,
`build_context_pack` reserves the existing compact exact-source minimum for as
many leading candidates as the hard token budget and `max_files` permit.
Higher-confidence/authoritative files can still consume additional depth, and
explicit `priority_files` keep their historical allocation semantics. The
coverage reserve does not alter file scores or reorder candidates; it prevents
early large sections from exhausting the context before later high-ranked files
receive any exact-source evidence.

### File ranking stages

File ranking now has a one-way dependency chain:

```text
query_analysis
      ↓
file_scoring
      ↓
graph_rerank
      ↓
ranking.py orchestration
```

`query_analysis.py` has no dependency on scored files or graph traversal.
`file_scoring.py` owns deterministic lexical/structural policy and does not
import closure or embedding implementations. `graph_rerank.py` can adjust an
already-scored candidate set but does not redefine BM25 or structural boosts.
`ranking.py` preserves the historical private helper surface while composing
those stages in the existing order.

`symbol_scoring.py` consumes `query_analysis.py` directly rather than routing
through the ranking compatibility facade. This keeps shared overload/query
interpretation reusable without coupling within-file scoring to repository-level
ranking orchestration.

### Pluggable ranking extensions

Post-score ranking is composed through `RankingStageRegistry`. A stage declares
a stable `name`, an integer `order`, an `enabled(context)` gate, and an
`apply(context, ranked)` mutation over the already-scored candidate list.
The public stage context exposes only the repository index, query, and immutable
stage options; it does not leak the private deterministic-scoring scope.

The default registry preserves the validated baseline:

```text
100  graph-closure
200  embeddings
```

The registry rejects duplicate names and duplicate execution orders during
composition. It intentionally does not sort between stages: each extension sees
the deterministic pre-rerank order plus any score/evidence mutations from prior
stages, matching the previous graph-then-embedding behavior. Final ordering
remains centralized in `rank_files()`.

Custom registries flow through `rank_files`, `build_context_pack`, and
`RepositoryContextService.build_context`. Existing defaults remain unchanged
when no registry is provided, while
`DEFAULT_RANKING_STAGE_REGISTRY.extend(...)` provides a non-mutating way to add
new rerankers.

### Ranking observability

Score tracing is deliberately opt-in. Normal ranking keeps `trace_scores=False`
so context packing and holdout evaluation do not allocate per-candidate trace
events. `RepositoryContextService.explain_ranking`, the
`ranking-explain` CLI command, and the MCP `explain_ranking` tool enable
tracing explicitly.

Deterministic file scoring records exact before/after transitions at the point of
each score mutation. `RankingStageRegistry` snapshots enabled rerankers and
automatically records each plugin's aggregate delta plus newly-added evidence.
This makes custom stages observable without expanding the extension contract.

`RankingScoreEvent` is additive metadata on `RankedFile`; legacy
`score`, `reasons`, ordering, and default runtime behavior remain unchanged.
The explanation payload verifies that the final trace endpoint equals the final
rank score.

### Ranking regression snapshots

`ranking-snapshot` records trace-enabled ranking evidence against the same task
manifest used by retrieval evaluation. Snapshot capture disables changed-file
and learned-feedback boosts to make revision/configuration comparisons stable,
records repository revisions, and retains every expected file even when its
rank is below the configured top-N display limit.

`ranking-diff` requires identical ground-truth hashes and task definitions,
then compares expected-file rank/score movement and per-stage contribution
changes. The comparison layer does not rerun retrieval, so baseline and
candidate artifacts can originate from different commits, machines, or
configurations. Optional CI gating treats disappearance as a regression and
supports a bounded allowed rank drop.

This makes ranking R&D evidence-preserving: a regression can be attributed to
the scoring component or registered reranker whose contribution changed,
rather than inferred from a single final score.

PR CI operationalizes the same contract without hidden baseline recomputation.
The workflow checks out the immutable pull-request base SHA and the candidate
tree separately. The base ACCO captures the baseline snapshot; candidate
ACCO captures the candidate snapshot. Both use the base checkout's task
manifest so a PR cannot redefine its own comparison ground truth. The candidate
then performs the pure artifact diff and publishes Markdown plus raw JSON
artifacts.

The first CI phase is informational for rank movement. Tooling failures remain
hard failures, while ranking regressions are summarized but do not block merges
until a regression allowance is calibrated from observed PR history.

### Ranking gate calibration

`ranking_calibration.py` consumes saved ranking-diff artifacts rather than
repository state. It groups reports by frozen ground-truth hash, computes
empirical positive rank-drop percentiles, disappearance/regression frequencies,
and per-stage score activity, then reports whether the configured minimum
history factually supports strict zero-drop or no-disappearance behavior.

The scheduled/manual `ranking-calibration.yml` workflow collects the newest
ranking artifact per PR, deduplicating workflow reruns before sampling. It
selects the current benchmark hash explicitly, so reports from previous task
definitions remain separate cohorts. The resulting JSON and Markdown are
descriptive evidence only; calibration does not infer that a historical
regression is harmless noise or silently change merge policy.

### Symbol scoring vs rendering

Within-file relevance and source rendering are separate policies.
`symbol_scoring.py` has no repository-index or redaction dependency and does not
format source windows. `symbol_windows.py` consumes the scoring stage to select
symbols, then owns only source-range selection, evidence labels, and section
formatting. `pack.py` imports both implementation stages directly, so the
`symbols.py` compatibility facade is not on the production execution path.

This boundary is intentional: scoring weights and overload policy can be
benchmarked independently from changes to context-line radius, large-container
windowing, source formatting, or redaction.


## Output boundary

The pre-1.4 `acco.output_processors` module remains as a compatibility
facade. New code should use the `acco.output` package:

- `contracts.py` — processor/result/policy contracts;
- `registry.py` — ordering and failure-aware processor selection;
- `processors.py` — format-specific transformations only;
- `text.py` — shared normalization and critical-diagnostic preservation;
- `pipeline.py` — orchestration and acceptance policy.

This prevents format-specific processors from owning routing or global safety
policy, and lets integrations inject a processor registry without modifying the
pipeline.


## Session-efficiency evaluation boundary

The runtime session layer and its causal evaluation are deliberately separate.

`session_metrics.py` reads raw benchmark transcripts and derives repeated
commands, identical-failure retries, duplicate Reads, and tool-call counts
without consulting the efficiency ledger. `session_holdout.py` joins those
outcomes with task success, blind quality, exact pricing, condition-profile
identity, feature activation, and task-cluster bootstrap intervals.
`session_holdout_pipeline.py` is orchestration only, while
`session_holdout_docker.py` owns the pinned two-phase fresh-session protocol.

The benchmark control and treatment both install the same ACCO build.
Only the four session-efficiency environment switches may differ. Those
condition profiles are included in the frozen task-definition hash and are
validated before paid execution.

The treatment event ledger is **exposure evidence**, not an outcome oracle:
publication metrics such as tool calls and retries come from the transcript.
This prevents the optimization from grading its own behavior.

## Session-efficiency boundary

Session continuity and behavioral optimization live under
`acco.efficiency` rather than in the Claude adapter or repository
retrieval engine:

- `store.py` — private project-scoped snapshot/event persistence, locking,
  atomic writes, and bounded retention;
- `service.py` — structured working-state updates, exact command-output
  fingerprints, redacted command labels, and bounded behavioral signals;
- `report.py` — operational aggregation over efficiency events plus exact
  output-telemetry counters;
- `dashboard.py` — dependency-free rendering of the same report to local HTML.

The session layer consumes task classification and token estimation but does not
own repository ranking or output transformation policy. `HookRuntime` reaches
it only through injected service callables, preserving host independence.

Continuity is intentionally **structured state, not conversation memory**. It
stores task class, paths, redacted command labels/fingerprints, validation
status, failures, and counters. Raw prompts, assistant prose, and raw tool output
are excluded. Resume/compaction may inject a compact orientation snapshot, while
`clear` discards the active working checkpoint.

Cross-turn output dedup is exact by construction: the normalized command
identity and output digest must both match. Approximate/similar output continues
through the ordinary processor registry. Unchanged source-read dedup uses the
existing verified full-read digest and never applies to ranged Reads.

Behavioral signals are bounded nudges rather than autonomous policy changes.
Repeated-command/retry-loop detection is scoped to the current user turn, and
tool-cascade detection requires a configured number of tool calls without an
edit. The operational event ledger can inform later evaluation, but it never
changes the frozen retrieval/effectiveness publication gates.

## Native host-hook adapter boundary

Native coding-agent hooks are transport adapters over the existing
`HookRuntime`; they are not independent policy engines.

```text
Codex / Cursor / Gemini / Qwen / Copilot native event
        ↓
native_hooks.normalize_payload
        ↓
HookRuntime + existing services
        ↓
native_hooks.adapt_response
        ↓
host-native decision / replacement JSON
```

`native_hooks.py` owns event names, tool-id normalization, model-visible result
extraction, and documented response-schema translation. Read guarding, command
output processing, exact recovery, prompt ingress, generation policy, continuity,
routing advice, and efficiency telemetry stay in the same application services
used by Claude Code.

Host capability differences are explicit. Gemini and Copilot provide documented
successful-result replacement semantics. Trusted Codex project hooks expose a
documented PostToolUse stop-normal-processing path plus additional model context,
which ACCO uses for recoverable replacement of local Bash/MCP results without
claiming interception of hosted tools that bypass those events. Cursor and Qwen
do not expose a documented general successful-result replacement in their
command-hook surfaces, so ACCO does not manufacture one.

`native_hook_configs.py` owns project configuration. Shared Cursor, Gemini, and
Qwen JSON files are merged by removing/replacing only commands with ACCO's stable
native-hook prefix. Codex additionally refuses to create a sibling
`.codex/hooks.json` when the project layer already defines inline hook tables,
and its idempotent JSON serialization keeps the reviewed hook definition stable
across repairs. Copilot uses a dedicated `.github/hooks/acco.json`; an unmanaged
file at that exact path is a hard preflight conflict. Setup preflights all
selected surfaces before mutation, and uninstall removes only ACCO-owned entries.

## Hook boundary

`acco.hook` is now the Claude-specific composition root only. It parses
JSON/stdin, resolves project configuration plus environment overrides into
`HookConfig`, and wires concrete services. Event routing and replacement policy live in the host-neutral
`HookRuntime`.

`HookRuntime` receives an explicit `HookServices` bundle containing the
`OutputPipeline` contract, Delta application, output persistence, guard,
session/read-state operations, digesting, policy nudges, and token estimation.
This makes host behavior testable without filesystem-backed session state or a
Claude process, and lets another host reuse the same runtime policy with a
different adapter.

## Searchable session-ledger boundary

`acco.efficiency.ledger` is a project-scoped event/history component distinct
from both the compact continuity snapshot and durable project knowledge.

```text
HookRuntime events
  ├── session start / prompt task
  ├── explicit decision/preference snippets
  ├── file Read/Edit/Write activity
  ├── redacted commands / failures / validation
  └── pre-compaction checkpoint
        ↓
private SQLite events table
        ↓
FTS5 summary/subject/path index when available
        ↓
session_search / session_recent
        ↓
bounded resume context or explicit historical retrieval
```

Raw prompts and raw tool-result bodies are not persisted in this ledger.
Decision capture is deliberately narrow: only sentences containing explicit
decision/preference language are retained, after the same credential-style
redaction used for persisted command labels. Metadata accepts only bounded
JSON scalars.

The ledger is not repository truth and does not participate in source ranking.
It records *what happened*. `FindingStore` / project memory records
*conclusions deliberately preserved*. The ordinary continuity snapshot remains
the cheap latest-state path; the ledger gives older searchable history without
forcing that history back into every model call.

## Out-of-context execution boundary

Programmable execution is a separate application primitive in
`acco.execution`. It does not live in the MCP transport, Claude hook, output
pipeline, or repository ranking engine.

The data flow is intentionally narrow:

```text
explicit repository-relative files
        ↓
root/path + byte-count validation
        ↓
restricted Python AST validation
        ↓
isolated-startup subprocess
        ↓
JSON-serializable result
        ↓
small result → return directly
large result → exact recovery store + bounded preview
```

The model supplies only the analysis program and file names. ACCO reads the
selected source locally and passes it directly to the child process, so the
large bytes do not need to be copied through model context merely to count,
group, filter, scan, or summarize them. The same boundary now has three
orchestration surfaces: inline `execute`, repository-contained
`execute_file`, and bounded `batch_execute`. All delegate to the same
validator/subprocess/recovery implementation rather than creating new execution
engines.

The language surface rejects imports, arbitrary file access, process/shell
entry points, dynamic evaluation/introspection helpers, private/dunder traversal,
class/async constructs, and repository path escapes. The process also receives
hard file/input/result/time limits and a minimal environment. These controls are
defense in depth rather than an OS-level hostile-code sandbox; the security
contract is documented explicitly in `SECURITY.md`.

`AccoEngine.execute`, MCP `execute`, and the loopback/TypeScript SDK all
delegate to this single implementation. MCP adaptive disclosure treats execution
as a specialist surface rather than expanding the always-advertised core tool
set. Oversized computed results reuse `RecoveryStore`; execution never invents
a second persistence/recovery mechanism.

## MCP server boundary

`acco.serve` is now a compatibility facade and composition root. The
server implementation is split under `acco.mcp_server`:

- `contracts.py` — tool/context contracts with no JSON-RPC or stdio knowledge;
- `services.py` — repository-index lifecycle service;
- `tools.py` — tool schemas, application handlers, and `McpToolRegistry`;
- `protocol.py` — JSON-RPC method routing and MCP result/error translation;
- `transport.py` — newline-delimited stdio only.

Tool handlers return plain application values and depend on an explicit
`McpToolContext`. The protocol runtime receives an injectable registry and
index service, and the transport receives an `McpProtocol` instance. This lets
other hosts or transports reuse the exact same tools without importing stdio
behavior or duplicating repository logic.

## Architectural invariants

1. **Fail open:** unknown failed output is preserved unless a processor explicitly
   opts into failed-command handling.
2. **Preservation is centralized:** critical-line recovery and the final size
   gate run after every processor.
3. **Compatibility facades stay thin:** legacy imports delegate to the new core;
   they do not reimplement behavior.
4. **Composition validates ambiguity:** duplicate CLI command names and processor
   registries without a generic fallback fail during construction.
5. **Host adapters do not define domain policy:** hooks translate host payloads
   into calls to application services; they should not accumulate processor- or
   command-family-specific logic.
6. **Command handlers grow vertically:** registry composition and compatibility
   facades must not accumulate command implementation logic.
7. **MCP transport is replaceable:** tool handlers must not depend on JSON-RPC or
   stdio, and protocol routing must consume tools through the registry contract.
8. **Repository orchestration is single-sourced:** host-facing integrations use
   `RepositoryContextService` rather than rebuilding index/ranking/graph flows.
9. **Packing stages stay behaviorally separable:** file ranking, symbol scoring,
   source-window rendering, render/budget helpers, and final assembly may evolve
   independently without moving policy back into compatibility facades.
10. **Scoring does not render:** symbol relevance policy cannot depend on source
    formatting/redaction, while window rendering consumes scoring through the
    extracted scoring stage instead of duplicating its weights.
11. **Graph reranking is post-score:** deterministic file scoring must not depend
    on graph closure or embedding implementations; rerankers consume an already
    scored candidate set and cannot duplicate the lexical scoring pipeline.
12. **Ranking extensions are registered:** post-score behavior grows through
    `RankingStageRegistry`; duplicate names/orders fail at composition and
    `rank_files()` retains the only final sort.
13. **Observability is additive:** score tracing must not change ranking
    arithmetic, legacy reason strings, or default runtime cost; explanation
    surfaces opt into traces explicitly.
14. **Ranking comparisons preserve ground truth:** regression diffs require the
    same frozen task hash and compare saved evidence rather than silently
    rerunning baseline retrieval under candidate code.
15. **PR ranking baselines are immutable:** CI captures baseline evidence with
    base-commit code against the base checkout and uses the base manifest for
    both sides; candidate code cannot redefine the comparison ground truth.
16. **Gate calibration is empirical:** PR reruns are deduplicated, ground-truth
    cohorts remain separate, and calibration reports observed distributions
    without automatically redefining regressions as allowed noise.
17. **Session efficiency stays content-minimal:** continuity cannot persist raw
    prompt/assistant/tool-result content, and cross-turn replacement requires
    exact command/output identity.
18. **Operational savings are not publication evidence:** local dashboard
    estimates remain separate from independently verified cost-per-success.
19. **Documentation is a tested public interface:** package/README/validation
    versions stay aligned, every shipped CLI command is present in the command
    reference, and relative links in the maintained public documentation set
    must resolve in CI.
20. **Programmable execution stays bounded and single-sourced:** MCP/SDK adapters
    delegate to `acco.execution`; only explicit repository-contained text inputs
    are admitted, and oversized results require exact recovery before a lossy
    preview may cross the model boundary. Execution is not represented as a
    hardened hostile-code sandbox.

21. **Native hooks translate, never fork policy:** non-Claude host adapters
    normalize input and translate output only. A host without documented
    successful-result replacement must not be represented as if ACCO can rewrite
    that result, and shared host configuration may remove only ACCO-owned entries.


`tests/test_architecture_boundaries.py`, `tests/test_hook_runtime.py`,
`tests/test_mcp_server_boundaries.py`, `tests/test_repository_service.py`, and
`tests/test_pack_pipeline_boundaries.py`, `tests/test_symbol_pipeline_boundaries.py`,
`tests/test_ranking_pipeline_boundaries.py`, `tests/test_ranking_stage_registry.py`,
`tests/test_ranking_observability.py`, `tests/test_ranking_regression.py`, and
`tests/test_ranking_ci_workflow.py`, `tests/test_ranking_calibration.py`,
`tests/test_ranking_calibration_workflow.py`, and `tests/test_documentation.py`
lock in these extension seams and public documentation contracts so future
features can grow without silently breaking discoverability or evidence links.

### Semantic query views

When optional semantic retrieval is enabled, concise prompts use one persistent
query vector. Long prompts can add at most two deterministic views extracted
from clauses or overlapping word windows. Views contain only original user-query
vocabulary; no model-generated expansion or repository identifier is introduced.
Each view is retrieved independently through the same SQLite/HNSW index and
persistent query-vector cache, then fused with weighted reciprocal rank before
the existing non-overlapping chunk aggregation and bounded graph expansion.
Exact source remains the only rendering authority.

## Model-routing decision boundary

Model routing is an application policy, not a transport concern.

```text
prompt
  -> deterministic task classifier
  -> adaptive complexity tier
  -> explicit risk escalation
  -> minimum capability policy
  -> allowed/profiled model filter
  -> fresh pricing lookup
  -> cheapest eligible one-turn projection
  -> route decision
```

The price stage runs only after the capability gate. The built-in profiles are
conservative ACCO product policy and are not empirical rankings of model
quality.

Before those edges consume the decision, an optional quality-gated calibration
artifact may add an exact-bucket exception below the static capability floor.
Artifacts are generated only from frozen paired model experiments with the same
non-model arm configuration, independent verifier success, complete blinded
response quality, and transcript-confirmed model identity. Runtime loading
rechecks hard sample/success/quality floors before an exception becomes
eligible. Calibration therefore extends the allow-set; it never replaces the
static fallback policy.

The same pure decision engine feeds three edges:

- `model-route` CLI for humans and scripts;
- MCP `route_task` for orchestrators that can actually select a model;
- Claude `UserPromptSubmit` for opt-in observe/advisory mode.

Claude's hook boundary does not claim to mutate the active top-level model.
Instead it stores content-free route metadata and can inject a bounded advisory.
Stop telemetry later compares the route target with the actual model id observed
in transcript usage counters. This keeps routing adoption measurable without
turning a recommendation into a savings or task-success claim.
