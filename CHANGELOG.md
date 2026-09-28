# Unreleased

# 1.23.0 - 2026-09-28

- **Added first-class out-of-context programmable execution.** ACCO can run a
  restricted Python analysis program over explicit repository-contained text
  files in a separate local process and return only the JSON result, keeping
  bulk logs/JSON/reports out of model context. The surface is shared by MCP
  `execute`, `AccoEngine.execute(...)`, the loopback `/v1/execute` bridge,
  the TypeScript client, and frozen standalone executables.
- **Kept programmable execution bounded and recoverable.** Imports, arbitrary
  file access, shell/process APIs, dynamic evaluation/introspection, private
  attribute traversal, path escapes, binary inputs, and unbounded execution are
  rejected or capped. Large computed results reuse ACCO's existing exact
  `tsr_...` recovery store. The boundary is documented as defense in depth,
  not a hardened hostile-code VM/container sandbox.
- **Added native hook interception for Cursor, Gemini CLI, Qwen Code, Copilot
  CLI, and Codex.** All adapters normalize host events into the existing
  host-neutral `HookRuntime` instead of duplicating compression, read-guard,
  ingress, continuity, routing, or telemetry policy. Setup/uninstall mutations
  preserve unrelated host configuration.
- **Added result replacement where the host genuinely supports it.** Gemini and
  Copilot can replace/hide successful tool results directly. Trusted Codex
  project hooks can suppress normal handling of large local Bash/MCP results
  and deliver ACCO's compact recoverable context. Cursor/Qwen capability
  reporting stays conservative where general successful-result rewriting is
  not available.
- **Made Codex lifecycle integration trust-aware.** `acco setup --host codex`
  now manages both the existing MCP block and project `.codex/hooks.json`
  lifecycle hooks, keeps repeated setup byte-stable, preserves unrelated hook
  groups, refuses mixed inline/hooks.json representations, and does not mark
  executable project hooks trusted on the user's behalf.
- **Added prompt-derived multi-path task coverage.** The generation policy now
  receives a deterministic checklist when a task explicitly names multiple
  APIs/paths/reproductions, reducing the risk that focused verification fixes
  only the first reported path and stops.
- **Recorded the 144-run paired SWE-bench development study without promoting it
  into a release claim.** On 24 tasks × 3 trials per arm, ACCO measured 55/72
  solved versus 56/72 for plain Claude Code, with 25.6% fewer total tokens,
  20.3% fewer model calls, and 21.1% lower equivalent cost per solved task.
  Because the suite was adapted rather than frozen and success was one run
  lower, the result remains non-publishable development evidence.
- **Release-gated the combined architecture cross-platform.** The new execution
  and native-hook paths passed the same 19-job CI matrix covering Python
  3.10/3.12/3.13, native Windows, TypeScript, Rust/HNSW parity, frozen retrieval
  holdout, ranking regression, real CLI-output corpora, and standalone
  Linux/macOS/Windows x86_64 and ARM64 builds.


# 1.22.1 - 2026-09-28

- **Migrated project hosting identity to `ehk2509`.** Repository URLs, Claude
  marketplace metadata, standalone installers, Homebrew publishing, benchmark
  fixtures, product UX, and documentation now target
  `ehk2509/ai-coding-context-optimizer`.
- **Moved the unused WinGet identity to `ehk2509.ACCO`.** ACCO had no installed
  WinGet user base, so the package identifier and manifest filenames were
  migrated before public adoption rather than carrying the old account-derived
  identifier indefinitely.
- **Added an identity regression guard.** CI now scans tracked text and filenames
  so the previous GitHub handle or WinGet package identifier cannot silently
  re-enter release/install surfaces.
- No runtime feature, retrieval, ranking, compression, or benchmark claim changes
  are introduced by this patch release.


# 1.22.0 - 2026-09-27

- **Added an explicit host transport capability registry.** `acco transport-status`
  now reports whether provider interception is automatic, environment-only,
  manual-setting, or unsupported for each host. Persistent Claude/Codex routing
  derives from this single fail-closed registry instead of duplicating host
  policy across proxy code.
- **Added federated multi-repository workspace intelligence.** `acco workspace
  init|add|remove|status|pack` keeps each repository's existing ACCO index and
  ranking pipeline authoritative, scores repositories for the task, incorporates
  bounded package-dependency hints from package.json/pyproject.toml/Cargo.toml/go.mod,
  allocates one hard global token budget, and preserves repository provenance in
  the combined context.
- **Added adaptive whole-context budgeting.** `acco context-budget` allocates a
  caller-owned context envelope across exact source, prior history, durable
  memory, historical tool results, tool schemas, and reserve. Repository packing
  consumes only the source slice; provider interception can use observed schema
  and historical tool-result demand to decide when existing recoverable
  compression should activate.
- **Exposed whole-context planning to custom agents.** Python SDK,
  `POST /v1/context-budget`, and the typed TypeScript client now share the same
  deterministic planner. The TypeScript SDK source package advances to 0.3.0.
- **Preserved conservative evidence boundaries.** The new workspace and budget
  layers are release-gated mechanically, but ACCO does not claim that these
  additions alone establish a universal reduction in API cost or cost per
  successful coding task. That still requires fresh paired full-stack evidence.


# 1.21.0 - 2026-09-27

- **Broadened zero-config provider wrapping without replacing ACCO's
  retrieval-first design.** `acco wrap` can infer provider-aware arbitrary
  CLIs conservatively, preserve existing gateways, reuse an existing ACCO
  proxy, and fail closed on ambiguous provider environments. Specialized
  adapters now use documented GitHub Copilot BYOK variables, a safe manual
  Cursor BYOK bridge, and ephemeral OpenClaw config overlays rather than
  private-state rewrites.
- **Added persistent background provider proxies for Claude Code and Codex.**
  `acco proxy install|status|start|stop|uninstall` creates project/provider
  stable loopback profiles with Linux systemd-user, macOS LaunchAgent, and
  Windows logon-task lifecycle support. Host routing changes only after ACCO
  verifies the expected proxy instance; profiles persist no provider
  credentials, reserve ports across stopped sessions, survive launcher
  upgrades, and roll back transactionally on partial installation failure.
- **Added optional RAG/API/database compressor SDK middleware.** Python and
  TypeScript callers can compress already-retrieved documents, caller-supplied
  API JSON, and database/query rows through the same structural context router,
  token/byte reduction gates, and exact recovery store used by the coding
  product. These adapters do not retrieve, fetch, authenticate, connect to a
  database, or execute SQL, preserving ACCO's coding-first identity.
- **Strengthened cross-host safety boundaries.** Copilot Azure base semantics
  are preserved; Cursor private settings remain untouched; OpenClaw
  OAuth/native/custom routes and configured fallbacks fail closed when full
  interception cannot be guaranteed; Codex persistent routing is
  project-scoped and refuses unmanaged root provider overrides.
- **Kept release claims conservative.** These additions expand integration,
  persistence, and embeddability. They do not establish a new universal token,
  API-dollar, task-success, or cost-per-success improvement. The existing
  frozen retrieval and paired-agent evidence boundaries remain in force.


# 1.20.0 - 2026-09-26

- **Completed cross-platform standalone lifecycle support.** Frozen ACCO
  binaries now detect Linux, macOS, and Windows plus x86_64/ARM64 at runtime,
  download the matching release asset, verify its SHA-256 sidecar, smoke-test
  the replacement, and update safely. Windows still defers replacement until
  process exit; Linux/macOS replace atomically in place.
- **Preserved native package-manager ownership.** Frozen binaries installed by
  Homebrew or WinGet route `acco update` back through `brew upgrade acco` or
  `winget upgrade --id ehk2509.ACCO` instead of mutating package-managed
  files directly.
- **Expanded standalone releases to six native targets.** Release and PR smoke
  matrices now cover Linux x86_64/ARM64, macOS ARM64/Intel, and Windows
  x86_64/ARM64 using native GitHub-hosted runners.
- **Added native signing/notarization hooks and build provenance.** Windows
  Authenticode and macOS Developer ID/notary steps activate when their
  repository secrets are configured. Every standalone release remains
  SHA-256-verified and gets GitHub build-provenance attestation independently
  of OS signing.
- **Prepared package-manager-native distribution.** Releases now generate an
  architecture-complete Homebrew formula and WinGet 1.12 multi-file manifests
  from the actual release checksums. A secret-gated publisher workflow can
  create/update `ehk2509/homebrew-acco` and submit WinGet manifests;
  absent publisher credentials, those external steps visibly no-op rather than
  claiming publication.

# 1.19.1 - 2026-09-26

- **Completed the Windows standalone lifecycle.** Frozen `acco.exe` now uses
  a checksum-verified self-update path instead of incorrectly trying to invoke
  itself as a Python interpreter. The updater downloads the latest Windows
  asset and SHA-256 sidecar, smoke-tests the replacement, and schedules the
  executable swap after the current ACCO process exits.

# 1.19.0 - 2026-09-26

- **Added first-class Windows runtime support.** Native Windows CI now runs the
  complete Python test suite plus retrieval and product-UX smoke checks on
  `windows-latest`, so Windows behavior is a release gate rather than an
  untested standalone artifact.
- **Made the standalone Windows installer zero-friction.** The verified
  PowerShell installer smoke-tests `acco.exe`, installs under
  `%LOCALAPPDATA%\ACCO\bin`, and adds that directory to the user's PATH
  idempotently.
- **Added native PowerShell completion and Windows state storage.**
  `acco completion powershell` emits a native argument completer, while
  private runtime state defaults to `%LOCALAPPDATA%\ACCO` with APPDATA and
  `ACCO_STATE_DIR` fallbacks.
- **Fixed provider wrapping from frozen executables.** Standalone `acco.exe`
  now re-enters itself as `acco.exe provider-proxy ...` instead of incorrectly
  treating the frozen executable as a Python interpreter. This makes
  `acco start` / `acco wrap` viable for Claude, Codex, and Gemini from the
  no-Python Windows installation.

# 1.18.0 - 2026-09-26

- **Made ACCO install-and-forget for ordinary users.** The recommended
  non-Claude path is now `uv tool install acco` followed by one
  `acco setup`; `uvx acco bootstrap` provides a one-command persistent
  bootstrap. Setup now
  detects/configures hosts, writes the explicit safe profile, installs managed
  Claude Lean without overwriting user-modified skill content, warms the
  structural repository index, runs readiness checks, and finishes with
  `READY` when healthy.
- **Added a beginner product shell without removing the expert CLI.** Bare
  `acco` is now a project-aware home screen, `acco start` detects/remembers
  the coding agent and launches it, and `acco advanced` keeps the complete
  existing command surface discoverable separately.
- **Added simple everyday health and proof surfaces.** `acco status` now shows
  integration/index health plus bounded local efficiency telemetry while
  `--ledger` preserves the previous low-level state view. `acco demo` gives
  a provider-free repository-context demonstration and `acco savings`
  summarizes operational reductions without turning estimates into bill
  claims.
- **Added package-manager-aware upgrades.** `acco update` reports the safest
  detected `uv`, `pipx`, or pip upgrade command and mutates the environment
  only with explicit `--apply`.
- **Prepared standalone distribution.** Tagged releases build smoke-tested
  macOS, Linux, and Windows single-file executables with SHA-256 sidecars so
  users can install ACCO without managing Python. The Python/PyPI path remains
  the reference distribution and `uv` remains the recommended install.

- **Added a first-class Compaction Guardian.** Claude Code now registers a
  `PreCompact` hook that captures bounded structured task state before host
  compaction. Resume/compact starts can restore that checkpoint even when the
  host session id changes; raw prompts, assistant prose, and raw tool output
  are not persisted by the guardian.
- **Added low-friction `acco wrap` provider launching.** Claude, Codex, and
  Gemini presets start an ephemeral loopback ACCO provider proxy, set only the
  provider's base-URL environment variable for the child, and tear the proxy
  down on exit. Model routing remains off unless explicitly enabled. The
  `acco claude`, `acco codex`, and `acco gemini` aliases use the same path.
- **Added the portable ACCO Lean skill.** `acco lean-skill` can print or install
  a terse-output policy for Claude or the portable `.agents/skills` layout.
  The policy explicitly scopes brevity to final prose and forbids skipping
  investigation or verification to save tokens.
- **Added payload-aware fallback compression.** Unknown commands can now route
  large browser HTML/AX dumps, JSON, unified diffs, leveled logs, and Markdown tables to content-type
  processors after command-specific processors decline them. Diff compression
  preserves every changed line; hook/provider recovery remains authoritative
  for lossy reductions.
- **Added cross-host context auditing and a live status line.**
  `acco context-audit` covers Claude context plus AGENTS.md, GEMINI.md,
  Copilot instructions, Cursor rules, portable skills, duplicate instruction
  bodies, oversized files, and optional MCP schema measurement.
  `acco statusline` exposes compact savings/waste/prefix/working-set signals
  from local operational telemetry.

- **Added everyday provider cost controls without weakening task quality.**
  The opt-in provider proxy can now suppress repeated byte-identical historical
  tool results with exact local recovery and can observe model-routing
  opportunities. Automatic model downgrades are disabled by default and, in
  `calibrated` mode, require an accepted quality-gated routing bucket; static
  heuristics alone never change the caller's model.
- **Made provider cache telemetry understand normal conversation growth.**
  Stable-prefix accounting now distinguishes exact reuse from append-only
  history extension using content-free element hashes, instead of treating
  every newly appended assistant/tool turn as a cache-prefix miss.
- **Made verification cheaper without making it optional.** Coding guidance now
  starts with the smallest existing test/lint/typecheck/build target that
  directly covers touched code, expands when failures/risk/project policy
  require it, and discourages unchanged blind retries. The #128 requirement to
  run relevant existing tests before finishing remains intact.
- **Kept cost evidence boundaries explicit.** Duplicate-history token estimates,
  prefix-reuse observations, and projected routing savings are operational
  signals, not general API-savings or cost-per-success claims. End-to-end
  savings still require paired verified evaluation.

- **Stopped the generation policy from cutting verification short.** The
  injected policy said "Stop once the acceptance criteria are satisfied" and
  gave an unscoped output budget; in paired SWE-bench runs agents treated a
  passing reproduction as done and skipped the test suite, failing
  `psf__requests-2931` in 3/4 runs versus 0/4 for plain Claude Code. The budget
  now limits the final prose only, and code changes must run the touched
  code's existing tests before stopping. With the fix, ACCO solved the task
  3/3.
- **Ran benchmark agents in the grader's environment.** `acco.claude_docker`
  gains `--task-image` (suite placeholder `{task_image}`): the agent runs
  inside the SWE-bench task image with the snapshot mounted at `/testbed`, the
  image's environment commit as its base and its build products excluded, so
  it can run the same tests the grader does. Subscription auth (`--auth
  subscription`), root-host sandboxing, `ACCO_OUTPUT_POLICY` forwarding and
  clean retry state are also supported.
- **Made history-isolated snapshots equal the task revision.** Snapshots now
  force-add tracked files that match `.gitignore` and undo `export-subst`
  rewrites; previously agent edits to such files were silently dropped from
  the graded patch.
- **Added a log-heavy stress fixture and a limit-tolerant runner.**
  `benchmarks/stress/generate_ledgerkit.py` builds a deterministic repository
  with a ~1 MB CI log and a 2,400-line module; `scripts/run_resilient_experiment.py`
  resumes experiments across subscription usage limits and token expiry.
  Development evidence only: on 10 paired trials of this single synthetic
  task, ACCO reduced cost per success by 24.5% (trial bootstrap 95% CI 7.1% to
  37.5%, 10/10 success in both arms); small SWE-bench samples showed no
  significant difference. No general savings figure is claimed.

# 1.17.0 - 2026-09-25

- **Made bounded context packing coverage-aware.** ACCO now reserves compact
  source evidence across leading ranked files before spending the remaining
  budget on depth, preventing a strong retrieval ranking from being silently
  collapsed into too few packed files under a fixed context cap.
- **Separated ranking quality from pack realization in semantic holdouts.**
  Frozen retrieval evaluation now records rank-level file recall, packed file
  recall, selected-file counts, and rank-to-pack recall loss so allocation
  failures cannot be misdiagnosed as ranking failures.
- **Validated the allocator on untouched semantic holdout #17.** Across 18
  eligible issue-derived tasks from pytest, Black, Starlette, attrs, Resty, and
  anyhow, ACCO lexical/structural rank@12 reached **91.67%** file recall versus
  **80.56%** for the trivial distinct-term lexical baseline. The 6,000-token
  bounded pack also reached **91.67%**, selecting 12.0 files per task on
  average with **0.00 percentage points** of rank-to-pack recall loss.
- **Kept semantic evidence conservative.** Gated hybrid semantic retrieval also
  reached **91.67%** on holdout #17 with 0 improved tasks, 0 worsened tasks,
  0 strict recoveries, and 0 strict regressions versus ACCO lexical/structural.
  Semantic retrieval therefore remains optional augmentation; this release
  does not claim an independent recall gain from embeddings.
- **Preserved evidence boundaries.** Holdout #16 remains burned diagnostic
  evidence and #17 is now burned after its canonical first run. The new
  measurements validate retrieval and bounded packing only; they do not create
  a production-dollar or end-to-end cost-per-success claim.

# 1.16.0 - 2026-09-24

- **Added `acco trial` and `acco learn`.** `trial` runs a local,
  history-isolated baseline-vs-ACCO comparison against committed `HEAD` with
  independent verifier commands and explicit non-publishable evidence labels.
  `learn` analyzes local Claude session evidence to rank concrete context,
  output, duplicate-read, retry, cache, and always-on-context opportunities
  without turning estimates into savings claims.
- **Made ACCO embeddable in custom agents through Python and TypeScript SDKs.**
  The in-process Python `AccoEngine` and framework-neutral middleware expose
  provider-request optimization, recoverable context/output optimization,
  deterministic model routing, exact recovery, and browser-context focusing.
  The typed `@acco-ai/sdk` client talks to the same Python engine through the
  loopback-only `acco sdk-serve` bridge instead of duplicating optimization
  logic in JavaScript.
- **Broadened provider-boundary interception while keeping retrieval first.**
  ACCO now recognizes Anthropic Messages, OpenAI Chat Completions / Responses,
  and Gemini generateContent/streamGenerateContent shapes; optimizes nested
  provider tool schemas and explicit historical tool/function outputs only;
  preserves current user instructions and fresh source context; forwards
  provider responses byte-for-byte; and records optional content-free
  provider-reported token/model usage separately from transcript billing
  counters. TypeScript clients can opt into fail-open provider `fetch`
  interception without changing provider base URLs.
- **Expanded browser/context-payload optimization where it naturally fits.**
  Captured HTML, accessibility/ARIA snapshots, browser-shaped JSON trees, and
  embedded AX snapshots can be query-focused with rarity-weighted relevance,
  bounded structural/actionable context, hidden/script/style-noise suppression,
  exact `tsr_...` recovery, minimum-size gating, and automatic routing from
  generic tool/provider contexts. Ordinary JSON remains on the generic context
  path; ACCO still does not navigate, fetch URLs, execute page JavaScript, or
  inspect screenshot pixels.
- **Kept release evidence conservative.** The new SDK/provider/browser surfaces
  are covered by the Python 3.10/3.12/3.13 matrix, TypeScript strict
  typechecking/runtime/package checks, frozen retrieval holdout, ranking
  regression, semantic HNSW parity, Rust fastpath parity, and frozen CLI corpus
  gates. These mechanism tests do not create a new universal token- or
  cost-per-success claim.

- **Froze semantic holdout #15 ground truth.** Expected files come mechanically
  from each issue's merged upstream fix; the 24 frozen queries are unchanged.
  13 tasks are eligible, 8 are identifier-bearing and reported separately, and 3
  have no establishable target. `VALIDATION.md` discloses that the ground truth
  was collected by the agent that developed #106-#109 and that four of the six
  repositories were used as regression guards during that work. No evaluation
  has been run yet.

- **Recorded a negative result for semantic symbol matching.** The optional
  `all-MiniLM-L6-v2` embeddings, fused with lexical symbol scoring, fixed 19
  expected symbols but broke 45 across 488 holdout cases, so no semantic
  symbol ranker was built. See `VALIDATION.md`.

- **Compact fitting for clipped sections.** When a file's section must be
  clipped to its budget, a compact form showing the head of every selected or
  credited symbol is tried and used only when it shows strictly more symbol
  evidence in no more tokens. External holdouts: scoped symbol recall
  89.17% -> 89.49%, 2 tasks improved, 0 regressed.

- **Backfill a wasted symbol slot without displacing evidence.** When one of a
  file's two symbol windows only repeats a child its container already renders,
  the next distinct definition is added as an `### additional source windows`
  block after the outline, so budget fitting clips it first. The primary
  selection is unchanged. External holdouts: scoped symbol recall
  88.75% -> 89.17%, 3 tasks improved, 0 regressed.

- **Exact identifier mentions and assignment-bound definitions.** A request that
  spells a function, method, or variable name in code form (`Get`, `get()`,
  `should_bind_json`) now credits that definition like an explicit
  `Container member` mention, so longer names containing it no longer win.
  Types, constructors, and members named like a type in the same file are
  excluded. The index also records Python module-level names bound to a call,
  CommonJS exports with a real value (not aliases), and named function
  expressions that are an export's value. `INDEX_VERSION` is now 13, so cached
  indexes rebuild. External holdouts: scoped symbol recall 87.26% -> 88.75%,
  8 tasks improved, 0 regressed.

- **Restored the self-benchmark to 100% file, symbol, and scoped symbol
  recall** (from 72% / 88% / 80% at 1.15.0) without regressing external
  holdouts. Three ranking changes: the `path` boost now counts only the file's
  own name, not shared directory terms; Python outlines lead with the module
  docstring summary and argparse option names count toward relevance; and
  ordinary files get 2/5 of the remaining pack budget (authoritative files keep
  3/5) so more ranked files fit. `INDEX_VERSION` is now 12, so cached indexes
  rebuild. Four benchmark tasks whose target code moved behind compatibility
  facades were repointed to its current home, which changes the manifest's
  ground-truth hash. `VALIDATION.md` records the 471-task external comparison
  and every rejected candidate.

# 1.15.0 - 2026-09-23

- **Rebranded the project as ACCO — AI Coding Context Optimizer.** The canonical
  repository, Python package, CLI, MCP/plugin identifiers, config/state names,
  environment variables, documentation, and source/Rust folder names now use
  the ACCO identity.
- **Renamed the PyPI distribution to `acco`.** Installation is now
  `pip install acco`; the import package and CLI are also `acco`.
- **Renamed canonical code folders and executables.** `src/acco` is now
  `src/acco`, `rust/acco_fast` is now `rust/acco_fast`, and the
  optional native module is `_acco_fast`.
- **Preserved frozen historical evidence.** Existing benchmark manifests keep
  their original ACCO identifiers and hashes; ACCO normalizes those
  legacy identifiers only when reading or replaying the frozen suites.

# 1.14.0 - 2026-09-22

- **Expanded managed setup/doctor/uninstall support from three to eight coding-agent hosts.**
  ACCO now manages Claude Code, Cursor, Codex, OpenCode, OpenClaw,
  Hermes Agent, GitHub Copilot CLI / VS Code, and Google Antigravity through
  host-specific adapters instead of assuming one universal MCP config shape.
- **Added host-native configuration paths where available.** OpenClaw uses
  `openclaw mcp set/unset` instead of rewriting JSON5 directly. Copilot CLI
  uses `copilot mcp add/remove`, while VS Code Copilot remains workspace-local
  through `.vscode/mcp.json`.
- **Preserved unrelated host configuration and added fail-closed ownership checks.**
  OpenCode refuses ambiguous sibling JSON/JSONC project configs, Hermes refuses
  unowned or structurally ambiguous `mcp_servers` entries, and Copilot CLI
  refuses to replace a user-owned `acco` server definition.
- **Made multi-host setup safer on mixed developer machines.** `--host all`
  now means all detected supported hosts rather than every product ACCO
  knows about. Copilot detection distinguishes its CLI/extension/MCP surfaces
  from a generic VS Code installation.
- **Extended capability reporting and documentation for the larger host matrix.**
  MCP support is declared explicitly per host while proprietary lifecycle hooks
  remain conditional/unknown unless ACCO can actually guarantee them.
- **Kept regression evidence unchanged.** The complete Python 3.10/3.12/3.13
  matrix, Rust/Python parity, semantic HNSW parity, ranking regression, frozen
  holdout, real CLI corpus capture, and both frozen CLI comparator suites pass
  on the release branch.

# 1.13.0 - 2026-09-22

- **Added a recoverable optimization platform across context surfaces.**
  Lossy transforms can now retain exact original bytes in a project-scoped,
  content-addressed SQLite store with `tsr_...` handles, SHA-256 verification,
  hard capacity, and no eviction. The contract is exposed through CLI/MCP and
  bridges Claude Bash-output compression while keeping the legacy paged-output
  interface.
- **Combined adaptive MCP disclosure with conservative tool-schema compression.**
  Selected catalogs can drop annotation-only metadata and shorten long
  descriptions while preserving tool/property identity, argument-construction
  fields, and recognized constraint sentences. Exact original catalogs remain
  recoverable; compression fails closed when recovery is unavailable.
- **Added a measured keep-or-revert optimizer, stable provider-prefix evidence,
  and an opt-in provider reverse proxy.** The optimizer edits only Token
  Saver-owned project config, backs up exact prior bytes, compares
  provider-reported tokens/turn, and can restore the previous config
  automatically. The local proxy is loopback-only by default, disables
  automatic upstream redirects, forwards provider responses unchanged, and
  composes recoverable request transforms with content-free prefix reuse
  accounting.
- **Added focused browser-context compression for captured HTML/AX-like text.**
  Query-neighborhood evidence and an interactive skeleton can replace large
  captured payloads only when the result is smaller and the full original is
  recoverable. ACCO does not fetch arbitrary URLs for this feature.

- **Expanded durable knowledge into progressive persistent project memory.**
  Typed decisions, bugfixes, conventions, guardrails, architecture notes, facts,
  and findings now share the existing evidence-backed store with tags,
  importance, related-memory ids, source-digest staleness, reuse metadata,
  gentle age decay, and bounded near-duplicate supersession. MCP callers use
  `memory_index` -> `memory_search` -> `memory_get` so discovery does not
  require loading full memory records.
- **Added adaptive MCP tool-surface disclosure.** The opt-in `adaptive`
  profile starts from seven core schemas and uses `discover_tools(query)` to
  activate bounded memory/retrieval/review/output/routing groups for the current
  task. The server advertises `listChanged=true`, returns exact selected
  schemas in the discovery result, and keeps `full` as the default explicit
  compatibility fallback. Project config supports `[mcp] profile` and
  `adaptive_max_tools`.
- **Kept memory and tool selection local and non-generative.** No raw
  conversation text is auto-harvested, no memory is silently injected into
  ordinary context packs, and adaptive tool selection is deterministic rather
  than delegated to another model.

# 1.12.0 - 2026-09-21

- **Added automatic capability- and cost-aware model routing.** The new
  `model-route` CLI and MCP `route_task` tool classify task type, complexity,
  and explicit high-risk domains, establish a conservative minimum capability,
  then choose the lowest projected one-turn cost only among models that satisfy
  that policy. The default profiled set is Haiku 4.5 / Sonnet 5 / Opus 5.
- **Added opt-in Claude prompt-hook routing intelligence and adoption telemetry.**
  `[model_routing] mode = "observe"` records decisions silently; `advisory`
  additionally injects a bounded recommendation for model-selectable
  subagents/orchestrators. The hook explicitly does not claim to switch Claude's
  active top-level model. Stop telemetry records route target versus actual model
  so adoption can be measured before any savings claim.
- **Kept model economics evidence bounded.** Routing cost compares fresh input
  plus the selected output-budget target using the freshness-gated built-in
  pricing registry. Local prompt-only token estimates are labeled as incomplete
  input evidence, and routing profiles are documented as conservative product
  policy rather than benchmark rankings of model quality.
- **Added quality-gated routing calibration.** Frozen paired experiments can now
  assign different models per randomized arm while keeping ACCO/config
  treatment identical, and record transcript-confirmed actual model ids.
  `model-route-calibrate` admits a cheaper lower-capability model only for an
  exact task/complexity/risk bucket after >=10 pairs across >=5 tasks, >=80%
  baseline success, zero lost baseline successes, complete blind A/B quality
  parity, independent hidden/post-agent verification, and fresh verified
  pricing. Rejected groups remain visible with explicit reasons.
- **Made calibration fail closed at runtime.** The loader rechecks hard sample,
  success, quality-delta, model-ordering, and evidence floors; malformed or
  below-floor calibration cannot relax routing. Claude hook routing falls back
  to the original static conservative policy when a local calibration artifact
  is invalid.

- **Added a centralized, packaged Claude pricing registry.** Current first-party
  standard/global rates are stored once with explicit source, verification date,
  freshness limit, canonical model ids, aliases, and cache-write/read columns.
  `acco pricing` exposes the registry and its provenance; operational
  `cost-advisor --rates builtin` fails closed when the registry is stale.
- **Added pricing-drift CI without making normal PRs depend on the network.**
  Deterministic CI validates schema and freshness on relevant changes, while a
  weekly/manual workflow also compares every packaged model's five price columns
  against Anthropic's official Markdown pricing table. Historical benchmark rate
  files remain explicit and frozen so upstream price changes cannot rewrite past
  cost evidence.

- **Added a measured Cost Intelligence / Efficiency Advisor.** The new
  `cost-advisor` command combines real always-on context measurements, Claude
  transcript usage/cache counters, output-budget telemetry, continuity/waste
  signals, and observed ACCO tool-context reductions into a transparent
  local efficiency score with explicit evidence coverage and prioritized next
  actions.
- **Kept dollars and savings evidence strict.** ACCO prices usage only
  from a user-supplied exact-model rate file, refuses to allocate mixed-model
  turns or unknown cache-write TTLs, and exposes partial pricing as partial.
  Estimated tool-context savings can be shown under a clearly labeled
  fresh-input-once counterfactual, but are never promoted to measured API-dollar
  savings or task-success evidence.

- **Added bounded multi-view semantic query fusion for long prompts.** The full
  user query remains authoritative, while long multi-clause prompts can add up
  to two deterministic subviews made only from exact vocabulary already present
  in the prompt. Per-view chunk rankings are fused with weighted reciprocal-rank
  evidence, reducing whole-prompt semantic dilution without generated synonyms,
  inferred identifiers, or repository-specific query expansion.
- **Kept semantic persistence and exact-source authority unchanged.** Each
  deterministic query view reuses the existing persistent query-vector cache;
  short prompts remain on the historical single-vector path, and final context
  still comes from current repository bytes. These mechanism tests do not make a
  new external semantic-recall claim: burned holdout #13 is not used for tuning,
  and a fresh no-identifier-leakage holdout #14 is required before publishing
  generalization results.

# 1.11.0 - 2026-09-21

- **Expanded CLI output compression from 12 to 40 built-in processors.**
  Dedicated Git, Docker, Kubernetes, Terraform, Helm, Pulumi, Cargo, Go,
  Maven/Gradle, lint/typecheck, and structured-query families now compress
  command-specific evidence while the existing failure-aware routing,
  critical-line recovery, and minimum-benefit gate remain authoritative.
- **Added regression ratchets for output quality and routing.** A hash-frozen
  40-case synthetic suite locks processor identity, required evidence,
  no-hallucination constraints, and minimum token-reduction floors. The suite
  passes 40/40 with 100% required-evidence preservation and 100% processor
  identity match on its representative fixtures.
- **Added provenance-backed real CLI compression evidence.** Three successively
  fresh corpora were captured and frozen before comparison/tuning. On untouched
  Git-focused corpus v3, ACCO measured 50.50% weighted estimated output
  reduction with 100% mechanically detected critical-line survival versus
  51.25% / 80% for the pinned ppgranger comparator. Git status led 62.90% to
  61.75%; Git log was within 1.42 percentage points. These controlled CLI
  measurements are not an end-to-end model/API cost-per-success claim.
- **Hardened Git and Go compression from burned-corpus findings.** Git log now
  compacts verbose commit metadata and stat summaries, Git status strips help
  prose while preserving branch/stage/path state, Git diff removes redundant
  patch boilerplate while retaining exact edits, and Go build/test keeps exact
  actionable diagnostics while dropping redundant package/pass chatter.

- **Added an opt-in Smart Tool Proxy for large Claude Code Reads.** Eligible
  unbounded source Reads can now pass through PreToolUse and be replaced at
  PostToolUse with a bounded evidence packet. A local/free Ollama model selects
  candidate line ranges, but ACCO validates the ranges and rehydrates
  exact code from the original file. Selector-generated prose is never
  forwarded to Claude.
- **Added deterministic failure fallback and exact-read recovery.** Missing,
  slow, or malformed local-model responses fall back to structural/lexical
  selection, while bounded Reads bypass proxying entirely for edit-grade source.
  The feature is disabled by default and records only content-free savings
  telemetry.

- **Strengthened semantic/vector discovery without tuning against burned
  holdout #13.** Semantic indexing now emits declaration-aware chunks carrying
  kind, parent and signature metadata in addition to overlapping fallback
  windows. File-level semantic evidence aggregates up to three non-overlapping
  hits instead of keeping only the single best chunk.
- **Removed lexical-rank double counting from hybrid fusion.** Semantic file
  rank is now independent of the already-applied BM25/structural rank, allowing
  semantically strong low-lexical files to receive the intended rescue boost.
  Semantic contributions remain bounded far below exact structural identity.
- **Added bounded post-semantic graph expansion.** Top semantic witness files
  can contribute a small one-hop provider/dependency boost, so a descriptive
  test/caller may surface a terse implementation without turning semantic
  retrieval into broad transitive graph traversal.
- **Recorded the evidence boundary from semantic holdout #13.** Its one fresh
  run (GitHub Actions `35537362040`) measured 50.00% hybrid-semantic file
  recall vs 45.45% ACCO lexical/structural and 40.91% trivial lexical
  across 22 eligible no-identifier tasks, with one semantic recovery and zero
  semantic regressions. That suite is now burned and is not used to tune or
  score the changes above; a future fresh #14 is required for a new
  generalization claim.


- **Froze semantic holdout #13 before consuming it.** Twenty-four public
  issue-derived behavior queries across six repositories were committed before
  target-file/fix lookup. A post-freeze leakage audit conservatively excludes
  two identifier-bearing tasks without rewriting them, leaving 22 eligible
  natural-language tasks. The final harness compares lexical/structural Token
  Saver, hybrid semantic ACCO, and a trivial distinct-term-overlap
  baseline under identical retrieval limits.
- **Made semantic evidence reproducible by model weights, not model name
  alone.** `ACCO_SEMANTIC_MODEL_REVISION` now participates in vector
  index paths, persisted metadata, and query-vector cache identity. Holdout #13
  pins `all-MiniLM-L6-v2` revision
  `bc57282bc374d33e0d6c4de27f12dc1c2a87f37a` and forces exact cosine for the
  canonical first run.
- **Added an explicitly confirmed one-shot semantic evidence workflow.** The
  first real run requires `RUN_SEMANTIC_HOLDOUT_13` and burns the suite for
  future tuning. It has not been run, so no new external semantic-recall or
  cost claim is made by this change.


# 1.10.0 - 2026-09-20

- **Promoted embeddings from file-level reranking to persistent chunk-level
  semantic discovery.** `--semantic` / `--embeddings` now derives overlapping
  source chunks from the versioned repository index, persists normalized vectors
  plus file/line/symbol coordinates in private SQLite state, caches exact query
  vectors, and incrementally re-embeds only changed file digests. Source text is
  never duplicated into the vector database.
- **Added deterministic lexical/vector fusion without weakening exact-source
  authority.** Chunk hits contribute bounded semantic-similarity and RRF-style
  rank evidence after BM25/structural/graph scoring. Exact structural symbol
  authority remains substantially stronger than fuzzy semantic affinity, and the
  final context pack is still rendered from current repository bytes rather than
  vector-store summaries.
- **Added optional persisted HNSW acceleration with exact-scan fallback.** The
  semantic database remains authoritative; when `hnswlib` is installed Token
  Saver builds a versioned HNSW sidecar from those vectors. Missing/stale ANN
  state falls back to exact cosine scan instead of changing retrieval semantics.
- **Added semantic index observability and integrity gates.** New
  `semantic-index` and `semantic-status` commands expose synchronized
  file/chunk counts, dimensions, backend and local path. Semantic refresh refuses
  to persist vectors if repository bytes changed after structural indexing,
  preventing cross-index evidence races.
- **Kept the evidence claim narrower than the feature.** Existing frozen
  retrieval/ranking gates continue to run with semantic retrieval disabled by
  default. Unit tests prove persistence, invalidation, warm model-free reuse,
  hybrid ranking evidence and exact-source rendering, but 1.10.0 does not claim
  improved external natural-language recall until a new no-identifier-leakage
  semantic holdout is frozen and run.


# 1.9.0 - 2026-09-20

- **Added safe opt-in pre-model prompt ingress staging.** Claude Code cannot
  replace a submitted prompt from `UserPromptSubmit`, so ACCO never
  pretends to do so. When `ingress.enabled` is explicitly enabled and a
  prompt crosses the configured token threshold, the hook blocks it before
  model processing, stores the exact original in private local state, and
  returns a stage id. `ingress-show` exposes a bounded exact head/tail packet
  and `ingress-read` recovers only requested exact line ranges. There is no
  fallback that silently keeps only the first N words.
- **Added persistent content-fingerprinted retrieval-result caching.** Completed
  context packs can now be reused across processes when repository content,
  retrieval configuration, changed-file evidence, feedback, and working-set
  state are identical. Source-digest/index-version changes automatically
  produce a different key; embeddings and custom ranking stages deliberately
  bypass the first cache version until their external state can be fingerprinted.
- **Added an optional Rust acceleration boundary with Python parity.** The
  separately buildable PyO3 extension accelerates the existing character-based
  token estimator, index identifier extraction, BM25 accumulation, identifier
  Jaccard similarity, and shared n-gram primitive. Python remains the reference
  and automatic fallback; CI builds the native wheel, runs Rust unit tests, then
  reruns pack/retrieval/context-quality checks with the native backend required.
- **Added Claude Code marketplace packaging.** The repository now exposes a
  command-source marketplace entry and a `claude-plugin-path` renderer that
  creates a complete plugin directory containing ACCO hooks, MCP config,
  and an ingress-resume skill. Generated commands use
  `python -m acco.entry` so the plugin does not depend on the console
  script being present on `PATH`. Existing pip + `acco setup`
  remains the multi-host installation path.


- **Added opt-in knowledge-assisted read avoidance.** The PreToolUse source
  guard can now replace an unbounded full-file Read with compact verified findings
  anchored to that exact unchanged file. Stale, superseded, probable/speculative,
  ranged, allowlisted, and non-source reads never qualify, and the replacement
  explicitly routes edits/verification back to bounded exact source ranges.
- **Added cache-aware rewrite economics.** A pure `cache_economics` policy and
  `cache-economics` CLI model cached-prefix reuse separately from the uncached
  frontier, including the penalty when a transformation recreates cached history.
  Provider/model ratios are configurable rather than presented as universal
  pricing. The runtime gate remains opt-in.
- **Added a frozen causal knowledge-efficiency holdout.** The new 24-task ×
  3-trial SWE-bench Verified design gives both arms the same explicit verified
  phase-1 findings and a fresh phase-2 session; continuity, cross-turn dedup, and
  waste detection are disabled in both arms. Only knowledge read avoidance plus
  its cache-economics gate differ. A paid/manual 144-arm-run / 288-Claude-phase
  workflow, independent verification, blind grading, cache-TTL-aware pricing,
  and task-cluster cost-per-success gate are checked in. The paid run has not
  been executed, so **no knowledge-efficiency savings percentage is claimed**.

- **Added durable evidence-backed project knowledge.** New
  `remember`, `recall`, and `knowledge-status` commands plus matching MCP
  tools persist explicit claims with evidence/applicability/confidence and real
  repository anchors. Anchor content hashes are revalidated at recall time, so
  changed/missing source automatically quarantines stale findings; explicit
  supersession and exact-identity deduplication prevent obsolete conclusions
  from silently accumulating.
- **Added progressive MCP schema profiles.** `ACCO_MCP_PROFILE` can
  advertise `minimal`, `context`, or the backward-compatible `full` tool
  surface. Unknown profiles fail closed. This reduces recurring MCP tool-schema
  context for hosts that only need repository context + durable knowledge
  instead of diff/output specialist tools.
- **Kept the new memory layer outside existing retrieval claims.** Durable
  findings are explicitly written/recalled rather than automatically harvested
  from conversation or injected into normal context packs, preserving current
  frozen retrieval behavior while creating a separate surface for future causal
  cross-session savings evaluation.

# 1.8.0 - 2026-09-20

- **Added a frozen causal holdout for the session-efficiency bundle.** The new
  `session-efficiency-swebench-24.frozen.json` reuses the existing 24 frozen
  SWE-bench Verified tasks at the same revisions/hidden tests and runs three
  randomized trials per task. Both arms install the same current ACCO
  binary; the control disables only continuity/dedup/waste switches while the
  treatment enables them, avoiding version/retrieval/output-processor
  confounding.
- **Made continuity exposure deterministic.** Every benchmark arm now runs an
  investigation-only Claude phase, verifies that phase did not modify
  repository state, invokes the real `SessionStart:resume` ACCO hook,
  then starts a fresh Claude implementation session. This gives both arms the
  same two-session cost while only the treatment receives structured
  continuity context.
- **Added independent session metrics and a strict publication gate.** Raw
  transcripts independently measure total tool calls, input tokens, repeated
  Bash commands, identical-failure retries, and duplicate Reads. ACCO's
  local efficiency ledger is used only for feature-activation evidence. The
  evaluator reports task-cluster bootstrap intervals and refuses a publishable
  claim unless success/quality are preserved, control contamination is zero,
  continuity fires for every treatment arm-run, all session feature families
  activate somewhere, cost evidence is complete, and cost-per-success has a
  strictly positive 95% CI lower bound.
- **Added resumable benchmark CLI/workflow surfaces.** `session-holdout` runs
  experiment → blind grade → analysis; `session-holdout-evaluate` evaluates
  already merged evidence. A dedicated paid GitHub workflow preflights the
  frozen 24×3 design, runs a paid two-arm smoke, shards all 144 arm-runs
  (**288 Claude task phases**), blind-grades all 72 pairs, and publishes only
  when the strict session gate passes. Merging this release alone makes no
  savings claim.

# 1.7.0 - 2026-09-20

- **Added a modular session-efficiency control plane.** Claude hooks now retain a
  bounded structured working checkpoint across resume/compaction, including task
  class, working file paths, recent redacted command labels, failures, and
  validation status. The checkpoint deliberately stores no raw user prompt,
  assistant response, or tool output and is exposed through `acco
  continuity`.
- **Added exact cross-turn deduplication and behavioral waste guards.** Repeated
  identical Bash output for the same command can collapse to a recoverable
  stub, unchanged repeated full-file Reads are blocked, and bounded detectors
  surface repeated-command, identical-failure retry-loop, and no-edit
  tool-cascade signals. Each behavior has independent project/environment kill
  switches.
- **Expanded command-aware output compression without weakening failure safety.**
  The existing processor registry now covers git status, grep/ripgrep/find,
  Ruff/ESLint/Pylint/Clippy, tsc/mypy/pyright, Go/Cargo tests, common build
  systems, Python package installs, and Docker/Kubernetes logs in addition to
  the existing pytest/Jest/git-log/install families. Unknown failures still
  pass through conservatively and registry-wide critical-line recovery remains
  the final safety layer.
- **Added local savings dashboards and frozen output-quality evidence.**
  `acco dashboard` exposes terminal/JSON reporting and can write a
  dependency-free local HTML dashboard. Estimated tool-context savings,
  continuity restores, behavioral signals, and exact transcript usage stay
  explicitly separated; the dashboard is not a cost-per-success claim. CI now
  enforces a hash-frozen multi-family output fixture with exact preservation,
  minimum-reduction, and no-hallucination contracts while retaining the
  existing frozen retrieval holdout and ranking-regression gates.

# 1.6.0 - 2026-09-20

- **Completed the output-cost evidence feature from agent run through publication
  gate.** Added deterministic balanced blind A/B response grading with strict
  rubric JSON, resumable grading checkpoints, hashed audit records, and a
  no-side-effect Claude judge adapter. Added `evidence-run` to compose frozen
  randomized paired experiments, independent hidden verification, blind grading,
  cache-TTL-aware cost-per-success analysis, and quality-gated adaptive-budget
  calibration in one resumable command.
- **Productized the real frozen 24-task × 3-trial evaluation path.** The existing
  SWE-bench Verified workflow now performs a paid agent+telemetry+judge smoke
  before fan-out, runs the 144 agent calls, merges shard evidence, blind-grades
  all 72 pairs, enforces the strict output-effectiveness publication gate, and
  emits the learned calibration artifact. Manual workflow dispatch requires an
  explicit `RUN_144` confirmation. No new savings percentage is claimed until
  that paid workflow actually completes and passes.
- **Closed benchmark plumbing gaps exposed by the end-to-end pipeline.** Docker
  agent runs now persist ACCO telemetry through an explicit mounted state
  directory; shard merging preserves grader/evidence metadata; the grader treats
  responses as untrusted data and runs with shell/filesystem/web tools denied.

- **Added joined output-effectiveness evidence and closed the experiment-analysis
  condition gap.** Paired experiments now embed exact transcript usage
  (fresh input, cache creation split by 5-minute/1-hour/unknown TTL, cache
  read, output, model calls, tool calls) for every run
  and isolate enabled-arm ACCO state per artifact. When Claude hook
  telemetry is available, enabled runs also embed selected output task/mode/
  budget plus a telemetry-vs-transcript integrity check. New
  `output-effectiveness` joins those measurements with independently verified
  task success, blind response-quality parity, cache-TTL-aware token pricing,
  budget cohorts, and a task-cluster bootstrap CI to gate cost-per-success
  claims. The gate requires >=20 tasks, >=3 trials/task, no success/quality
  regression, complete matching policy telemetry, complete cache-TTL-aware cost evidence,
  a positive cost-per-success reduction, and a task-cluster 95% confidence
  interval whose lower bound remains above zero. `agent-evaluate`, `cost-report`, and
  `output-calibrate` now accept the experiment-native `enabled` condition as
  an alias for `acco`, so raw experiment artifacts no longer require
  manual condition rewriting.

- **Added automatic content-free output-budget telemetry.** Claude Code setup now
  registers `Stop` and `StopFailure` hooks. `UserPromptSubmit` checkpoints the
  transcript byte offset and active policy, then turn completion reads only the
  appended transcript usage counters and records real input/cache/output tokens,
  model calls, task/mode, selected budget, complexity/calibration metadata, and
  API-failure status. Prompt text, assistant text, tool payloads, and copied
  transcript content are never written to telemetry. `output-telemetry` reports
  budget utilization by task/mode plus explicitly observational underuse/overrun
  signals; it does not equate a completed turn with task success or quality.
  Storage is project-scoped, private, and bounded to the newest 2,000 records
  after the telemetry log exceeds 4 MiB. Set `output.telemetry = false` or
  `ACCO_OUTPUT_TELEMETRY=0` to disable capture.

- **Added adaptive, quality-calibrated generation budgets.** Automatic output
  policy now scales task/mode bases using deterministic prompt complexity
  signals while preserving hard mode bounds and stable budgets across vague
  follow-ups. New `output.adaptive`, min/max clamp, and calibration-file
  settings are available with environment overrides. `acco
  output-calibrate` learns task/mode base budgets only from blinded paired runs
  where both arms succeed and correctness, safety, weighted quality, and blocker
  constraints remain at parity; at least three valid samples spanning three distinct task IDs are required.
  Recommendations use observed p90 output tokens plus a configurable safety
  margin. Failed, blocked, unblinded, or degraded short responses cannot train
  the controller.

- **Made generation-time output control automatic for Claude Code.**
  `UserPromptSubmit` now deterministically classifies strong coding, debugging,
  review, planning, and explanation prompts and injects the task-aware response
  policy before generation. Ambiguous follow-ups inherit the active session
  policy without another full injection; task/mode changes and clear/compact
  resets re-inject it. Explicit terse/detailed requests override the configured
  mode. New `[output]` project settings and environment overrides control the
  feature, and only resolved task/mode/budget metadata is stored locally — user
  prompt text is not persisted. The generated Claude token-budget skill is also
  synchronized with the checked-in template.

- **Made Output Saver generation policy task-aware and quality-gated.**
  `output-policy --task` now adapts default budgets and response constraints for
  coding, debugging, review, explanation, and planning while preserving the
  historical general-mode budgets. The policy now explicitly removes
  conversational preambles, tangents, recaps, closing filler, repeated progress
  narration, and unchanged code while keeping explicit output contracts,
  diagnostics, safety information, and material caveats as hard escape hatches.
  Debugging mode separates observations from hypotheses so brevity cannot justify
  an invented root cause. `agent-evaluate` can now consume optional blind
  response-quality scores and reports generated-output-token reduction only when
  task success and quality remain at parity; unblinded quality evidence cannot
  authorize a savings claim. Agent evaluation now pairs by task + trial,
  supports repeated paired runs, reports output tokens per success plus
  deterministic paired bootstrap intervals, and returns explicit
  `claim_blockers`. Raw reductions remain observable, but missing blind quality
  evidence now prevents `claim_allowed=true`.

- **Closed the remaining documentation completeness gaps.** Added a reproducible
  end-to-end bug narrative, 48 dedicated command-reference pages with flags,
  exit semantics, and machine-output links, explicit JSON CLI contracts, merged
  top-level `--help` discovery, and a holdout query-construction protocol that
  separates semantic natural-language evaluation from identifier-bearing
  lookup. Documentation tests now enforce those surfaces and keep the known
  validation limitations visible.


# 1.5.0 - 2026-09-20

- **Made file reranking an explicit extension surface.** Ranking now composes
  deterministic scoring with a validated ordered `RankingStageRegistry`; graph
  closure, embeddings, and future/custom rerankers no longer require branches
  inside `rank_files()`.
- **Added ranking observability and causal regression analysis.** Optional
  `RankingScoreEvent` traces expose exact score transitions without changing
  default ranking cost or legacy reasons. `ranking-explain`,
  `ranking-snapshot`, and `ranking-diff` provide stage-attributed diagnostics,
  including expected files that fall below the ordinary top-N display window.
- **Added PR ranking-regression evidence and empirical gate calibration.** Pull
  requests compare immutable base/candidate snapshots, publish GitHub summaries,
  and retain raw evidence. Weekly/manual calibration deduplicates reruns, selects
  the newest artifact per PR, isolates frozen ground-truth cohorts, and reports
  empirical rank-drop/disappearance distributions without inventing a blocking
  threshold.
- **Productized host onboarding and lifecycle management.** Added `acco
  setup`, `doctor`, `uninstall`, `commands`, and shell `completion`.
  Setup auto-detects Claude Code, Cursor, and Codex, merges only Token
  Saver-owned MCP/hook entries, creates project `.acco.toml`, and is
  idempotent so rerunning it after upgrades repairs managed configuration.
  Uninstall removes only managed entries and preserves modified/unrelated host
  configuration.
- **Added project-scoped runtime configuration.** The Claude hook and large-read
  guard now resolve the nearest `.acco.toml` for guard/read/output/Delta
  settings while keeping `ACCO_*` environment variables as higher-
  priority overrides. Guard allowlists now support repository-relative globs.
- **Added consolidated integration health checks.** `acco doctor`
  reports package/CLI availability, project config, detected/configured hosts,
  repository-index health, and available Claude transcript evidence in one
  human- or JSON-readable result.
- **Rebuilt the documentation as a tested product surface.** Added a docs hub,
  five-minute quickstart, complete CLI map, canonical configuration reference,
  troubleshooting playbook, upgrade/migration guide, contributor guide, and
  security/privacy reference. CI now checks package/document version parity,
  internal Markdown links, and coverage of every shipped CLI command.



# 1.4.0 - 2026-09-19

- **Added a pluggable, failure-aware Bash-output processor registry.** The existing
  `filter_command_output` API now routes through format-specific processors for
  pytest, Jest/Vitest, `git log`, and npm/pnpm/yarn/bun installs, with a
  conservative generic fallback. Processors must explicitly opt into failed-command
  handling; unsupported failures are not forced through success-oriented
  compression. A final ratio gate rejects rewrites that do not save enough output.
- **Added registry-wide critical-diagnostic recovery and replayable quality
  contracts.** A shared recovery pass can restore omitted error, traceback,
  assertion, and source-location lines after processor compression.
  `acco output-replay` evaluates captured output against exact
  `must_preserve` strings, optional token budgets, and minimum reduction
  requirements, returning nonzero on contract failure. `acco
  output-explain` exposes processor and failure-routing decisions.
- **Added opt-in graph-aware diagnostic Delta for repeated pytest and Ruff runs.**
  With `ACCO_DELTA=1`, repeated diagnostics are classified as NEW,
  CHANGED, UNCHANGED, or RESOLVED. New/changed diagnostics are mapped through the
  repository index to the containing symbol and nearby dependency/call-graph
  edges when possible. Delta stores only a bounded structured diagnostic
  inventory in local session state and replaces the normal compressed fallback
  only when the rendered delta is smaller.
- **Documented the output subsystem as an explicit safety boundary.**
  `OUTPUT_OPTIMIZATION.md` now describes processor extension contracts,
  failure routing, critical-line recovery, replay manifest semantics, Delta
  privacy/state rules, Claude Code hook flow, configuration, and validation
  limits.
- **Canonical fresh Holdout #12 reached 100% across all retrieval/identity
  metrics on the predeclared larger design.** The first and only fresh run covers
  72 tasks across 12 unseen repositories and 6 languages: 72/72 file, bare,
  scoped, qualified, and exact symbol-identity recall. Mean estimated context
  reduction is **94.30%**, which is reported unchanged and remains below the
  previously proposed >=97% efficiency target. The suite is burned for tuning.

- **The large-file guard now covers `cat` through Bash.** A lone `cat <large source
  file>` was a full dump that bypassed the Read guard (seen in a paired Sonnet 5 run,
  +$0.04 per run). It is now denied with the same outline; pipes, redirects, chains,
  globs and other commands are untouched. `acco install` registers the
  PreToolUse hook for `Read|Bash`, so re-run it to pick this up.
- **Added a large-output demo** (`examples/large_output_demo/`): a generated project
  whose verbose test run and large module trigger both ACCO savings paths
  (98% and 86% fewer tokens, checked deterministically), plus a paired Claude Code
  runner and an honest 3-trial write-up in which the saving depends on the model
  running the noisy command untruncated.
- **Fixed SWE-bench grading in the experiment harness.** Captured agent patches
  keep their trailing newline (previously stripped, so `git apply` rejected every
  patch as corrupt). Agent edits to files the hidden test patch modifies are
  removed before verification instead of making the hidden tests fail to apply.
  Success is now per test: all `fail_to_pass` tests pass and nothing that passed
  on the unpatched reference regresses, rather than the exit code of the whole
  test command, which pre-existing image errors could make unsatisfiable.

- **Added executable broad cost-per-success experiments.** A new `experiment`
  command runs randomized paired baseline/enabled trials in clean pinned Git
  worktrees, applies a hard hook kill-switch to the baseline arm, installs
  project hooks only for the enabled arm, executes independent verifier
  commands, captures real transcripts, and checkpoints after every run. The
  transcript benchmark now exposes task-clustered 95% bootstrap intervals and a
  publication gate requiring frozen task definitions, at least 20 distinct
  tasks, at least three paired trials per task, one exact model ID, randomized
  arm order, and no manual intervention. Small development experiments remain
  supported but are explicitly not publishable evidence.

# 1.3.1 - 2026-09-19

- **Made release artifacts provenance-safe.** Release automation now treats a
  version as immutable: it no-ops once the corresponding GitHub release exists,
  refuses to reuse an already-reserved tag for a different commit, serializes
  concurrent release attempts, creates the version tag before publishing, and
  publishes to PyPI before creating the GitHub release. A retry after a partial
  failure is safe through the pinned tag plus PyPI's `skip-existing` behavior.
- **Renamed the PyPI distribution to `acco`.** PyPI rejects
  `acco` as too similar to the unrelated existing `tokensaver`
  project. The Python import remains `acco` and both CLI entry points
  remain `acco` / `acco-pack`.
- **Hardened CI and ranking maintainability after 1.3.0.** The ranking core was
  decomposed into addressable scoring stages without retuning, correctness-
  focused Ruff and actionlint gates were added, and the historical external
  holdout is now enforced as an explicit regression floor including scoped
  symbol recall.

# 1.3.0 - 2026-09-19

- **Hardened the four failure classes exposed by frozen holdout #11.**
  JS/TS parsing now keeps structurally valid declarations around isolated
  Tree-sitter `ERROR` nodes instead of degrading an entire file to generic
  regex extraction, preserving interface members such as generic
  `Slice.getSelectors` and `Slice.injectInto`. File ranking now gives
  stronger parser-backed authority to an explicit `Container member` pair and
  uses callable-signature evidence to distinguish same-named top-level
  functions; exported top-level API declarations receive a small bounded edge
  over equivalent file-local helpers. Overload ranking now removes terms
  explicitly negated by `without ...` from positive lexical evidence and
  applies a decisive same-family penalty when an overload still carries the
  excluded parameter. These changes target general failure classes rather than
  holdout task IDs, with synthetic regressions for partial TypeScript parsing,
  interface-member identity, Java negative-parameter overloads, cross-file
  same-name top-level TypeScript functions, and Go receiver/member authority
  under many `context.WithTimeout` call sites. The repository index version is
  bumped so persisted indexes cannot retain the old JS/TS fallback records.
  Holdout #11 remains burned. A single development-only rerun of the
  frozen suite (run 35399929752) reached **100% file, bare, scoped, qualified,
  and exact identity recall across all 60 tasks**, with **99.71% mean context
  reduction** and zero remaining misses. This is regression confirmation only
  and does not replace the preserved 88.33% exact fresh first-run evidence.

- **Built and first-ran an eleventh frozen external holdout after C# 14 extension-block support.**
  `benchmarks/holdout-external-11.json` contains **60 source-grounded tasks
  across 10 previously-unused repositories**: .NET Runtime and EF Core (C#),
  Spring Framework and Apache HttpComponents Core (Java), Redux Toolkit and
  Vitest (TypeScript), tracing (Rust), go-redis and gRPC-Go (Go), and SQLAlchemy
  (Python). The suite deliberately includes real C# 14 `extension(...)` blocks
  outside RestSharp, dense Java overload families, TypeScript overloads and
  implementation signatures, Rust same-name span members, Go receiver methods,
  and Python class methods in very large source files. All repositories are
  pinned to exact revisions. Ground truth was committed before evaluation and
  frozen at SHA
  `011dffedad4fe5ea99400cc58655850dcf43f38b3664b9219b4f5cf92a7f94ec`.

  Run `35395304893` is the **first and only fresh evaluation** of that frozen
  manifest. It completed successfully with the holdout protocol enforced.

  **First-ever result: 96.67% file recall, 96.67% bare symbol recall, 93.33%
  symbol recall in expected files, 91.67% qualified-symbol recall, 88.33% exact
  symbol-identity recall, and ~99.71% estimated context reduction.** Six
  repositories scored 100% across file/bare/scoped/qualified/exact: .NET
  Runtime, EF Core, Spring Framework, tracing, gRPC-Go, and SQLAlchemy. The two
  fresh C# repositories therefore provide independent confirmation that C# 14
  extension-block extraction generalizes beyond the RestSharp development case.

  The remaining misses are concentrated rather than broad: HttpComponents Core
  has 100% file/bare/scoped/qualified recall but 66.7% exact identity inside a
  dense `EntityUtils.toString` overload family; Redux Toolkit reaches 100%
  file but 83.3% bare, 66.7% scoped and 50% qualified/exact on its selected
  TypeScript callable families; go-redis misses one of six Client tasks at the
  file-selection stage; and Vitest misses one expected file while still
  retaining 100% bare-name recall. The exact untouched result is preserved in
  `benchmarks/holdout-external-11.result.json`. Holdout #11 is now burned for
  tuning.

- **Added compatibility extraction for C# 14 extension blocks.**
  The published `tree-sitter-c-sharp 0.23.x` grammar predates
  `extension_declaration`, so modern source shaped as
  `extension(Receiver receiver) { ... }` could preserve the outer class while
  dropping every inner method from ACCO's callable index. ACCO
  now performs a narrow balanced-source recovery pass for those blocks: it
  masks comments and string/character/raw literals, finds only top-level
  extension members, preserves the enclosing class as the qualified parent,
  carries the receiver text into the structural signature, and records exact
  declaration identity lines. Recovered symbols are deduplicated against
  parser-native symbols so a future grammar release can supersede the
  compatibility path without duplicate callables. The repository index version
  is bumped to invalidate stale C# records. Synthetic regressions cover
  overload identity, generic methods, expression-bodied methods, receiver
  evidence, and false-positive protection inside comments/strings. Holdout #10
  remains burned and any rerun is development evidence only. A development-only
  rerun of that burned suite moved bare recall from 89.6% to 100%, scoped recall
  from 87.5% to 100%, qualified recall from 87.5% to 100%, and exact identity
  from 87.5% to 100%; file recall remained 100% and context reduction remained
  ~98.98%. RestSharp specifically moved from 16.7% bare and 0%
  scoped/qualified/exact to 100% on all retrieval and identity metrics. These
  numbers are regression diagnostics, not independent generalization evidence.

- **Built and first-ran a tenth frozen external holdout after callable-identity v5.**
  `benchmarks/holdout-external-10.json` contains **48 source-grounded tasks
  across 8 previously-unused repositories**: RestSharp and Shouldly (C#),
  Mockito and Apache Commons Collections (Java), the MongoDB Node.js driver and
  TanStack Query (TypeScript), futures-rs (Rust), and GORM (Go). The suite
  stresses overload parameter shapes, TypeScript overload signatures versus
  implementations, lower-case container members, trait methods, and a single
  Go receiver type split across multiple source files. All repositories are
  pinned to exact revisions. Ground truth was committed before evaluation and
  frozen at SHA
  `685ac9b9ca60fa02ea2ad797c7b768ee47790b015b9baaff447a74d37c1209f7`.
  A separate hash-only workflow computed and verified the freeze hash without
  cloning benchmark repositories or performing any evaluation.

  **First-ever result: 100% file recall, 89.6% bare symbol recall, 87.5% symbol
  recall in expected files, 87.5% qualified-symbol recall, 87.5% exact
  symbol-identity recall, and ~98.98% estimated context reduction.** Seven of
  eight repositories scored 100% on every retrieval/identity metric:
  Shouldly, Mockito, Commons Collections, MongoDB, TanStack Query, futures-rs,
  and GORM. RestSharp scored 100% file recall but 16.7% bare symbol recall and
  0% scoped/qualified/exact recall on its six C# extension-member tasks.

  Holdout #10 therefore provides fresh evidence that the callable-identity v5
  work generalizes across Java overload families, TypeScript overload
  declarations/implementations, Rust trait members, and Go receiver methods.
  It also exposes a sharply isolated remaining frontier around the modern
  RestSharp C# extension-block source shape: the correct source file is found,
  but the expected extension members are not retained as parser-backed callable
  evidence. The exact untouched first-run output is preserved in
  `benchmarks/holdout-external-10.result.json`. Holdout #10 is now burned for
  tuning.

- **Hardened exact callable identity after holdout #9 exposed lower-case
  member and overload-shape blind spots.** Container/member detection now treats
  member casing as language-specific, so structural hints such as
  `StringUtils split`, `SelectQueryBuilder select`, `ClassTransformer
  instanceToPlain`, and `Sender send` receive the same parser-backed
  authority that PascalCase C# members already had. JS/TS symbols now retain
  structural kinds (function/method/constructor/class/interface/type), with an
  index-version bump so persisted indexes cannot keep the old generic kind.
  Overload ranking also uses explicit zero/one-parameter wording, positive or
  negative array intent, excluded parameter terms, and declaration-vs-
  implementation shape when a TypeScript-style overload family contains both.
  Explicit package/module/top-level requests now prefer top-level definitions
  over same-named receiver/class members. These changes are covered by new
  cross-language synthetic regressions; holdout #9 remains burned and is not
  reused as fresh evidence. A development-only rerun of that burned suite moved
  scoped recall from 87.5% to 95.8%, qualified recall from 85.4% to 95.8%, and
  exact identity from 70.8% to 93.75%, while file recall stayed at 100% and
  context reduction stayed ~97.63%. These numbers are regression diagnostics,
  not independent generalization evidence.

- **Built and first-ran a ninth frozen external holdout under the stricter scoped-symbol metric.**
  `benchmarks/holdout-external-9.json` contains **48 source-grounded tasks
  across 8 previously-unused repositories**: NLog and FluentAssertions (C#),
  Caffeine and Apache Commons Lang (Java), TypeORM and class-transformer
  (TypeScript), Tokio (Rust), and Logrus (Go). The suite targets dense overload
  families, giant source files, declaration-vs-implementation overloads,
  same-name members in different containers, and same-name symbols in different
  files. All repositories are pinned to exact revisions. Ground truth was
  committed before any evaluation and frozen at SHA
  `5c07f59e7a96bb7b6c97764c02aecae2e7597afe6be25b84f95a8154617d7ecf`.

  The initial workflow attempt stopped before evaluating any task because the
  repositories were cloned one directory above the manifest-relative paths.
  Only the workflow clone destinations were corrected; the frozen manifest and
  hash were unchanged. Run `35385165759` is therefore the **first actual
  evaluation** of the frozen ground truth.

  **First actual result: 100% file recall, 95.8% bare source-visible symbol
  recall, 87.5% symbol recall in expected files, 85.4% qualified-symbol recall,
  70.8% exact symbol-identity recall, and ~97.63% estimated context reduction.**
  Per repository file/bare/scoped/qualified/identity recall:
  NLog 100/100/100/100/100, FluentAssertions 100/100/100/100/100,
  Caffeine 100/100/100/100/100, Commons Lang 100/83.3/66.7/66.7/50,
  TypeORM 100/100/83.3/83.3/33.3, class-transformer
  100/83.3/83.3/83.3/33.3, Tokio 100/100/83.3/66.7/66.7, and Logrus
  100/100/83.3/83.3/83.3.

  This is the first untouched external suite created after
  `symbol_recall_in_expected_files` was added. It confirms why the scoped
  metric matters: bare-name recall can remain high when a same-named symbol is
  selected from the wrong file or container. File retrieval remains perfect on
  this suite; the exposed frontier is exact overload/declaration identity,
  especially TypeScript overload declarations/implementations, very large Java
  overload families, and same-leaf container resolution in Rust. The first-run
  result is preserved in `benchmarks/holdout-external-9.result.json`.
  Holdout #9 is now burned for tuning.

- **Built and first-ran an eighth frozen external holdout focused on adversarial callable resolution.**
  `benchmarks/holdout-external-8.json` contains **48 source-grounded tasks
  across 8 previously-unused repositories**: FluentValidation and Polly (C#),
  Guice and Retrofit (Java), class-validator and tsyringe (TypeScript), Rayon
  (Rust), and Viper (Go). The suite deliberately stresses overload families,
  partial classes, generic arity, nested builders, interface/trait members,
  async/sync twins, and package-level functions sharing names with receiver
  methods. All repositories are pinned to exact revisions. Ground truth was
  committed before evaluation and frozen at SHA
  `ea638a0cf9a5777ac5799982a728b6f895aaa952cf7b9f04a714991650c0d7ab`.

  **First-ever result: 100% file recall, 97.9% bare source-visible symbol
  recall, 91.7% qualified-symbol recall, 81.25% exact symbol-identity recall,
  and ~95.31% estimated context reduction.** Per repository
  file/bare/qualified/identity recall: FluentValidation 100/83.3/83.3/83.3,
  Polly 100/100/100/100, Guice 100/100/100/100, Retrofit
  100/100/83.3/83.3, class-validator 100/100/100/50, tsyringe
  100/100/100/66.7, Rayon 100/100/100/100, and Viper
  100/100/66.7/66.7.

  The suite validates the post-Dapper partial-class and overload work on fresh
  repositories: file retrieval is perfect and exact declaration identity
  crosses 80% on an intentionally overload-heavy benchmark. The remaining
  misses are concentrated in TypeScript overload declaration identity,
  package-level-vs-receiver disambiguation in Go, and isolated nested/member
  selection cases. The exact first-run output is preserved in
  `benchmarks/holdout-external-8.result.json`. Holdout #8 is now burned for
  tuning.

- **Fixed six issues found in review of the recent structural-ranking and
  cost-report changes, each with a regression test that fails on the previous
  source.**
  1. *One pathological file no longer aborts indexing.* Deeply nested generated
     sources (JS/Go/Rust/Java/C#, and Python via `ast`) raised `RecursionError`
     from the recursive tree walkers and killed whole-repo indexing.
     `syntax.symbols()` now converts it to a `ValueError`, the Python extractor,
     outline and signature rendering tolerate it, and the file falls back to
     generic extraction. A missing tree-sitter grammar likewise degrades import
     extraction to the regex path instead of raising `ImportError`.
  2. *Structural file authority is narrower and cheaper.* It no longer fires on
     generic callable names defined in more than three files (`get`, `add`),
     is applied before the low-value-directory dampening so tests/examples no
     longer keep an undampened boost, and the query terms, explicit
     container/member pairs and per-name file counts are computed once per
     query instead of once per file.
  3. *Explicit `Name<T>` generic arity now works.* The regex was double-escaped
     inside an rf-string, so `QueryAsync<T>` in a query never set a requested
     arity; only the "two input types ... return type" wording did.
  4. *`cost-report` no longer keeps the last run for duplicate task ids.* Runs
     pair on `(task_id, trial)`; an optional `trial` field supports repeated
     attempts, true duplicates raise with a pointer to `trial`, and the report
     prints a seeded 95% cluster-bootstrap interval over tasks (or `n/a` for
     fewer than two tasks), so a handful of tasks is not read as a precise
     saving.
  5. *Bare-name symbol recall can be checked against the expected files.* The
     evaluator adds `symbol_recall_in_expected_files` (and its mean in the
     summary): a same-named symbol in an unrelated file no longer counts toward
     it. The existing bare `symbol_recall` is unchanged, so frozen holdout
     numbers stay comparable.
  6. *Missing-grammar robustness only.* Tree-sitter grammars remain hard
     dependencies and the version is not bumped; moving them to optional extras
     and cutting a release are packaging decisions left to the maintainer.

  Self-benchmark is unchanged at 100% file and symbol recall (~97.3% context
  reduction). Any re-run of already-burned holdouts after these changes is a
  non-regression diagnostic, not fresh evidence: on holdouts #1-#3 (77 tasks)
  against the previous source, file recall rose on 3 tasks (holdout #2
  87.8% vs 85.4%, #3 96.7% vs 90.0%, #1 unchanged at 100%) and symbol recall
  moved by +1 task in #2, +1 in #3 and -1 in #3. The one loss,
  `scrapy-scheduler-next-request`, comes from finding 2's narrowing: the old
  authority boosted `scheduler.py` because `next_request` matched, but that
  same generic-name boost also lifted unrelated test files. The file is still
  retrieved; its `next_request` window is no longer selected. It was not
  tuned around.

- **Hardened partial-class and overload retrieval after holdout #7's Dapper failures.**
  Repository ranking now gives a bounded, length-independent boost to files that
  structurally define the requested container/member, preventing very large
  implementation files from losing solely to BM25 length normalization. Within
  a file, callable overloads now use overload-family-local signature IDF plus
  structural features for generic arity, arrays, async callables, generic type
  parameter roles, and CommandDefinition-style discriminators. This targets
  exact overload selection without changing holdout #7 or treating a rerun as
  fresh evidence.

- **Built and first-ran a seventh frozen external holdout after callable symbol
  ranking v3, before any tuning against its repositories.**
  `benchmarks/holdout-external-7.json` contains **48 source-grounded tasks
  across 8 previously-unused repositories**: Rich (Python), NestJS
  (TypeScript), Echo and Fx (Go), Hyper and Serde (Rust), Jackson Databind
  (Java), and Dapper (C#). The suite deliberately stresses overloaded members,
  same-name methods in different containers/files, builders, traits/interfaces,
  constructors, and exact declaration identity. All repositories are pinned to
  exact revisions. Ground truth was frozen before the first evaluation at SHA
  `ebd45fda46047399cf3d68a494760e25002cbe0e384b3ae2913834be5afa1249`.

  **First-ever result: 91.7% file recall, 85.4% bare source-visible symbol
  recall, 72.9% qualified-symbol recall, 68.8% exact symbol-identity recall,
  and ~98.71% estimated context reduction.** Per repository
  file/bare/qualified/identity recall: Rich 100/83.3/83.3/83.3, NestJS
  100/100/100/100, Echo 100/100/75/75, Fx 100/100/100/100, Hyper
  100/100/100/100, Serde 100/75/75/75, Jackson Databind 100/100/70/70,
  and Dapper 60/50/30/10.

  This is the first untouched external suite to measure the post-#15 callable
  ranking changes. It provides strong fresh evidence that precise symbol
  selection generalized substantially beyond holdout #6, while exposing Dapper
  as the dominant remaining file/member-selection outlier. The exact first-run
  output is preserved in `benchmarks/holdout-external-7.result.json`.
  Holdout #7 is now burned for tuning.

- **Built and first-ran a sixth frozen external holdout after structural symbol
  graph v2, before any tuning against its repositories.**
  `benchmarks/holdout-external-6.json` contains **24 source-grounded tasks
  across 6 previously-unused repositories**: go-playground/validator and
  spf13/cobra (Go), seanmonstar/reqwest and tokio-rs/bytes (Rust), google/gson
  (Java), and LuckyPennySoftware/AutoMapper (C#). Every repository is pinned to
  an exact revision. Ground truth includes file, bare symbol, qualified symbol,
  and exact `path:qualified@line` identity and was frozen at SHA
  `6c069bc6ef9fcaffd19f6960b9da5e45797a1cbc6f30f9938b937dd2ac7f0535`
  before the repositories were cloned into the validation run.

  **First-ever result: 91.7% file recall, 58.3% bare source-visible symbol
  recall, 50.0% qualified-symbol recall, 45.8% exact symbol-identity recall,
  and ~97.41% estimated context reduction.** Per repository file/bare/qualified/
  identity recall: validator 75/75/50/50, Cobra 100/25/25/25, reqwest
  100/75/75/75, bytes 100/75/75/75, Gson 100/75/75/50, and AutoMapper
  75/25/0/0.

  This is the first fresh suite to measure overload/container identity directly,
  and it confirms the remaining bottleneck is primarily symbol selection inside
  already-correct files rather than file retrieval. The exact first-run output
  is preserved in `benchmarks/holdout-external-6.result.json`. This suite is
  now burned for tuning; follow-up fixes must use independent synthetic
  fixtures and another untouched suite for fresh generalization evidence.

- **Added a deterministic Output Saver benchmark harness.**
  `acco output-benchmark manifest.json` runs compaction over inline or
  file-backed responses and reports weighted/mean output-token reduction,
  exact fenced-code preservation, required-content preservation, removed
  units, and budget-overflow rate. The harness intentionally does not claim
  generation-time savings from post-processing; real generated-token and
  invoice effects belong in paired agent runs measured by `cost-report`.

- **Added paired cost-per-success reporting for real agent runs.**
  `acco cost-report baseline.json optimized.json` compares identical
  task IDs across baseline and ACCO runs using success outcomes,
  input/output/cache tokens, model/tool calls, latency, and cost. It reports
  total token and invoice reductions, success-rate change, improved/regressed
  tasks, and the primary commercial metric: **cost per successful task**.
  Costs can be supplied directly per run or derived from configurable
  per-million input/output/cached-input pricing. Mismatched workloads are
  rejected by default so savings cannot be inflated by comparing different
  task sets. The command also accepts the existing single-file
  `agent-evaluate` paired manifest format (`task` +
  `condition=baseline|acco`), so quality parity and economics can be
  computed from the same experiment record rather than duplicated data.

- **Built and first-ran a fifth frozen external holdout after the multi-language
  parser work.** `benchmarks/holdout-external-5.json` contains **30
  source-grounded tasks across 6 previously-unused repositories**: chi and zap
  (Go), clap and tower (Rust), Guava (Java), and Serilog (C#). Ground truth and
  exact repository revisions were frozen before ACCO saw any selected
  repository at SHA
  `9f2d7b6df3971aee95f906a1a85da4fde3c26226d10f3cecc2bafb6ce1c4fca3`.

  **First-ever result: 90.0% file recall, 56.7% source-visible symbol recall,
  and ~97.28% estimated context reduction.** Per repository: chi 100%/100%,
  zap 100%/60%, clap 100%/40%, tower 80%/60%, Guava 60%/40%, and Serilog
  100%/40% (file/symbol recall). The exact first-run output is preserved in
  `benchmarks/holdout-external-5.result.json`.

  This suite is now burned for tuning. Subsequent structural improvements are
  developed on independent synthetic fixtures; a later untouched suite is
  required for fresh generalization evidence.

- **Added structural cross-language symbol graph v2.** Parser-backed Go, Rust,
  Java, and C# symbols now contribute AST-native method calls and import/use
  targets to the repository graph instead of relying on generic call/import
  regexes. `SymbolRecord` now persists qualified identities (for example
  `UserLogger.Information`) and the index format is version 7.

  Context packing keeps the legacy bare-name symbol labels for compatibility
  while also emitting source-visible `path + qualified symbol + line`
  identities. The evaluator can opt into stricter `qualified_symbols`
  ground truth and, when overload/member disambiguation matters, exact
  `symbol_identities` such as `Formatter.cs:Formatter.Format@7`. Both
  fields are opt-in, so historical frozen manifests keep their original hashes.

  Within-file ranking now uses qualified/container names plus a bounded
  parser-derived call signal. Container symbols no longer inherit all
  descendant body vocabulary or additively double-count child relevance;
  this prevents large classes/types from becoming lexical hubs while still
  allowing relevant children to credit their container.

  Validation: **381 tests passing**, Python 3.10/3.12/3.13 CI green, and the
  25-task self benchmark remains **100% file / 100% source-visible symbol
  recall** at **~96.6% estimated context reduction**. Development used
  independent synthetic fixtures; frozen holdout #5 is diagnostic only.

- **Built and first-ran a fourth frozen external holdout before any tuning
  against its repositories.** `benchmarks/holdout-external-4.json` contains
  **40 source-grounded tasks across 8 previously-unused public repositories**:
  Jinja and Werkzeug (Python), ESLint and Undici (JavaScript), gorilla/mux and
  Gin (Go), and Axum and serde_json (Rust). All repositories are pinned to
  exact revisions. Ground truth was authored from source first, frozen at SHA
  `73b66da6cc5b5595ee956154b8c05242a44b011e2d0bd22b3c86faa0278edb38`,
  verified by the evaluator before cloning, and only then evaluated once.

  **First-ever result: 95.0% mean file recall, 45.0% source-visible symbol
  recall, and ~97.18% mean estimated context reduction.** The exact first-run
  output is preserved in `benchmarks/holdout-external-4.result.json`.

  The language split is especially useful: Python measured 90% file / 60%
  symbol recall, JavaScript 90% / 80%, Go 100% / 10%, and Rust 100% / 30%.
  Thus the suite provides strong new evidence that file retrieval generalizes
  across additional languages while exposing a substantial Go/Rust
  symbol-level gap. This suite is now considered burned for tuning; fixes
  inspired by these misses must be developed on independent synthetic fixtures
  and validated by another untouched external suite before being claimed as
  fresh generalization evidence.

- **Added parser-backed symbol extraction for Go, Rust, Java, and C#.**
  These languages no longer rely on the generic one-line declaration regex:
  the shared Tree-sitter syntax layer now records exact source spans, compact
  signatures, symbol kinds, container/receiver relationships, and method-local
  calls. Qualified names preserve ownership across language idioms, including
  Go receiver methods (`Engine.ServeHTTP`), Rust `impl`/trait methods
  (`Json.into_response`, `Handler.call`), Java members, and C# methods,
  constructors, properties, events, and delegates.

  The same structural information now powers repository indexing, code maps,
  and exact named-symbol snippets. The persisted index format was bumped to
  version 6 so older regex-only records are rebuilt automatically. Unsupported
  or malformed source retains the existing conservative generic fallback.

  A first implementation placed the new parsers in a separate generic
  `syntax_multilang.py` module. The self-benchmark immediately caught that
  module becoming an artificial lexical hub and displacing the real
  `snippet.py` target (100/100 -> 96/96). Rather than special-case ranking,
  the language registry was folded into the existing syntax module; the
  temporary diagnostic was removed and the benchmark returned to **100% file /
  100% source-visible symbol recall** at **~96.4% estimated context reduction**.
  Validation: **374 tests passing** and CI green on Python 3.10/3.12/3.13.

  Development used generic synthetic fixtures rather than holdout #4 task IDs.
  Holdout #4 remains burned/diagnostic; it is not re-run here as fresh
  generalization evidence.

- **Added conservative typo-tolerant retrieval and an inspectable context browser.**
  Repository-scope typo normalization now compares query words only against
  indexed identifier vocabulary, requires a high similarity score plus a clear
  margin over the next candidate, and retains the original query term instead
  of rewriting it. Within an already-selected file, a bounded fuzzy identifier
  bonus provides a slightly broader fallback for misspelled symbol names. This
  keeps fuzzy matching subordinate to BM25/graph/structural evidence rather
  than turning it into a new global retrieval strategy.

  Added `acco browse` with ranked files, reasons, source-backed selected
  symbols, redacted previews, estimated preview tokens, and visible fuzzy
  corrections. `--show N` prints a detailed candidate and `--interactive`
  provides a small terminal inspection loop (`list`, `show N`, `quit`).
  The browser deliberately reuses the production ranker/source-window/redaction
  path. The same surface is exposed to agents through MCP as
  `browse_context`.

  Validation: **368 tests passing** on Python 3.10/3.12/3.13. The 25-task
  self-benchmark remains **100% file / 100% source-visible symbol recall** at
  **~96.3% estimated context reduction**. The fresh external holdout #3 was
  created and run before this work (90.0% file / 51.7% symbol / ~97.3%
  reduction), so it is not being reused as a tuning target for these changes;
  another untouched holdout is required to make a fresh generalization claim
  about fuzzy retrieval.

- **Built and ran a third, genuinely fresh frozen external holdout
  suite** (`benchmarks/holdout-external-3.json` / `.result.json`): 30
  tasks across 6 independently-authored public repositories never used
  in either prior suite -- [pallets/flask](https://github.com/pallets/flask),
  [tornadoweb/tornado](https://github.com/tornadoweb/tornado),
  [scrapy/scrapy](https://github.com/scrapy/scrapy),
  [tj/commander.js](https://github.com/tj/commander.js),
  [koajs/koa](https://github.com/koajs/koa), and
  [socketio/socket.io](https://github.com/socketio/socket.io) (server
  package). Ground truth authored the same way as the second suite: by
  isolated agents reading each repository's actual source, before
  acco was ever run against it, then frozen via
  `--print-ground-truth-hash`. This suite exists because both prior
  suites are now heavily reused for diagnosing and validating fixes --
  a third, untouched suite is needed to check those fixes generalize
  rather than having been quietly tuned to the specific repos that found
  them.

  **First-ever result: 90.0% mean file recall, 51.7% mean symbol
  recall**, ~97.3% mean estimated token reduction. File recall is
  markedly better than either prior suite started at (83.3% and 58.5%
  respectively, before any fixes), consistent with this cycle's fixes
  generalizing rather than overfitting. Symbol recall (51.7%) sits
  between the two prior suites' *current*, already-fixed numbers
  (100% and 63.4%), which is a reasonable, expected outcome for a
  never-tuned suite rather than a red flag on its own.

  One clear repository-level outlier: scrapy, at 40% file / 20% symbol
  recall (3 of 5 tasks missed entirely), spot-checked directly rather
  than left as an unexplained number. All three misses are buried well
  down the file ranking (position 5, 9, and 20) behind several other
  files that are *also* genuinely, non-coincidentally about
  downloading/requests/crawling (`core/downloader/handlers/http11.py`,
  `exceptions.py`, `pipelines/media.py`, `spiders/crawl.py`, ...) --
  the same already-disclosed "large/broadly-related hub file"
  competition pattern found and deliberately left unfixed on the second
  suite (pydantic's `core_schema.py`/`_generate_schema.py`), not a new,
  cleanly-fixable bug. Not chased further in this pass, for the same
  reason: a blanket fix for "many files legitimately share this
  vocabulary" broke a different, previously-correct case (httpx's large
  but genuinely-correct `_client.py`) the one time it was tried this
  release.

- **Fixed a real regression on the first (httpx/zod) frozen external
  holdout: `httpx-redirects` dropped from 1.0 to 0.0 symbol recall**,
  surfaced by re-running that suite after this cycle's stricter
  visible-source-only symbol labeling (see the entry below) started
  correctly filtering out labels whose source doesn't actually survive
  budget fitting. This wasn't the stricter check introducing a bug -- it
  correctly caught a latent fragility in an earlier fix (from before this
  cycle): crediting a boosted parent's matching child with a label
  assumed the parent's *entire* window would render, so the child's code
  would "already be there." For a genuinely large container -- httpx's
  `Client` spans ~1400 lines -- real cross-file budget competition clips
  the window long before reaching the credited child's line (`_client.py`
  was truncated at line 907, well short of `_send_handling_redirects` at
  964), so the label pointed at source that was never actually rendered.

  Fixed by rendering a tight window around the credited child instead of
  the container's full span, once the container exceeds 200 lines (a
  conservative threshold -- small classes like `DigestAuth` keep
  rendering in full, unaffected). A second regression was found and fixed
  while validating this: substituting only the child's window dropped the
  *container's own* declaration line, so its own label then failed the
  same visible-source check for the same reason -- fixed by also keeping
  a couple of lines at the container's declaration alongside the child's
  tight window.

  New regression test
  `test_symbol_window_uses_tight_window_for_credited_child_in_large_container`
  (`tests/test_pack.py`), confirmed via git stash to fail without the fix.
  Verified: 361 tests passing (was 360), self-benchmark unchanged at
  100%/100%, and a one-time re-run of both frozen external holdouts (not
  a tuning loop): the first suite is back to a clean 100%/100%, the
  second, larger suite is unaffected either way (zero regressions, zero
  new passes) -- none of its 41 tasks happened to exercise this specific
  large-container-with-credited-child shape.

- **Improved actual symbol-source recall rather than metadata-only recall.**
  Added a conservative, query-only symbol normalization layer for nearby
  code-oriented wording such as `connection -> connect`,
  `equality -> equal`, `completion -> complete`,
  `validation -> validate`, `persistence -> persist`, and
  `first/begin -> start`. The richer terms are used only after a file has
  already been selected, so repository-wide BM25/file ranking is unchanged.

  Fixed two context-allocation bugs uncovered while making the metric stricter:
  (1) `selected_symbols` previously credited labels even when their exact
  source had been clipped out of the final section, and (2) exact source
  windows were emitted after ranking metadata/full outlines and then sorted by
  source line, allowing lower-value navigation or an earlier weaker symbol to
  consume a tight per-file budget before the higher-scoring implementation.
  Symbol labels now count only when their source line survives, exact source is
  emitted before metadata/outlines, and source windows preserve symbol-score
  order before lexical navigation windows.

  The stricter accounting initially exposed the self-benchmark's previous
  100% symbol result as partly metadata-only (88% when source presence was
  enforced). The source-priority fixes recovered a **real 100% file / 100%
  symbol recall** on the 25-task self-benchmark at ~96.0% estimated context
  reduction. Full suite: **360 tests passing** on Python 3.10/3.12/3.13.

  A one-time diagnostic run of the already-burned 41-task external suite is
  intentionally *not* treated as new generalization evidence. Under the new
  stricter source-visible metric it measured 87.8% file / 59.8% symbol recall;
  compared task-by-task with the old stored result, `requests-connect-timeout`
  improved from 0 to 1 while three old positive symbol hits disappeared because
  their labels did not have source surviving in the actual pack. Further
  tuning against that suite was stopped; a fresh holdout is required for a new
  generalization claim.

- **Added Output Saver, a deterministic output-token layer for coding agents.**
  Generation-time `output-policy` produces terse/normal/detailed response
  contracts with explicit token targets, no task restatement/tool narration,
  diff/reference-first code guidance, compact validation reporting, structured
  agent-to-agent state, and stop-on-success behavior. `output-save` safely
  compacts already-generated responses by removing trivial filler, exact
  repeated prose/status echoes, and pretty-print JSON overhead; optional
  `--enforce-budget` trims prose only. Fenced code and diffs are never
  truncated: if preserved code cannot fit, the result explicitly reports
  `budget_exceeded` rather than corrupting source. Both capabilities are also
  available as MCP tools (`output_policy`, `compact_output`) and report
  estimated before/after token counts so output savings can be measured
  separately from input-context savings.

- **Investigated the second holdout suite's remaining 19 misses in
  detail; fixed one more real bug, attempted and reverted one extraction
  extension, and disclosed the rest as genuinely hard rather than forcing
  a fix.**

  Fixed: the acronym-boundary regex added for `HTTPBasicAuth` was itself
  slightly too eager -- `(?<=[A-Z])(?=[A-Z][a-z])` fires on a *single*
  leading capital too, so `ETag` split into `E`+`Tag` and never matched
  the plain `etag` property name used for the same concept elsewhere in
  the same codebase (expressjs/express). Tightened the lookbehind to
  require *two* preceding uppercase letters (`(?<=[A-Z][A-Z])`), so
  genuine acronym prefixes (`HTTP`, `XML`, `IO`) still split but a single
  leading capital (`ETag`, `IPage` -- almost always just an ordinarily-
  capitalized word) does not. New test
  `test_single_leading_capital_is_not_treated_as_a_one_letter_acronym`
  (`tests/test_lexical.py`).

  Attempted and reverted: extending `assignment_expression` extraction to
  cover `exports.etag = createETagGenerator({...})` (a CommonJS export
  whose value is a call result, not a function literal) by treating any
  `exports.X = <anything>` as an exported data symbol, mirroring the
  existing treatment of `export const X = <data>`. This swept up trivial
  one-line re-export aliases too (`exports.request = req`,
  `exports.response = res`, in express's own `lib/express.js`), and one
  of those aliases' name happened to coincidentally match a different
  task's query vocabulary strongly enough to displace the genuinely
  correct symbol (`createApplication`) -- a real, measured regression
  (`express-create-application`, 1.0 -> 0.0 symbol recall), not a
  measurement artifact this time. Reverted; `exports.etag` itself remains
  unextracted (a real, disclosed extraction gap), though the query terms
  now at least match its plain `etag` symbol thanks to the acronym fix
  above -- it competes closely (a 1-point score gap against two sibling
  helpers) rather than being invisible.

  Investigated but deliberately left unfixed, each for a distinct,
  disclosed reason rather than silently dropped:
  - `pydantic/errors.py`, `pydantic/root_model.py`: buried at file rank
    49 and 19 respectively behind pydantic's few large, genuinely
    heavily-cross-referenced "hub" files (`core_schema.py`,
    `_generate_schema.py`, `json_schema.py`) that legitimately discuss
    schema/model/validation extensively for nearly every query in this
    domain. This is the same large-file-dominance shape that broke
    `httpx-redirects` when a blanket size-based dampening was tried
    earlier this release (and reverted) -- not attempted again without a
    fundamentally different, more targeted signal than file size.
  - `requests/exceptions.py` (`ConnectTimeout`): loses to its own parent
    classes (`ConnectionError`, `Timeout`) partly because "connect" and
    "connection" are different word forms the tokenizer doesn't stem
    together -- a general English-morphology gap (also behind
    `lodash-deep-equal`'s `equality`/`equal` mismatch and
    `date-fns-start-of-week`'s `start`/`first` synonym gap), not a
    single targeted bug; a real stemmer or synonym table is a much larger
    change than this pass's scope.
  - `axios-cancel-request-timeout`, `date-fns-start-of-week`: many
    structurally-similar sibling files (date-fns's `getWeek`/
    `getWeekOfMonth`/`getWeekYear`/...) all receive the identical
    `graph:semantic-ref@1` boost via their own `fp/` re-export, so the
    signal doesn't discriminate the correct sibling from the others here.
  - `express-negotiate-accept-header` (`accepts` vs `header`): a genuine
    near-tie (22 vs 21 raw score), not a clear miss.

  Verified: 342 tests passing (was 341), self-benchmark unchanged at a
  clean 100%/100%, and the second frozen holdout ends this investigation
  net neutral on its own numbers (87.8%/62.2%, matching the pre-
  investigation state) but with one additional real bug fixed and
  disclosed rather than a regression shipped -- the reverted attempt was
  caught before being kept specifically because of the discipline of
  re-checking both frozen holdouts, not the self-benchmark alone, before
  trusting a change.

- **Strengthened test/doc-file deprioritization for "how does X work"
  queries** -- the largest remaining root cause behind the second frozen
  external holdout's misses (8 of the original 19), and the same class of
  problem two earlier, reverted file-ranking attempts targeted with
  novel, ad-hoc signals (symbol-name rarity, outline size). This attempt
  used neither: `file_priority()` (`skeleton.py`) already correctly tags
  `tests/`, `docs/`, `fixtures/`, and similar directories as low-value,
  and is already used elsewhere (the repo map/skeleton listing) without
  issue -- `rank_files()` just applied it far too weakly to matter, a
  flat `+0.3`-vs-`+1.2` additive bonus against BM25 scores that routinely
  run into the tens of points. A test file that exercises a feature
  extensively, or a doc page that explains it in prose, both legitimately
  share a lot of vocabulary with a query about that feature without being
  the right answer to it, and nothing was strong enough to say so.

  Fixed by dampening (not just lightly nudging) a low-value-directory
  file's whole computed score by 0.35x, so the penalty scales with
  however large the underlying score actually is, rather than adding a
  fixed, easily-swamped amount. New regression test
  `test_rank_files_prefers_implementation_over_test_file_for_how_does_x_work`
  (`tests/test_pack.py`), confirmed via git stash to fail without the fix.

  Verified: 341 tests passing (was 340), self-benchmark reached a clean
  **100%/100%** (up from 92%/96%, including `pack-cli`, a self-referential
  failure present since early in this session that was never chased down
  before), and a one-time re-run of both frozen external holdouts: the
  first httpx/zod suite remains 100%/100%; the second, larger suite rose
  from 58.5% to **87.8% mean file recall** and 58.5% to **62.2% mean
  symbol recall**, with 4 tasks newly passing and 2 partial regressions
  (`click-group-dispatch`, `pydantic-json-schema-generation`, both
  1.0->0.5 symbol recall) that turned out, on direct inspection, not to be
  real behavior regressions at all: in both cases the *previous* 1.0 was
  itself a false positive -- a test file (`tests/test_commands.py`,
  `tests/test_json_schema.py`) happened to define its own, unrelated
  method with the exact same bare name as the ground-truth symbol
  (`resolve_command`, `generate`), which the recall metric counts as a
  match regardless of which file it came from. Suppressing that test file
  correctly removed the accidental match and exposed a real, separate,
  disclosed gap this fix doesn't touch: the actual `resolve_command`/
  `generate` methods in their correct files aren't independently winning
  their own symbol-window competition against sibling classes/methods.

  The self-benchmark's 100%/100% here is not the same warning sign the
  reverted outline-size attempt's 100%/100% was: that one broke a
  different, previously-fixed holdout task outright (`httpx-redirects`).
  This one was checked against both frozen holdouts before being trusted,
  and produced zero real regressions on either.

- **Fixed a JS/TS symbol-extraction gap and generalized the parent-credit
  symbol-window boost past Python.** Two changes shipped together because
  the second was found as a direct regression from the first.

  1. **`obj.prop = function () {...}` was invisible to symbol
     extraction.** tree-sitter gives this common CommonJS/prototype-
     assignment pattern its own `assignment_expression` node type with
     "left"/"right" fields, not the "name"/"value" fields the extractor
     already handled for `const x = function(){}` (`variable_declarator`)
     and object-literal methods (`pair`). Left unhandled, an entire public
     API surface written this way -- as expressjs/express's
     response.js/request.js near-universally are -- never appeared in the
     index at all (`res.cookie`, `req.accepts`, and similar were
     completely missing). Fixed in `syntax.py` by handling
     `assignment_expression` the same way.
  2. **Regression:** once `View.prototype.lookup`/`render` became visible,
     they immediately began outscoring and displacing `View` itself --
     the same DigestAuth-shaped failure, just newly exposed for JS/TS's
     pre-ES6 constructor-function/prototype-method pattern rather than
     fixed for it, since the earlier DigestAuth fix's parent-credit boost
     is gated on `kind == "class"`, which JS/TS symbols never carry
     (tree-sitter extraction tags all of them `"symbol"` regardless of
     shape). Fixed by generalizing the boost's eligibility check from
     `kind == "class"` to "has at least one other symbol recording it as
     `parent`" -- a structural definition that already exactly matches
     Python's `kind == "class"` in practice (parent is only ever set for
     class-contained methods there) but also now correctly covers real JS/
     TS `class` bodies and the new `X.prototype.method` pattern. This
     required also fixing *what* records a `parent` link in the first
     place: previously *any* accepted symbol (including an ordinary
     function) prefixed its descendants' qualified names, so an ordinary
     function containing a nested helper function would have newly
     qualified as a "container" too under the broadened check -- reintroducing
     the exact over-boosting bug fixed earlier for `zod-error-tree`/
     `zod-flatten-error`. Restricted qualified-name prefixing in
     `syntax.py` to genuine containers (`class_declaration`,
     `interface_declaration`, `enum_declaration`) plus the new
     `X.prototype.method` link, so ordinary function nesting creates no
     parent link in either language, same as Python already didn't.

  New tests:
  `test_member_assignment_function_is_indexed_with_prototype_owner_as_parent`
  (`tests/test_v1.py`, direct extraction/parent-linking check) and
  `test_symbol_window_boosts_prototype_constructor_over_its_own_methods`
  (`tests/test_pack.py`, end-to-end); the existing
  `test_symbol_window_does_not_boost_function_nested_in_another_function`
  regression test continues to pass, confirming the nested-function fix
  wasn't undone.

  Verified: 340 tests passing (was 338), self-benchmark file recall shows
  a one-task self-referential-corpus dip (96% -> 92%: this commit's own
  new comment in `syntax.py`, which mentions "symbol extraction",
  coincidentally overlaps the self-benchmark's `snippet` task query more
  than before -- not a logic regression, the same category of noise
  `snippet`/`pack-cli` have shown before), and a one-time re-run of both
  frozen external holdouts (not a tuning loop): the second, larger suite's
  mean symbol recall rose from 56.1% to **58.5%** with zero regressions
  across all 41 tasks, the first httpx/zod suite remains a clean 100%/100%.

- **Fixed an acronym-prefixed identifier tokenization bug.** `terms()`'s
  camelCase splitter only recognized a lowercase/digit-to-uppercase
  transition, not an uppercase-run-to-title-case one, so an identifier
  like `HTTPBasicAuth` tokenized as one fused word (`httpbasic`, `auth`)
  instead of `http`, `basic`, `auth`. Found via the second frozen external
  holdout: a query for "HTTP basic authentication" never matched
  `HTTPBasicAuth`'s own name at all (scored 0), so an unrelated helper
  function that merely mentioned "basic"/"HTTP" in prose comments won the
  symbol-window competition instead of the obviously correct class. Fixed
  by adding the missing boundary pattern to `_CAMEL` in `lexical.py`
  (`URLPattern`, `XMLHttpRequest`, and similar acronym-prefixed names are
  affected the same way; plain acronyms like `ID` are unaffected). New
  tests: `tests/test_lexical.py` (direct tokenizer unit tests) and
  `test_symbol_window_matches_acronym_prefixed_class_name`
  (`tests/test_pack.py`, an end-to-end reproduction of the real shape),
  both confirmed via git stash to fail without the fix.

  Verified: 338 tests passing (was 335), self-benchmark unchanged (96%
  file / 96% symbol recall -- this repository's own identifiers happen not
  to hit the acronym-prefix shape), and a one-time re-run of both frozen
  external holdouts (not a tuning loop -- this is a general tokenizer
  correctness fix, not tuned to either suite's scores): the second, larger
  suite's mean symbol recall rose from 53.7% to **56.1%** with zero
  regressions (`requests-basic-auth` now 1.0/1.0), the first httpx/zod
  suite remains a clean 100%/100%.

- **Built and ran a second, larger, genuinely fresh frozen external
  holdout suite** (`benchmarks/holdout-external-2.json` /
  `.result.json`): 41 tasks across 8 independently-authored public
  repositories never used in any prior validation --
  [pallets/click](https://github.com/pallets/click),
  [pydantic/pydantic](https://github.com/pydantic/pydantic),
  [psf/requests](https://github.com/psf/requests),
  [tiangolo/fastapi](https://github.com/tiangolo/fastapi),
  [axios/axios](https://github.com/axios/axios),
  [date-fns/date-fns](https://github.com/date-fns/date-fns),
  [expressjs/express](https://github.com/expressjs/express), and
  [lodash/lodash](https://github.com/lodash/lodash). Ground truth for
  each repository was authored independently (by isolated agents with no
  access to acco's own source or the tool's known weaknesses'
  specifics beyond "include some large-file-correct and some
  terse-file-correct cases if the repo naturally supports them"), from
  reading the actual source, before acco was ever run against it,
  then frozen via `--print-ground-truth-hash` exactly as the first
  holdout suite was. This suite exists specifically because the first
  6-task httpx/zod suite was explicitly disclosed as "burned" for further
  `zod-email-regex`-style diagnosis after two failed fix attempts against
  it -- validating a future fix needs ground truth that was never used to
  find or chase that fix.

  **Result: 58.5% mean file recall, 35.4% mean symbol recall**, ~98.4%
  mean estimated token reduction -- the honest, frozen, first-ever number
  on this suite, and materially worse than both this repository's own
  self-benchmark (92%/96%) and the now-much-improved first external
  holdout (83.3%/83.3%). This is a significant, previously-invisible
  generalization gap that neither of the smaller/narrower benchmarks used
  so far happened to surface.

  Root-caused by inspecting every one of the 16 missed tasks directly
  (not by guessing from the aggregate number): two distinct, compounding
  causes, not one.
  1. **Test and documentation files systematically outrank
     implementation files for "how does X work" queries.** 10 of 16
     misses had a test file (`tests/test_validators.py`,
     `tests/test_requests.py`, ...) or a docs page ranked #1, ahead of
     the actual implementation. This isn't an unreasonable BM25 outcome
     in isolation -- a test file that exercises a feature extensively
     genuinely does share a lot of vocabulary with a query about that
     feature -- but nothing in the ranking signal set distinguishes "a
     file that exercises/discusses the concept" from "the file that
     implements it," which is what most of these queries were actually
     asking for.
  2. **No cap on how much of the total budget a single file can consume.**
     `build_context_pack`'s per-candidate budget loop has no general
     fair-share limit (the existing `slots_left` fair-share logic only
     applies to explicitly-passed `priority_files`, and the
     `authoritative_reserve` mechanism only protects one specific
     semantic-ref provider). When the #1-ranked file is both large and
     the (arguably mis-ranked) top scorer, it can consume the entire
     budget in one shot, e.g. `tests/test_validators.py` alone used 5993
     of pydantic's 6000-token budget, leaving literally nothing for
     `pydantic/functional_validators.py` -- the actual, correctly-ranked
     #4 candidate -- to ever be considered. This compounds cause 1 into
     complete, one-file-only failures: every task with only 1-2 files in
     `selected_files` hit this pattern.

  Deliberately not fixed in the same commit as the diagnosis -- see the
  next entry for cause 2's fix, designed and validated against the
  self-benchmark first, per this project's standing discipline.

- **Fixed cause 2 above: no cap on how much of the budget a single file
  can consume.** `build_context_pack`'s per-candidate loop now caps an
  ordinary (non-`priority_files`) candidate's share of what's left to
  `max(remaining * 3/5, 300 tokens)`, mirroring the existing
  `priority_files` fair-share mechanism but generalized to every
  candidate. The cap only applies while more candidate files and
  selection slots remain -- the true last usable candidate still gets
  whatever's left rather than wasting it unused, so this never shrinks a
  pack when only one or two files are genuinely relevant. New regression
  test `test_context_pack_does_not_let_one_large_file_monopolize_the_budget`
  (`tests/test_pack.py`), confirmed via git stash to fail without the fix.

  Verified: 335 tests passing (was 334), self-benchmark **improved**
  (92% -> 96% file recall, 96% symbol recall unchanged -- the pre-existing
  `snippet` self-referential-corpus failure is fixed as a side effect, only
  `pack-cli` drift remains), and a one-time re-run of both frozen external
  holdouts (not a tuning loop -- this fix targets the general budget
  mechanism, not either suite's specific scores): the second, larger suite
  went from **58.5% to 80.5% mean file recall, 35.4% to 53.7% mean symbol
  recall**, zero regressions across any of the 41 tasks, 10 tasks newly
  passing. The first, smaller httpx/zod suite -- unrelated in design intent
  to this fix -- incidentally also went to a clean **100%/100%**: its one
  remaining disclosed gap, `zod-email-regex`, turned out to be the exact
  same budget-monopolization pattern (`schemas.ts` was starving
  `regexes.ts` of any room at all), not solely the outline-size ranking
  bias two earlier, reverted attempts targeted.

  Remaining known gaps on the larger suite, both untouched by this fix and
  disclosed rather than chased further in this pass: cause 1 (test/doc
  files outranking implementation files) accounts for 8 of the 20
  remaining misses (file recall still 0). The other 12 are a third,
  previously-uncharacterized failure mode -- the correct *file* is found
  (file recall 1.0) but the correct *symbol* isn't selected within it
  (`requests-basic-auth`, `lodash-clone-deep`, `lodash-deep-equal`,
  `express-generate-etag`, and others) -- distinct from the DigestAuth-
  shaped symbol-window bugs fixed earlier in 1.2.0, since those files
  aren't classes with a competing method or a type alias; worth its own
  root-cause investigation before attempting a fix.

# 1.2.0

Note: PR #3 (`fix/graph-aware-symbol-ranking`) and PR #4
(`fix/authoritative-file-ranking`) merged directly to `main` without their
own version bump or CHANGELOG entry; summarized here rather than
re-documented in detail (see the PR descriptions for full rationale).
PR #3 added caller-graph-aware symbol ranking and exact incoming
semantic-reference evidence to `_symbol_windows()`, targeting the same
generalization gap the first frozen holdout found, without tuning against
that frozen suite. PR #4 gave exact `semantic-ref` edges a strong,
deliberately non-transitive one-hop ranking weight, aimed at the
`zod-email-regex`-shaped gap (a terse provider file supplying an exact
value a query-relevant consumer file describes in prose) -- it merged with
its own CI check failing (see the fix below) and, per a fresh one-time
holdout check after that fix, does not actually resolve `zod-email-regex`
itself: `regexes.ts` has no direct incoming `semantic-ref` from a file
that independently outranks `schemas.ts`, so the underlying outline-size
bias documented below is still the live, unfixed root cause.

- **Fixed CI on `main`**, broken by PR #4 (`fix/authoritative-file-ranking`,
  merged despite its own `CI` check failing on every push -- only its
  separate, narrower `PR4 Frozen Holdout` workflow was green). The failing
  test, `test_context_pack_reserves_budget_for_exact_provider_behind_large_consumer`,
  exposed a real gap in that PR's own "authoritative provider" mechanism,
  not an interaction with unrelated work: `rank_files()` only seeds
  `dependency_closure` from the top `seed_limit` files by raw score
  (deliberately small and cost-bounded, since most edge kinds it walks are
  transitive and can fan out), so a source file that's clearly on-topic but
  ranks below that cutoff -- e.g. behind several near-duplicate files that
  outscore it on raw term overlap alone -- never got a chance to surface an
  exact value it imports via a `semantic-ref` edge. `build_context_pack`'s
  budget-reservation search window for that same signal was independently
  too narrow for the same reason. Fixed with `closure.authoritative_providers`
  (`src/acco/closure.py`): a separate, cheap, non-transitive one-hop
  scan over every relevant candidate (not just the seed set) for
  `semantic-ref` edges specifically -- cheap because that edge kind never
  expands further regardless of how many sources it's checked from, unlike
  the general closure walk. `build_context_pack`'s reservation search now
  scans all candidates for the resulting tag instead of a truncated prefix,
  since the tag itself is already the bounded, authoritative signal.
  Verified: 334 tests passing (was 328), self-benchmark unchanged
  (92%/96%), frozen external holdout unchanged (83.3%/83.3%, one-time
  re-run, not a tuning loop).

- **Fixed both remaining symbol-selection root causes behind
  `zod-flatten-error` and `zod-error-tree`** (the other two frozen external
  holdout tasks disclosed as unfixed in VALIDATION.md), found by
  investigating `zod-flatten-error` fresh rather than reusing the
  previously-abandoned "terse implementation" file-ranking framing --
  both turned out to be *symbol-window* bugs, not file-ranking bugs (file
  recall was already 1.0 for both).

  1. **Type alias signatures went untruncated.** `type_alias_declaration`
     has no tree-sitter "body" field (functions/classes/interfaces do), so
     its inline right-hand side -- however large -- went straight into its
     captured `signature`, double-counting every word in it at both the
     20x name-term ranking weight (signature) and the 1x body-term weight
     it already gets like any other symbol's body. A type alias describing
     `flattenError`'s return shape (`_FlattenedError`, whose fields are
     literally named `formErrors`/`fieldErrors`) outscored `flattenError`
     itself purely from its own field names matching the query. Fixed in
     `syntax.py` by truncating a type alias's signature at its `value`
     field, the same way a function/class signature truncates at its
     `body` field. New direct test:
     `test_type_alias_signature_is_truncated_like_a_function_body`
     (`tests/test_v1.py`), confirmed via git stash to fail without the fix.

  2. **The parent-credit boost (from the DigestAuth fix above) wasn't
     scoped to classes.** It also applied when a *function* contained a
     nested helper function -- a fundamentally different relationship
     from class/method: a class groups multiple members that can each
     independently be the right, narrower answer; a function's nested
     helper is just an implementation detail of that one function, not a
     set of candidate answers. A top-level distractor function's own body
     already includes its nested helper's text (so its own score already
     reflects the helper), but the boost added the helper's score a
     *second* time, letting an unrelated function outscore the file's
     actually correct, unrelated top-level function (`treeifyError` /
     `flattenError`, depending on the query). Fixed in `pack.py` by
     restricting the boost to parents with `kind == "class"` -- available
     for Python (`ast.ClassDef`); JS/TS symbols are all tagged `"symbol"`
     today regardless of shape, so this disables the boost for JS/TS
     entirely for now rather than mis-scoping it, a disclosed limitation,
     not a regression (no passing JS/TS behavior depended on it). New
     regression test:
     `test_symbol_window_does_not_boost_function_nested_in_another_function`
     (`tests/test_pack.py`), confirmed via git stash to fail without the
     fix.

  Verified: 328 tests passing (was 326), self-benchmark unchanged
  (92%/96%), and a one-time re-run of the frozen external holdout (not a
  tuning loop -- both fixes are general correctness fixes discovered by
  reading the symbol-extraction and boosting code, not by iterating
  against this suite's specific scores) shows **`zod-flatten-error` and
  `zod-error-tree` both now at 1.0/1.0** with no new regressions across
  any of the 5 previously-passing tasks: mean symbol recall
  **66.7% -> 83.3%**, file recall and token reduction unchanged.

  **A third attempt, at the actual remaining `zod-email-regex` file-ranking
  gap, was tried and reverted.** Root cause identified precisely this
  time: `rank_files()`'s `symbol_hits` bonus (`+5` per distinct query term
  present anywhere in a file's outline) is presence-only, not
  frequency-normalized, unlike the properly length-normalized BM25 term
  right above it in the same function -- so a file with a sprawling,
  many-hundred-symbol outline (`schemas.ts`, 201,606 outline characters)
  picks up far more distinct query-term hits than a small, precisely
  on-topic file (`regexes.ts`, 900 outline characters) purely from having
  more surface area, even though raw BM25 alone (before this bonus is
  added) already correctly favors the smaller file (15.8 vs 8.0).
  Dampening the bonus by how far a file's outline exceeds the corpus's
  average outline size fixed `zod-email-regex` and, unexpectedly, pushed
  the self-benchmark to a clean 100%/100% -- but it also broke a
  previously-fixed, previously-passing task, `httpx-redirects` (1.0 ->
  0.0 file recall): `_client.py` is *itself* a large, many-symbol file
  that is genuinely the correct answer, and the same dampening that
  correctly demotes `schemas.ts` also demotes `_client.py` below a test
  file with high raw term overlap. A flat per-file outline-size dampener
  can't distinguish "large file, diffusely and incidentally matching" from
  "large file, genuinely and heavily on-topic" -- the same class of
  failure the earlier "terse implementation" attempts hit, now confirmed
  a third time on a different mechanism. Reverted; `zod-email-regex`
  remains a disclosed, deliberately unfixed gap. The self-benchmark's
  100%/100% result on the reverted version is itself worth noting: it
  would have shipped clean on the self-benchmark alone had the frozen
  external holdout not been re-checked before committing.

- **Fixed the DigestAuth per-file symbol-selection bug** the external
  holdout benchmark found (`httpx-digest-auth`: found the right file,
  `_auth.py`, but selected helper methods `_parse_challenge`/
  `_build_auth_header` over the actually-relevant class `DigestAuth`).
  Distinct from PR #3's graph-aware ranking (which fixes a *different*
  failure shape -- a top-level distractor function reached via
  caller-graph evidence): here the outranking symbols are the class's own
  nested methods, so no caller-graph signal applies. Root cause: a
  class-level symbol's extracted body always includes its own methods, but
  a lone method's *signature* (with type-annotated parameters) can rack up
  more name-term matches than the class's own bare `class Foo:` line, and
  a class's `__init__`/dispatch code doesn't carry its methods' body-match
  credit at all -- so a helper can outscore and displace the class it
  belongs to, even though the class's window would show that same
  helper's code anyway.

  Fixed by crediting a matching parent symbol with its single
  best-matching child's score (not the sum of all matching children --
  tried that first, and it let a class with many mediocre-but-nonzero
  matching methods out-accumulate a more precisely-matching standalone
  function, regressing 2 self-benchmark tasks; reverted and used max
  instead of sum). Children are not excluded from the running -- a
  specific method can still legitimately win when nothing else in its
  class is independently relevant (verified against an existing test
  expecting exactly a method name, not its class, in the result).

  Verified: 325 tests passing (was 324), self-benchmark unchanged at the
  PR #3 baseline (92% file recall / 96% symbol recall, only the
  pre-existing `snippet`/`pack-cli` self-referential-corpus drift), and
  the original motivating case now selects `DigestAuth` directly (checked
  against the real httpx source, not the frozen holdout as a tuning loop).

  **Re-ran the frozen external holdout suite once, after the fact, as a
  one-time measurement** (not a tuning loop -- the fix above was designed
  and validated entirely against the self-benchmark, per this project's
  own discipline; this run only *observes* its effect on the suite that
  originally found the bug). Result: mean symbol recall rose from 16.7%
  to **50%** (`benchmarks/holdout-external.result.json`), file recall and
  token reduction unchanged. Three tasks flipped to full symbol recall
  (`httpx-digest-auth`, `httpx-multipart`, `zod-error-tree`), consistent
  with the parent-credit mechanism fixing genuinely the same shape of bug
  in each. But **one task regressed**: `httpx-redirects` went from 1.0 to
  0.0 symbol recall. Root cause, confirmed by direct inspection: the
  query's actual answer is a single specific method,
  `_send_handling_redirects`, and *both* of the classes containing it
  (`Client` and `AsyncClient`, httpx's sync/async twins) now score high
  enough via the parent-credit boost to take both of the file's top-2
  window slots themselves, pushing the method that was the genuinely
  correct, narrower answer out of `selected_symbols` entirely -- even
  though its source bytes are still present inside the classes' windows,
  since symbol recall here is measured by name match against
  `selected_symbols`, not byte coverage. This is a real, disclosed
  regression, not swept under the self-benchmark's unchanged numbers
  (which don't exercise the two-classes-share-one-target-method shape).

  **Fixed** -- not by re-tuning the parent-credit heuristic against this
  frozen suite, but by fixing the actual underlying correctness gap it
  exposed: a boosted parent's window already contains its credited
  child's source (a class's line range always spans its own methods), so
  the child that earned a parent its window slot is now also added to
  `selected_symbols` as a label, without spending a second window slot on
  source that's already rendered. `_symbol_windows()` no longer collapses
  windows and labels into one 1:1 list; labels can now include a
  window-less credited child. New regression test
  (`test_symbol_window_credits_shared_method_name_when_two_classes_both_win_slots`)
  reproduces the Client/AsyncClient shape synthetically and is verified,
  via git stash, to fail without this fix. Verified: 326 tests passing
  (was 325), self-benchmark still unchanged (92%/96%), and a second
  one-time re-run of the frozen holdout now shows `httpx-redirects` back
  at 1.0 with no new regressions -- **mean symbol recall 16.7% -> 66.7%**
  across the two fixes, file recall and token reduction unchanged.
  Remaining known gap on this frozen suite: `zod-flatten-error` and
  `zod-email-regex` (the disclosed, still-unfixed file-level terse-file
  ranking weakness), unrelated to symbol-window selection.

- **Attempted and reverted: a "terse implementation" file-ranking signal**
  to address the external holdout benchmark's `zod-email-regex` finding
  (a file of bare regex constants losing the file-ranking competition to a
  larger, prose-richer file merely discussing the same topic). Two
  designs were tried, each validated against this repository's own
  25-task self-benchmark (per the explicit instruction not to tune
  against the external holdout that found the weakness):
  1. A flat bonus for any query term exactly matching a defined symbol
     name. Regressed 2 self-benchmark tasks: common English words used as
     ordinary parameter/fixture names (`input`, `baseline`, `enabled`)
     got the same bonus as a genuinely rare, specific name, and
     verbosely-named test functions (whose names decompose into many
     individual word-tokens) racked up several such "matches" at once.
  2. A version requiring most of a *whole, short* (<=3-token) symbol
     name to be covered by the query, with an IDF-style discount for
     names that recur across many files. This fixed design 1's failures,
     but introduced 2 new ones: in a codebase whose actual subject matter
     is symbol/outline extraction (this one), short words like `extract`,
     `outline`, and `symbol` aren't rare identifiers -- they're the
     domain's own vocabulary, appearing as short-name components across
     many genuinely-different files, so the IDF discount wasn't steep
     enough to suppress them.

  Reverted rather than ship either regression. Root cause understood
  well enough to say why it's hard, not just that it failed: a
  file-ranking signal based on symbol-name matching alone can't
  distinguish "this name is specific to the one right answer" from "this
  name is common domain vocabulary that recurs everywhere on-topic,"
  without something like caller/import-graph or compiler-resolved
  reference signals -- which is exactly what the original diagnosis
  (CHANGELOG's frozen external holdout entry) proposed as fix #1, not
  fix #2. Left for a future attempt with that additional signal, or with
  a more conservative version of the IDF discount tuned against a fresh,
  never-seen suite rather than iterated against this one.

Note: PR #1 (`feat/index-backed-retrieval`) and PR #2
(`feat/semantic-retrieval-v2`) merged directly to `main` after 1.1.0 was cut,
adding index-backed retrieval performance, stronger JS/TS module semantics,
adaptive retrieval budgeting, provider-aware exact token counting,
multi-repository/frozen-holdout evaluation, a TypeScript-compiler semantic
overlay, and `acco host-check` -- without their own version bump or
CHANGELOG entry. Not re-documented here in detail; see the PR descriptions.
This entry covers only the validation work below, done against that merged
state.

- **First frozen external holdout benchmark actually executed.** The
  multi-repository/frozen-holdout infrastructure existed but had never been
  run against real, independently-authored repositories. Built a 6-task
  suite against two well-known public repos at pinned revisions --
  [encode/httpx](https://github.com/encode/httpx) `b5addb6` and
  [colinhacks/zod](https://github.com/colinhacks/zod) `59bbc03` -- with
  ground truth (target files/symbols for a natural-language query) written
  from reading the actual source before ever running the tool, then frozen
  via `--print-ground-truth-hash` and `--require-holdout`.

  Result: **83.3% mean file recall, 16.7% mean symbol recall**, ~98.5%
  estimated token reduction (`benchmarks/holdout-external.json` /
  `.result.json`). This is the honest number, not a cherry-picked one -- and
  it is materially worse on symbol recall than the tool's own repository
  self-benchmark (88-92%), which is exactly the generalization-gap risk
  freezing ground truth in advance exists to catch.

  Two disclosed, unfixed root causes (deliberately not patched against this
  frozen suite -- doing so would defeat holdout evaluation's purpose):
  1. Per-file symbol sub-ranking can pick densely-worded helper methods
     over the semantically-correct but sparser class/function the query
     was actually about (`httpx-digest-auth`: found `_auth.py` but
     selected `_parse_challenge`/`_build_auth_header` over `DigestAuth`).
  2. BM25 file ranking favors prose-rich files over terse-but-correct ones
     (`zod-email-regex`: `regexes.ts`, mostly bare regex constants, lost to
     `schemas.ts`, which merely discusses email validation in fuller
     sentences).
- **Fixed a real bug found while validating `host-check` against an actual
  live host** (not a simulated payload): spawned a genuinely separate
  `claude -p --debug-file` session (2.1.274) against a scratch project with
  ACCO's hooks installed, and inspected its real debug log. It
  proved genuine acceptance (`Hook PostToolUse (acco hook) replaced
  tool output`), but `_host_evidence()`'s exact-string check
  (`"acco: filtered output"`) still reported no acceptance, because
  the host's own debug-log redaction independently rewrote "filtered" to
  "[REDACTED]" inside the marker text (confirmed unrelated to ACCO:
  invoking the hook directly produces the unmangled note). Fixed by
  checking for the recovery command's generated hex id instead of exact
  prose, since nothing but ACCO produces
  `acco output <32-hex-chars>` and generic redaction of the
  surrounding sentence doesn't remove it.
- **Paired coding-agent trials against real bug-fix tasks**, same model/
  prompt/revision, full-context baseline vs. ACCO's hooks installed,
  independently verified by running the target tests directly (not by
  trusting either agent's self-report). Two trials against
  [encode/httpx](https://github.com/encode/httpx):
  1. A small, targeted fix (NO_PROXY handling in a ~500-line file).
  2. A fix requiring locating a bug in a 2019-line file
     (`httpx/_client.py`), specifically to exercise the read guard.

  **Both trials: both conditions produced the byte-for-byte identical,
  correct fix**, verified by independently running the target tests
  (`tests/test_utils.py`'s `test_get_environment_proxies`, 12/12;
  `tests/client/test_redirects.py`, 31/31) -- ACCO's hooks do not
  change *what* gets fixed. On cost: trial 1 showed ACCO 27% more
  expensive; trial 2 showed it 56% cheaper. Inspecting the actual hook
  debug logs (not inferring from cost alone) shows why neither number
  should be trusted as a real effect: **ACCO's filtering/guard
  mechanism never actually activated in either trial** -- `hook.py`'s
  `main()` only writes output when there is something to filter, and in
  both trials every Read/Bash call stayed under the size thresholds that
  would trigger it. In trial 2 specifically, the agent used `Grep` to
  locate the bug directly rather than reading the whole 2019-line file,
  avoiding the expensive read the guard exists to prevent, in both
  conditions identically. The observed cost differences are inter-run
  variance in how much each independent agent run explored/re-verified
  after the fix, not a demonstrated effect of the tool.

  This is a genuine, disciplined finding, not a null result to paper over:
  across the validation done this session, ACCO's clearest,
  best-evidenced value is in the pre-compiled context path (`pack`/
  `pack-diff` curating context up front, as in the external holdout
  benchmark and the earlier pikivo review validation) rather than the
  reactive hook-based guard/filter layer, at least for a capable agent
  doing normal file-editing work that already tends to avoid expensive
  full reads on its own. A task genuinely forcing an expensive full read or
  very verbose command output (neither of these two did) remains untested.

# 1.1.0

- Fixed `pack-diff`/`review` silently returning an empty pack (exit 0, no
  output) on large diffs: the ranking query embedded every changed
  file/symbol name uncapped, which could itself exceed `max_tokens` before
  any file content was even considered.
- Fixed a 20-30x performance cliff in impact analysis on large diffs:
  `RepositoryIndex` now caches reverse caller/neighbor/test-file indexes
  once per build instead of rescanning every record on every
  `symbol_callers()`/`neighbors()` call -- verified byte-for-byte identical
  output via differential testing against the old per-call scan.
- Fixed `pack-diff`'s changed-file boost being a no-op for a historical
  `--base` range: it only ever checked live working-tree git status, so a
  diff review never got the boost or closure-seeding it was meant to give.
- Fixed small, genuinely-modified files losing selection to large newly-added
  files at tight budgets: `build_context_pack()` now takes `priority_files`,
  which orders selection ahead of raw BM25 score (with a fair-share cap so
  one large priority file can't consume the whole budget either).
- Widened indexing beyond source code to `.sql`, `.json`, `.yaml`/`.yml`, and
  safe `.env.example`-style templates (real secret files stay blocked;
  `redact_secrets()` remains a backstop). Added dedicated extractors so
  these are real evidence with meaningful symbols -- SQL tables, npm
  scripts, CI job ids, env vars -- reusing the existing symbol/call-graph
  machinery rather than a parallel relationship-graph subsystem.
- Added budgeted evidence allocation: database/config/CI/test evidence that
  is entirely newly-added (so the priority-file mechanism can't reach it)
  gets a small, fair-share-capped budget reservation instead of competing
  purely on BM25 score against large new source files.
- Added a coverage manifest (`build_diff_context`'s `coverage` key, and a
  `# coverage: N/M changed files represented (...)` footer in `pack-diff`'s
  text output) that distinguishes selected, closure-only, policy-excluded,
  and simply-didn't-fit evidence -- so a caller can tell "nothing relevant
  here" from "this pack has a real, disclosed blind spot."
- Fixed `should_skip_dir()` excluding `.github/workflows` (and
  `.gitlab`/`.circleci`) under a blanket "starts with dot" rule -- these are
  committed, human-authored CI config, not VCS/tooling internals like `.git`
  or `.venv`.

Validated end-to-end against a real 129-file diff from a separate production
application (a private third-party codebase, not included in this
repository): reviewed independently by an isolated model instance with no
access to the source repository, at a fixed 4,000-token `pack-diff` budget,
against a full-repository-access baseline and an independently-built 15-item
ground-truth list, before any of this session's fixes existed and again
after each stage:

```
before these fixes:  pack-diff returned an empty pack (the query-size bug)
after the bug fixes:            4/15 ground-truth items, 37,306 tokens
after evidence widening:       11/15 ground-truth items, 38,186 tokens
after fair-share allocation:   12/15 ground-truth items, 37,036 tokens,
                                plus 2 findings a 100,416-token,
                                full-repository-access baseline missed
```

This is a single diff and a single reviewing model, not a statistically
validated benchmark -- no claim here generalizes beyond it. A synthetic
regression fixture reproducing the diff's key structural properties (a
genuinely modified file carrying real risk, mixed with a large batch of
newly-added source, SQL, CI, config, and test files) is checked in at
`tests/test_evidence.py::test_mixed_diff_represents_every_evidence_category_within_budget`
so these results are guarded going forward without depending on the private
repository the original diff came from.

# 1.0.0

- Added bounded, confidence-decayed dependency closure with explicit provenance.
- Replaced regex-only JS/TS definition ranges with Tree-sitter-backed exact
  function, class, method, interface, type, enum, and arrow-function spans.
- Added `pack-diff` and `review` commands for changed-symbol context, dependency
  impact, public-signature changes, removed symbols, and missing-test signals.
- Added a persistent MCP index service with `index_status`, `refresh_index`,
  `build_diff_context`, and `review_diff` alongside the v0.9 tools.
- Added paired agent-outcome evaluation. Savings claims are suppressed when the
  enabled condition does not preserve baseline task success.
- Added Codex, Claude Code, Cursor, and GitHub Actions integration artifacts.
- Added lexical normalization for common code-task inflections and structural
  terminology while retaining deterministic, inspectable scoring.
- Included benchmark: 96% file recall, 100% symbol recall, 92.94% estimated
  context reduction across 25 repository tasks at a 6,000-token cap.

# 0.9.1

- Fixed symbol selection when task vocabulary appears in a definition body but
  not its name or signature, including ambiguous CLI `main` functions.
- Hardened corrupted-cache handling, atomic index durability, and private cache
  permissions without changing the v0.9 on-disk schema.
- Made selector evaluation reproducible by excluding dirty-worktree and learned
  feedback boosts. On the expanded v0.9.1 corpus the included benchmark reports
  92% relevant-file recall and 88% relevant-symbol recall; no 100% claim is made.

# 0.9.0

- Upgraded the content-addressed index to store symbol ranges, signatures,
  parent classes, and per-symbol calls with automatic v1 cache invalidation.
- Added exact symbol-body context packing through `--target-symbol`, structured
  JSON output, selected-symbol metadata, and high-confidence secret redaction.
- Added `acco impact` for explainable file/symbol blast-radius analysis
  across imports, callers, and related tests.
- Added bounded local relevance feedback and a ground-truth context evaluator
  measuring file recall, symbol recall, and token reduction.
- Added a 25-task repository benchmark manifest and a dependency-free stdio MCP
  server exposing context, symbol lookup, impact, and feedback tools.
- Hardened repository scanning against sensitive paths, generated/vendor trees,
  escaping symlinks, and oversized context exposure.
- Full suite: 259 tests pass in the release environment.

# 0.8.0

- Added an incremental, content-addressed repository index. It extracts symbols,
  imports, calls, and normalized identifiers and reuses unchanged records.
- Added dependency and symbol-call graph expansion with configurable hop depth
  and distance-decayed ranking boosts.
- Added identifier-based near-duplicate suppression before context allocation.
- Added opt-in session working-set memory. Previous files are boosted only for
  follow-up queries sharing task terms, reducing stale-context carryover.
- Added optional local sentence-transformer reranking through the `embeddings`
  extra. Default behavior remains deterministic and dependency-free.
- Added atomic persistence for indexes and working sets, CLI controls, ranking
  explanations, and regression tests for every new subsystem.
- Full suite: 250 tests pass on Python 3.12 in the release environment.

# 0.7.0

- Added task-aware context packing with `acco pack` and the standalone
  `acco-pack` entry point.
- Added dependency-free BM25-style source ranking with stronger path and symbol
  weights, Git working-tree/staged-file boosts, and structural-priority fallback.
- Context packs combine compact outlines with exact line-numbered source windows
  around high-signal task matches instead of summarizing editable code.
- Added hard estimated-token caps, file-count/window controls, Git-ignore support,
  ranking explanations, and output-to-file support.
- Added conservative compression of consecutive duplicate lines in successful
  command output while keeping failures and diagnostics untouched.
- Added CI on Python 3.10 and 3.12 and regression coverage for relevance ranking,
  budget enforcement, exact source windows, dispatcher compatibility, JSON
  compaction, and failure preservation.
- Kept all 0.6 lifecycle, audit, recovery, source-read, and benchmark behavior;
  the new top-level dispatcher isolates `pack` from the mature legacy CLI.

ACCO still does not claim a universal end-to-end savings percentage.
Task success and paired-run measurements remain the standard for savings claims.

# 0.6.0

- Corrected Bash replacement to the documented structured `updatedToolOutput`
  contract. Unsupported/image/interrupted outputs pass through.
- Preserved stderr and failure diagnostics. Shortened outputs are saved privately
  and recoverable by ID/range, without re-executing commands. Saving failures
  leave original output visible. Added `output` and `outputs-prune` commands.
- Scoped read state by project and session, with locked read-modify-write
  transactions, unique temporary files and atomic replacement. Compaction resets
  are installed. Only verified full-read contents are recorded.
- Removed the Stop hook's reliance on undocumented usage fields. Lifecycle advice
  remains based on explicit transcript analysis, not invented live usage.
- Tightened Read ranges: offsets alone and oversized/invalid limits no longer
  bypass the context budget. Relative paths resolve against the hook project.
- Replaced JS/TS snippet boundaries with Tree-sitter, added qualified names and
  ambiguity errors, removed silent 120-line truncation, and improved outlines.
- Excluded first cache observations and compaction epochs from suspected
  recreation. Reported only suspected overlapping prefixes, not all new tokens.
- Scoped repeated-read analysis by session and compaction epoch; stopped
  describing every repeat as waste. Preserved final streaming usage totals.
- Added explicit model/TTL pricing, with incomplete-cost results for unknown
  prices or TTLs. Unknown image sizes no longer use base64 length as token cost.
- Added paired-run benchmark evaluation including failed-attempt costs and
  quality outcomes. Removed historical savings percentages and absolute-ceiling
  claims without reproducible supporting data.
- Made settings updates atomic and refused malformed settings; preserved
  unrelated hooks sharing a matcher. Updated templates and upgrade guidance.

Validation: regression tests cover these fixes and subprocess hook transport.
See VALIDATION.md for executed results. A live Claude Code integration run and
real-task savings benchmark remain unexecuted; BENCHMARKING.md supplies the
protocol. The Windows locking branch is implemented but was not run on Windows.
