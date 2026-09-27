# Validation for 1.22.0

## 1.22 workspace federation and whole-context orchestration

Version 1.22 adds two orchestration layers above ACCO's existing repository and
provider boundaries while retaining repository-local source authority and
fail-closed host integration.

Mechanical validation covers:

- a single host transport registry that distinguishes automatic foreground
  interception, automatic durable attachment, environment-only persistence,
  manual-setting persistence, and unsupported provider routing without
  rewriting undocumented host state;
- durable Claude/Codex provider mapping derived from that registry plus
  machine-readable `acco transport-status` reporting;
- workspace manifests with explicit repository identities, duplicate/path
  guards, bounded direct-child discovery, lifecycle operations that never
  mutate repository contents, and package dependency edges from
  package.json, pyproject.toml, Cargo.toml, and go.mod;
- federated workspace retrieval that calls each repository's existing
  `RepositoryContextService`, ranks/selects repositories, reserves at most a
  bounded dependency slot, divides one hard global token budget, and retains
  per-repository selected-file/scanned-file provenance;
- deterministic whole-context allocation across source, history, memory,
  historical tool results, tool schemas, and reserve with exact integer token
  conservation, task/complexity/risk policy, and observed-demand caps;
- opt-in runtime configuration so existing projects keep historical behavior
  unless `[context_budget]`, `acco pack --context-budget`, or provider-proxy
  budget configuration is explicitly enabled;
- source-pack enforcement of only the allocated source slice while preserving
  the caller's explicit source cap;
- provider-side enforcement limited to schema and historical tool-result slices
  that ACCO can already compress recoverably; history and durable-memory slices
  remain explicit orchestration guidance rather than hidden mutation;
- Python SDK, loopback SDK bridge, and TypeScript-client parity for
  `/v1/context-budget`.

The combined post-rebase feature state passed the complete 19-job CI matrix on
the final PR head before merge, including Python 3.10/3.12/3.13, native Windows
full-suite/retrieval/product-UX gates, TypeScript SDK, Rust/HNSW parity, frozen
retrieval holdout, ranking regression, real CLI-output corpora, and standalone
Linux/macOS/Windows x86_64 and ARM64 smoke tests.

These checks establish deterministic allocation, hard-budget behavior,
cross-repository provenance, host-capability honesty, and cross-platform
mechanics. They do **not** establish that the new allocator has learned an
optimal allocation policy or that the full ACCO stack improves production cost
per successful task. Quality-gated allocation calibration and fresh paired
whole-system evaluation remain separate evidence requirements.

## 1.21 persistent provider runtime and optional domain middleware

Version 1.21 expands ACCO's provider-boundary product and SDK surface without
changing retrieval/ranking authority.

Mechanical validation now covers:

- broader `acco wrap` inference for provider-aware arbitrary CLIs, preserving
  custom upstream gateways and refusing ambiguous multi-provider environments;
- documented GitHub Copilot BYOK environment routing, including Azure base-URL
  semantics, plus Cursor's manual documented BYOK bridge instead of private
  settings mutation;
- OpenClaw direct-provider wrapping through temporary sibling config overlays,
  with exact catalog metadata, cleanup after exit, and fail-closed handling for
  OAuth/native/custom transports, implicit runtime ambiguity, or fallbacks that
  could bypass ACCO;
- project/provider persistent proxy profiles with stable port reservation,
  credential-free manifests, verified instance health before host mutation,
  runtime-policy parity with `.acco.toml`, and current-user autostart on Linux,
  macOS, and Windows;
- reversible project-scoped Claude/Codex attachment, ownership preflights,
  invalid-config refusal, native-service restart on reconfiguration, upgrade-
  stable launcher paths, and transactional rollback on multi-provider failure;
- Python and TypeScript RAG/API/database middleware over caller-supplied
  JSON-compatible data, sharing the production JSON compactor, minimum-
  reduction gates, and exact canonical-JSON recovery;
- recovery-capacity fail-open behavior and strict JSON validation so structured
  middleware never silently stringifies arbitrary application objects.

The full 19-job CI matrix remains a release gate across Python 3.10/3.12/3.13,
native Windows, TypeScript SDK, Rust/HNSW parity, ranking regression, frozen
holdout, real CLI-output corpora, and standalone Linux/macOS/Windows x86_64 and
ARM64 smoke tests.

These checks establish lifecycle, safety, recovery, and cross-platform
mechanics. They do **not** establish that persistent proxy mode or the optional
RAG/API/database adapters improve end-to-end coding task success or reduce
production cost per success. Those claims still require fresh paired workloads
with independent verification and provider-complete usage accounting.

## 1.20 native distribution and trust surface

Version 1.20 expands ACCO's installation/release contract rather than its
retrieval algorithms. Validation now requires native standalone builds and
provider-free smoke tests on six hosted-runner targets: Linux x86_64/ARM64,
macOS ARM64/Intel, and Windows x86_64/ARM64. Product tests also require
deterministic platform-to-asset mapping, checksum rejection, Linux/macOS atomic
replacement, Windows post-exit replacement, and package-manager ownership
preservation for Homebrew/WinGet.

Release engineering additionally renders Homebrew and WinGet metadata from the
published asset hashes and supports optional Authenticode and Apple Developer
ID/notary flows when publisher credentials exist. SHA-256 sidecars and GitHub
build-provenance attestations remain independent integrity evidence. External
Homebrew-tap and WinGet-community publication is explicitly token/upstream
gated and is not counted as complete merely because manifests are generated.

These checks establish native installation, update, packaging, and release
integrity mechanics. They do not create a new token-savings, API-cost, or
task-success claim.

## 1.19.1 Windows standalone lifecycle

Version 1.19.1 is a patch release over the first-class Windows support in 1.19.0. It adds checksum-verified standalone self-update behavior: the frozen Windows executable downloads the latest Windows asset and SHA-256 sidecar, verifies integrity, smoke-tests the replacement, and schedules the executable swap after the running ACCO process exits. The update path is covered by focused unit tests plus the same native Windows CI, standalone-binary smoke, and cross-platform regression matrix used for 1.19.0.

## 1.19 native Windows support

Version 1.19 promotes Windows from a packaged artifact to a release-gated runtime
platform. CI now runs the complete Python suite on GitHub's native
`windows-latest` runner, then executes the same retrieval-quality evaluation
used by the Linux matrix plus provider-free product-UX checks.

The Windows gate specifically covers:

- project setup/runtime imports and all ordinary Python tests on Windows;
- multi-process state updates through Windows advisory locking;
- repository-relative continuity paths normalized independently of `\\` vs
  `/` host separators;
- Docker benchmark/grader helpers without POSIX-only `getuid/getgid`
  assumptions;
- large-source Bash/`cat` guarding when file arguments contain Windows paths;
- PowerShell completion syntax and the PowerShell standalone installer syntax;
- provider-free `acco demo` and the standard context-quality retrieval suite.

Standalone `acco.exe` provider wrapping is also covered mechanically: frozen
executables re-enter themselves as `acco.exe provider-proxy ...` rather than
attempting Python's `-m acco.entry` invocation. The Windows installer verifies
the release checksum, smoke-tests the installed executable, and manages the
user PATH idempotently.

These checks establish platform/runtime compatibility. They do not create a new
token-savings, API-cost, or task-success claim.

## 1.18 onboarding and distribution mechanics

Version 1.18 makes the existing optimizer substantially easier to install and
operate without changing ACCO's evidence standards. Mechanical validation
covers the project-aware bare `acco` home screen, persistent
`uvx acco bootstrap`, one-command setup/index/readiness, managed Claude Lean
installation with user-modification preservation, automatic host selection for
`acco start`, the simplified status/demo/savings surfaces, and explicit
package-manager upgrades.

Release validation additionally smoke-tests tagged single-file executables on
Linux x86_64, macOS arm64, and Windows x86_64. Each release binary must run
`acco --help` and a provider-free repository `acco demo` before upload, and
is published with a SHA-256 sidecar. The release-scoped Homebrew formula is
rendered only after the Linux/macOS checksums exist.

These checks establish onboarding, packaging, ownership, and local-measurement
correctness. They do **not** turn local token-reduction estimates into API
billing savings or create a new universal cost-per-success claim.

## 1.16 custom-agent, provider-boundary, and browser-context mechanics

Version 1.16 expands ACCO beyond coding-CLI-only integration while preserving
the existing retrieval-first authority and exact-recovery contract.

Mechanical validation covers:

- `acco trial` generation/execution boundaries: committed-HEAD isolation,
  paired baseline/enabled runs, independent verifier commands, transcript
  accounting, and an explicit non-publishable evidence label for local trials;
- `acco learn` session analysis from local Claude transcript evidence without
  promoting estimated opportunity sizes into measured savings claims;
- the in-process Python `AccoEngine`, framework-neutral middleware, loopback
  SDK bridge, and typed TypeScript client sharing the same Python
  optimization/recovery implementation rather than duplicating policy;
- provider-shape detection for Anthropic Messages, OpenAI Chat Completions /
  Responses, and Gemini generateContent/streamGenerateContent, with transforms
  restricted to tool schemas and explicit historical tool/function outputs;
- byte-preserving provider request passthrough when no ACCO transform is
  accepted, byte-for-byte provider response forwarding, and optional
  content-free provider usage counters kept separate from transcript usage to
  avoid silent double counting;
- caller-supplied HTML, accessibility/ARIA snapshots, and browser-shaped JSON
  focusing with rarity-weighted query relevance, bounded structural/actionable
  context, hidden/noise suppression, exact `tsr_...` recovery, and
  minimum-size/unprofitable-transform fail-open behavior;
- ordinary JSON remaining on the general context router and browser
  specialization never gaining navigation, arbitrary URL-fetch, page-code
  execution, OCR, or screenshot-analysis authority.

The release also keeps the 1.15-to-1.16 retrieval changes under the existing
external regression discipline: the self-benchmark is 100% for file, symbol,
and scoped-symbol recall, the documented 471-task external comparisons report
only observed non-regressing improvements, and semantic holdout #15 remains
frozen but unevaluated.

These checks establish implementation/safety invariants and retrieval
regression control. They do **not** establish a new universal provider-token,
API-dollar, task-success, or cost-per-success improvement. The unresolved
publication-grade paired-agent evidence requirements below remain in force.

## 1.15 ACCO identity and packaging mechanics

Version 1.15 completes the rename to **ACCO — AI Coding Context Optimizer**.
The canonical PyPI distribution, Python import, CLI, MCP/plugin id, config/state
namespace, source folder, and optional Rust module all use ACCO identifiers.

Validation covers packaging/import/CLI consistency, documentation version
alignment, managed integration identifiers, Rust/Python parity, and replay of
historical frozen benchmark manifests through explicit compatibility
normalization. Frozen evidence files themselves are not rewritten.

These checks establish rename and packaging correctness. They do not create a
new retrieval-quality, task-success, or cost-savings claim.


## 1.14 multi-host integration mechanics

Version 1.14 expands managed integration lifecycle coverage from Claude Code,
Cursor, and Codex to OpenCode, OpenClaw, Hermes Agent, GitHub Copilot CLI /
VS Code, and Google Antigravity.

The release evidence here is **configuration/lifecycle correctness**, not a claim
that every host exposes identical proprietary hooks or produces identical
end-to-end token savings.

Tests require that:

- setup/detection/uninstall preserve unrelated host MCP entries;
- repeated setup is idempotent on managed surfaces;
- OpenCode refuses ambiguous sibling JSON/JSONC project ownership;
- OpenClaw uses its native MCP registry command rather than rewriting JSON5;
- Hermes refuses unmanaged same-name entries and ambiguous/unsupported
  `mcp_servers` structures;
- Copilot CLI uses its native MCP registry, preserves unrelated entries, and
  refuses to replace an unmanaged `acco` definition;
- VS Code Copilot detection does not treat a generic VS Code installation alone
  as proof of Copilot use;
- `--host all` selects detected supported products instead of requiring every
  supported host to be installed;
- capability reporting marks MCP support explicitly while proprietary
  pre/post-tool, prompt, session, provider, and model-routing boundaries remain
  conditional/unknown unless ACCO can actually guarantee them.

These checks establish safe configuration ownership and lifecycle behavior.
They do not establish live host acceptance of every MCP capability, native hook
interception parity, task-success equivalence, or an end-to-end savings figure
for the newly added hosts.

## 1.13 recoverable optimization-platform mechanics

The recovery/schema/proxy/prefix/optimizer/browser additions are covered as
**mechanical and safety evidence only**. They do not yet support a new
end-to-end token, dollar-cost, task-success, or cost-per-success claim.

Tests require that:

- exact recovery is content-addressed, SHA-256 verified, private, deduplicated,
  and refuses a new lossy transform instead of evicting old source when capacity
  is exhausted;
- MCP schema compression preserves names, user-defined property identities,
  required/default/const/enum construction semantics, and recognized constraint
  sentences, while the exact original catalog remains recoverable;
- the adaptive MCP core always retains `recover_context` and bounded discovery
  replaces rather than accumulates specialist tools;
- provider request transformation falls back to the original complete request
  when exact recovery cannot be stored;
- stable-prefix reuse evidence excludes the latest user turn and persists only
  content-free fingerprints/counters;
- the provider reverse proxy refuses non-loopback binding unless explicitly
  permitted, refuses non-local plaintext HTTP upstreams, cannot let an
  absolute-form request target escape the configured upstream origin, and does
  not automatically follow upstream redirects;
- browser focusing operates only on caller-supplied captured payloads, preserves
  the requested neighborhood/actionable skeleton, and returns the original when
  exact recovery cannot be guaranteed;
- optimizer mutations first save exact config bytes and can automatically restore
  them when sufficient provider-reported treatment turns do not improve the
  configured tokens-per-turn threshold.

These checks prove implementation invariants, not model quality equivalence.
A publishable savings claim requires a fresh paired-agent experiment in which
the optimized arm actually exercises these mechanisms, both arms receive
independent task verification and blind quality grading, provider usage/cache
counters are complete, and cost-per-success passes the existing publication
gate.

## 1.13 persistent-memory and adaptive-MCP mechanics

The new project-memory and adaptive tool-surface features are mechanically
validated but do not yet carry an end-to-end savings claim.

Tests establish that:

- typed memory persists across service instances while retaining source anchors;
- changed or missing source digests quarantine stale memory before ordinary recall;
- near-duplicate active memory on the same source evidence is superseded rather
  than silently competing;
- progressive disclosure keeps full evidence out of `memory_index` and
  `memory_search`; `memory_get` returns it only after ids are explicitly selected;
- full memory access updates bounded reuse metadata without changing source truth;
- the adaptive MCP profile starts from a smaller schema than `full`;
- `discover_tools` selects deterministic task groups, expands the live surface,
  and advertises `listChanged=true`;
- static `minimal`, `context`, and backward-compatible `full` behavior remains
  available.

These tests do **not** establish that persistent memory reduces total agent
tool calls, that adaptive tool disclosure reduces billed input after host-side
tool caching/deferred loading, or that either feature preserves task success in
real coding work. Any such claim requires a fresh frozen paired-agent experiment
with actual tool-use exposure, independent success verification, and measured
usage/cost counters.


The 1.12 semantic-query ensemble is mechanically validated and has now also
been evaluated on fresh semantic holdout #14. Long prompts may use the full
query plus at most two deterministic exact-vocabulary subviews, fused before
the existing file-level semantic stage. Short prompts remain single-view and
warm query vectors remain persistent. Holdout #13 was not used to tune or score
that release, and holdout #14 was frozen independently before its first run.

ACCO separates **mechanical correctness**, **retrieval generalization**,
and **end-to-end agent economics**.

Version 1.14.0 adds managed OpenCode, OpenClaw, Hermes, Copilot CLI / VS Code, and Antigravity integration lifecycle support on top of the existing Claude Code, Cursor, and Codex adapters. The new evidence is configuration/lifecycle evidence only; no new live-host savings or task-success claim is made from adapter tests alone.

Version 1.13.0 adds progressive persistent project memory, adaptive MCP tool disclosure, recoverable MCP schema compression, universal exact-byte recovery handles, a measured keep-or-revert optimizer, content-free provider-prefix reuse evidence, an opt-in hardened local provider proxy, and focused recoverable browser-context compression. These additions are mechanically and safety validated; no new end-to-end savings percentage is claimed without fresh paired-agent evidence.

Version 1.12.0 adds automatic capability/cost-aware model routing,
quality-gated routing calibration, the centralized freshness-gated Claude
pricing registry, and the measured cost-efficiency advisor. Calibration may
relax one exact routing bucket only after frozen paired model experiments,
independent task-success verification, complete blinded quality grading,
transcript-confirmed model identity, and the documented hard sample/success
floors. The release also includes the multi-view semantic-query ensemble. Its
fresh external semantic evidence is the first complete holdout #14 run described
below; later reruns of #14 are development evidence only because the suite was
burned by that first evaluation.

The 1.10 semantic mechanism is covered by deterministic tests that establish:

- chunk vectors and exact-query vectors persist across fresh service instances;
- a repeated unchanged repository/query can reuse semantic state without
  invoking the encoder again;
- changed repository digests re-embed only changed files;
- live source bytes must still match the structural RepositoryIndex digest
  before vectors can be persisted;
- semantic hits contribute explicit chunk coordinates and hybrid-RRF ranking
  evidence;
- final context still contains exact live source rather than a generated
  semantic summary;
- optional HNSW is an acceleration sidecar over authoritative SQLite vectors,
  with exact cosine scan as the semantic fallback.

Those tests establish implementation correctness and safety. They do **not**
establish a new external natural-language recall number.

Semantic holdout #13 has now been consumed exactly once as fresh evidence.
Its 24 query/revision definitions were committed before ground-truth lookup at
`f3247c1d4c8e388de653aea1a5de4fa4624f82ce`, with query-freeze SHA-256
`8cdf871ea2fcbe59161a332f1f0ce0f93b087a6c3560acebadb5ee338c4169bf`.
After answer lookup, two tasks were conservatively classified as
identifier-bearing and excluded without changing their query text, leaving
**22 eligible natural-language tasks** across six previously unused
repositories/language ecosystems.

The final definition is sealed as
`dc6ea6c3641db573b5b05473f2bc4ee13e0f05a4f093cb86f803e68c7b265d25`.
The first real run was GitHub Actions **35537362040**, using pinned
`all-MiniLM-L6-v2` revision
`bc57282bc374d33e0d6c4de27f12dc1c2a87f37a` with exact cosine:

| Arm | File recall |
| --- | ---: |
| ACCO hybrid semantic | **50.00% (11/22)** |
| ACCO lexical/structural | **45.45% (10/22)** |
| Trivial distinct-term lexical | **40.91% (9/22)** |

The semantic arm recovered one task missed by ACCO lexical/structural
and introduced zero regressions. Mean estimated context reduction remained
essentially unchanged (97.8374% semantic vs 97.8373% lexical).

This is modest positive retrieval evidence, not proof of a strong semantic
generalization advantage and not an API-cost/task-success claim. Holdout #13 is
now **burned**. The semantic-retrieval-v3 changes (structure-aware chunks,
multi-hit file aggregation, lexical-independent semantic fusion, and bounded
semantic-witness graph expansion) were deliberately not tuned or scored against
#13.

Semantic holdout #14 was then frozen independently with query-freeze SHA-256
`2b96b273353c0dd76da0dd8bcdcd7a0cdbb93ca253b43409ff4fee2734d95f4a`
and ground-truth SHA-256
`c1d16ce0289305533055de2406143d692e82f7bca35e2fc47f054306d3f9ed92`.
It covers 24 issue-derived queries across Click, Echo, ripgrep, Mockito, Vite,
and ASP.NET Core; four tasks were conservatively excluded after ground-truth
review, leaving **20 eligible no-identifier-leakage tasks**.

The first complete fresh run was GitHub Actions **35615316639**, using the same
pinned `all-MiniLM-L6-v2` revision and exact cosine:

| Arm | File recall |
| --- | ---: |
| ACCO hybrid semantic | **82.50%** |
| ACCO lexical/structural | **80.00%** |
| Trivial distinct-term lexical | **70.00%** |

Semantic improved aggregate file recall by **2.5 percentage points**, introduced
**zero regressions**, and partially recovered one two-file ASP.NET Core target
without producing a complete task recovery. Mean estimated context reduction
was effectively unchanged (98.9516% semantic vs 98.9515% lexical).

That first run permanently **burned holdout #14**. A later development rerun
after structural-authority improvements reached 87.5% semantic recall versus
the same 80.0% lexical recall with zero regressions, but it is not fresh
generalization evidence and must not replace the 82.5% first-run result in
public claims.

Holdout #15's 24 natural-language queries and six pinned repository revisions
were frozen first in `benchmarks/semantic-holdout-15.query-freeze.json`. Ground
truth is frozen in `benchmarks/semantic-holdout-15.frozen.json` (ground-truth
SHA-256 `54df820439ab107e22ce5375b7ce5d4f170e93f15180633ea86c1808abeb2b1f`),
with the queries unchanged. Expected files come mechanically from each issue's
merged upstream fix: its non-test, non-documentation source files that exist at
the pinned revision, dropping files changed by two lines or fewer when the same
fix has a larger change.

The canonical first evaluation was GitHub Actions **36041192049**, using pinned
`all-MiniLM-L6-v2` revision
`bc57282bc374d33e0d6c4de27f12dc1c2a87f37a` with exact cosine and no HNSW.
Of 24 frozen tasks, 13 are eligible for the no-identifier-leakage headline, 8
are excluded as identifier-bearing, and 3 are excluded because no source target
could be established.

| Arm | File recall |
| --- | ---: |
| ACCO lexical/structural | **82.05%** |
| ACCO hybrid semantic | **71.79%** |
| Trivial distinct-term lexical | **50.00%** |

Semantic was **10.26 percentage points below** ACCO lexical/structural on this
fresh cohort. It produced **0 semantic-recovered tasks** and **1 strict semantic
regression** under the existing headline flag
(`gson-wildcard-runtime-subclass`, 100% -> 0% file recall). Per-task recall
also decreased on `polly-timeout-caller-token` (66.67% -> 33.33%), which is
not counted by the strict regression flag because lexical recall was already
partial. No eligible task had higher semantic file recall than lexical.

Mean estimated context reduction was effectively unchanged:
**97.7220% lexical vs 97.7233% semantic**. The result therefore does not support
a broad claim that the current semantic layer improves retrieval over ACCO's
lexical/structural ranker. Holdout #15 is now **burned** and must not be used to
tune and then rescore a fresh-generalization claim.

The six repository shards from run 36041192049 all completed successfully.
Its original merge-only step exposed a harness bug: axum has zero eligible
headline tasks, so its valid shard contains only excluded tasks and an empty
repository summary; the merger incorrectly treated that as missing repository
coverage. The merger was fixed to infer excluded-only shard identity from the
frozen manifest. A merge-only recovery run, **36042684955**, downloaded and
merged the six immutable artifacts from 36041192049 without rerunning retrieval
or embeddings and verified the literal headline above.

**Duplicate-run disclosure.** A second run (**36041240323**) was accidentally
triggered while checking whether GitHub had registered the newly created
workflow. It started before any result from 36041192049 had been observed and
used no changed retrieval code or frozen data. It is ignored for all headline
evidence; 36041192049 is the canonical first-triggered evaluation.

**Independence disclosure.** The ground truth was collected by the same agent
that developed ranking changes #106-#109 in the same session. ACCO was not run
on these repositories before the freeze. Four of the six repositories (chi,
gson, Polly, express) are pinned at the same revisions as external holdouts #5,
#6, #8 and #2, which served as regression guards during that development, and
one change (the CommonJS alias exclusion in #107) was motivated by an express
regression. Results on those four repositories are therefore not fully
independent of the changes being measured; werkzeug and axum use revisions not
used before. The eligible headline contains 11 tasks from those four
regression-guard repositories and 2 from werkzeug; axum contributes no eligible
headline task, so the cleaner independent subset remains small.


Semantic holdout #16 is the fresh post-confidence-gate generalization suite.
Its query layer was frozen **before ground-truth collection** at commit
`90bd16be19f85c6234c3a020d2c805db7722d208`, with query-freeze SHA-256
`f485dac4cef84caeefadc477e932b28734e0d13111671f119f9b70dad387f958`.
Ground truth was then derived mechanically from merged upstream fixes and sealed
with SHA-256
`14fb1e24745a803482eebb3229c7f72bd1d26222f3a9cd3b09101b4f158352e9`.

The suite contains **18 headline-eligible tasks across six repositories not
present in ACCO's checked-in prior semantic/external holdout evidence**:
HTTPX, Requests, serde_json, Jackson Databind, Pydantic, and Trio. The cohort
spans Python, Rust, and Java, with repository revisions pinned in
`benchmarks/semantic-holdout-16.query-freeze.json`. The same
case-insensitive answer-identifier audit used by earlier semantic suites finds
**zero literal identifier leaks** across all 18 queries.

The expected-file rule is unchanged from holdout #15: non-test,
non-documentation source files changed by the merged upstream fix and present at
the pinned revision are retained, while source edits of two lines or fewer are
dropped when the same fix contains a larger source edit. Two Requests tasks use
the merged pull request's problem statement because no separate issue was
selected; this weaker independence is frozen in the manifest disclosure rather
than hidden after results are known.

Holdout #16's **first and canonical fresh evaluation** is GitHub Actions run
**36122836318**. All six repository shards and the merge job completed
successfully using the frozen revisions, pinned
`all-MiniLM-L6-v2` revision
`bc57282bc374d33e0d6c4de27f12dc1c2a87f37a`, exact cosine, and no HNSW.

| Arm | Fresh file recall |
| --- | ---: |
| Trivial distinct-term lexical | **71.76%** |
| ACCO lexical/structural | **62.96%** |
| ACCO gated hybrid semantic | **56.02%** |

The gated semantic arm is **6.94 percentage points below** ACCO
lexical/structural and **15.74 points below** the trivial lexical baseline.
It produced **0 strict semantic recoveries** and **1 strict semantic
regression**. No eligible task had higher semantic file recall than lexical.

The strict regression is `httpx-head-empty-zstd`, where the lexical arm
recalled the expected decoder file at **100%** and the semantic arm fell to
**0%**. There is also a partial-recall decrease on
`jackson-decimal-biginteger-scale` (**25% -> 0%**), which is not counted by
the suite's strict regression flag because lexical recall was already partial.
Mean estimated context reduction was effectively unchanged:
**97.9636% lexical vs 97.9646% semantic**.

This is a meaningful negative generalization result. The confidence gate fixed
the burned #15 regressions but did **not** establish a general semantic
advantage on a fresh cohort. More broadly, ACCO's lexical/structural arm also
underperformed the deliberately simple distinct-term baseline on #16, so the
fresh evidence points to a wider retrieval-ranking gap rather than a
semantic-only problem.

Two Requests tasks use merged pull-request problem statements rather than
separate issue text, as disclosed before evaluation. The headline above retains
all 18 frozen eligible tasks exactly as defined; no task is removed or
reweighted after seeing results.

Holdout #16 is now **burned for tuning**. Later executions are development /
regression evidence only and must not replace run 36122836318 as the fresh
headline. Any fix motivated by #16 needs a newly frozen suite before ACCO can
claim fresh generalization.

A post-run **burned diagnostic** separated ranking quality from context-packing
coverage before the next fresh suite was defined. On the unchanged #16 tasks:

- ACCO lexical rank@12 recall is **83.80%**, versus **71.76%** for the trivial
  distinct-term rank@12 baseline;
- the canonical 6k ACCO pack rendered only **5.61 files on average**, reducing
  that stronger ranking to the **62.96%** fresh pack headline;
- when the trivial baseline is truncated to the same per-task file count as the
  ACCO pack, its recall is only **43.98%**.

This shows that the apparent +8.8-point trivial advantage in the fresh headline
was primarily a **rank-to-pack allocation confound**, not evidence that
distinct-term ordering was stronger.

The coverage-aware allocation candidate in PR #123 was then replayed on burned
#16 as development evidence only. It preserves a compact evidence budget for
later high-ranked files before spending surplus on depth. With the same 6k hard
cap it reaches **82.41% pack file recall**, selects **11.56 files on average**,
and uses **5995.5 tokens on average**, versus **5993.7 tokens** before the
change. Five tasks improve and none regress. This nearly realizes the existing
83.80% rank@12 recall without increasing the configured token budget.


PR #122 independently developed a stricter rank-preserving allocator on the
same burned diagnosis. After resolving its overlap with #123 against current
`main`, the #122 policy reserves the packer's existing **300-token compact
exact-source minimum** for every leading candidate that the hard budget can
support, while retaining extra allowance for structural authority, explicit
priority-file behavior, and the one-hop authoritative-provider reserve.

Its burned #16 development replay reaches **83.80% lexical pack recall**,
matching ACCO lexical rank@12, and renders **12.0 files on average** while
remaining below the same 6,000-token hard cap. This is stronger development
coverage than the earlier #123 candidate's 82.41% / 11.56-file result, but it is
still burned-suite evidence only and does not replace #16's canonical fresh
62.96% lexical-pack headline.

These figures are **not fresh generalization evidence**. They justify the
mechanism and regression tests; a separately frozen holdout #17 is required
before claiming that the allocation change generalizes.

Semantic holdout #17 is that separately frozen generalization test for the
coverage-aware allocator. Its issue-derived natural-language queries and six
previously unused repository revisions were frozen first at commit
`84aa439284cb47d1befcce88df58f8bf3c45408e`, with query-freeze SHA-256
`661361e6c55a24dbd6128898dcf92867ac644d4629a764a2493d20bed6736d95`.
Only after that commit was immutable ground truth collected from the merged
upstream fixes and sealed with SHA-256
`fe479ff78a43c14de108262242706fedf1324194d8be31be0f78827f2ab849a0`.

The suite contains **18 eligible tasks across six repositories absent from
ACCO's checked-in semantic/external retrieval holdouts**: pytest, Black,
Starlette, attrs, Resty, and anyhow. The canonical first evaluation is GitHub
Actions run **36131559625** at main commit
`801e8d9c0b89fdea87b07f72c9a4894f6146fe85`. All six repository shards and
the merge job completed successfully with pinned revisions, pinned
`all-MiniLM-L6-v2` revision
`bc57282bc374d33e0d6c4de27f12dc1c2a87f37a`, exact cosine, and no HNSW.

Holdout #17 records ranking and bounded-pack realization separately so the
rank-to-pack confound exposed by #16 cannot recur:

| Arm / surface | Fresh file recall |
| --- | ---: |
| Trivial distinct-term lexical | **80.56%** |
| ACCO lexical/structural rank@12 | **91.67%** |
| ACCO lexical/structural 6k pack | **91.67%** |
| ACCO gated hybrid semantic rank@12 | **91.67%** |
| ACCO gated hybrid semantic 6k pack | **91.67%** |

The coverage-aware allocator therefore generalized on this untouched cohort:
it selected **12.0 files per task on average** and incurred **0.00 percentage
points of rank-to-pack recall loss**. ACCO lexical/structural retrieval is
**11.11 percentage points above** the trivial distinct-term baseline while the
6,000-token pack preserves the complete measured rank@12 recall. Mean estimated
context reduction is **96.4954%** for lexical and **96.5043%** for semantic.

Semantic retrieval adds no measured value on #17: it produced **0 improved
tasks, 0 worsened tasks, 0 strict recoveries, and 0 strict regressions**, for a
net recall delta of **0.00 percentage points** versus ACCO lexical/structural.
This cleanly preserves the lexical result, but it does not provide fresh
evidence that embeddings improve retrieval. Semantic remains an optional
augmentation whose incremental benefit still needs independent evidence.

The two remaining retrieval misses are visible rather than hidden. The anyhow
temporary-lifetime task misses `src/macros.rs` in all three retrieval arms,
while Resty's multipart early-response task reaches **50%** recall on a
four-source-file ground truth in all three arms. The other 16 tasks reach full
ACCO lexical pack recall.

Holdout #17 is now **burned for tuning**. Later reruns are development evidence
only and must not replace run 36131559625 as the canonical fresh result. This
suite validates file retrieval and bounded packing, not model task success or
production-dollar savings. With packing generalization now demonstrated, the
largest remaining evidence gap is the paired end-to-end **cost-per-success**
experiment rather than another #17-driven ranking or packing retune.


Release CI is anchored to Linux across Python 3.10, 3.12, and 3.13 and requires:

- the complete pytest suite on every supported Python version;
- the deterministic context-quality evaluation;
- the frozen external holdout regression floor;
- PR base-vs-candidate ranking snapshots/diffs;
- Ruff correctness checks;
- 100% docstring coverage via interrogate;
- GitHub Actions workflow linting;
- an optional-Rust job that builds the PyO3 wheel, requires the native backend,
  checks Python/Rust primitive parity, reruns pack/retrieval tests, and reruns
  the deterministic context-quality benchmark;
- the hash-frozen session/output quality replay suite with preservation,
  no-hallucination, and minimum-reduction contracts.

Version 1.9.0 also adds three runtime/product mechanisms whose evidence
boundaries are intentionally narrower than an agent-cost claim:

- **prompt ingress staging** is covered by exact-original SHA-256 verification,
  bounded packet tests, explicit omitted-range recovery, hook ordering tests, and
  default-off configuration. Claude's prompt hook is used only to block before
  model processing; ACCO does not claim unsupported prompt replacement.
- **persistent retrieval caching** is tested across independent service
  instances. Identical content/config reuses a completed pack; a source mutation
  or retrieval-budget change produces a different cache key and a fresh pack.
  Cache-hit metadata is observable in CLI/MCP output.
- **Rust acceleration** is optional. Normal CI exercises the Python reference
  path; a separate native job builds the extension and requires the same
  primitive outputs plus the same pack/context-quality behavior. Failure to
  build/install Rust does not alter the supported Python runtime.
- **Claude marketplace packaging** is structurally tested for a complete
  generated plugin, stable hooks/MCP/skill content, and the command-source
  safety constraints (printable <=500-character command and <=600-second
  timeout). Actual Claude marketplace acceptance still depends on a supported
  Claude Code installation and is not inferred from JSON fixture tests alone.

These mechanisms may reduce repeated local work or prevent one oversized prompt
from reaching the model, but **1.9.0 makes no new end-to-end cost-savings
percentage claim from their existence alone**.

The 1.9 knowledge-efficiency layer has its own evidence boundary.
`knowledge_read_avoidance` and `cache_economics` are disabled by default.
The checked-in
`benchmarks/knowledge-efficiency-swebench-24.frozen.json` reuses the same 24
SWE-bench Verified tasks at three randomized paired trials per task. Both arms
run the same current ACCO binary, explicitly persist verified findings
during an identical no-edit investigation phase, and then enter a fresh
implementation session. Continuity, exact cross-turn deduplication, repeated-read
deduplication, and behavioral waste signals are disabled in both arms; only
knowledge-assisted full-read avoidance and its cache-economics acceptance gate
differ.

The accompanying paid/manual workflow represents **144 arm-runs / 288 Claude
task phases**, plus independent hidden verification and blind response grading.
It has **not been executed**. The stored mechanism tests and frozen protocol
therefore establish correctness/isolation only; they do not establish a real
reduction in tool calls, input tokens, billed cost, or cost per successful task.
**No knowledge-efficiency savings percentage is claimed** until the paid paired
run passes success parity, blind-quality parity, treatment-exposure/control-
isolation checks, complete cache-TTL-aware pricing, and a task-cluster 95%
confidence interval whose cost-per-success reduction lower bound is above zero.

Version 1.8.0 adds a separate frozen session-efficiency
holdout rather than treating operational dashboard estimates as evidence. The
holdout reuses the existing 24 SWE-bench Verified task definitions, runs three
randomized paired trials per task, and compares the same current ACCO
binary with only the four session-efficiency switches changed. Each arm uses a
forced two-session protocol and independent hidden verification; transcript
metrics, blind response grading, exact cache-TTL-aware pricing, and task-cluster
bootstrap intervals feed the publication gate.

The checked-in holdout definition is frozen and mechanically validated, but the
new paid **144 arm-run / 288 Claude-phase** workflow has not yet been executed
for this release candidate. Therefore **no session-efficiency savings
percentage is claimed for 1.8.0** merely from implementing the benchmark.

Version 1.7.0 adds a modular session-efficiency control plane: structured
continuity across resume/compaction, exact cross-turn command/read deduplication,
bounded retry/cascade waste signals, broader command-aware output processors,
and local operational savings dashboards. A new hash-frozen output-quality
fixture is enforced in CI alongside the existing external retrieval holdout and
ranking regression checks. It does **not** retune the frozen retrieval baseline
merely to improve release metrics.

Version 1.6.0 added the complete output-evidence control plane: automatic
task-aware budgets, runtime usage telemetry, cache-TTL-aware cost accounting,
deterministic blind A/B response grading, and the resumable experiment ->
verification -> grading -> cost-per-success -> calibration pipeline.

## Test suite and self-benchmark

- The release gate runs the full suite on Python **3.10, 3.12, and 3.13** rather
  than relying on a single interpreter.
- The included deterministic 25-task selector benchmark at a 6,000-token cap
  queries this repository's own tree, so its result is revision-specific and
  also depends on the prose of the files it indexes (including this one):

  | Revision | File recall | Symbol recall | Scoped symbol recall | Mean estimated reduction |
  |---|---:|---:|---:|---:|
  | `v1.5.0` (`2b4af9b`) | 92% | 92% | 88% | 98.71% |
  | `d816177` (1.15.0) | 72% | 88% | 80% | 99.38% |
  | this change | 100% | 100% | 100% | 99.38% |

- **Why it fell to 72%: the tree changed, not the ranking code.** 1.5.0-era
  ranking code on the `d816177` tree and `d816177` ranking code on the
  1.5.0-era tree each reproduce the tree's own result. Source roughly doubled
  (90 to 141 Python modules, 0.63 MB to 1.37 MB), and the new modules share
  vocabulary with the benchmark's natural-language queries.
- **Four tasks had stale ground truth** and now name where the code lives:

  | Task | Was | Now | Why |
  |---|---|---|---|
  | `impact-cli` | `commands.py` | `command_handlers/context.py` | `impact_main` is defined there; `commands.py` re-exports it |
  | `dispatcher` | `entry.py` (`main`) | `command_registry.py` (`dispatch`) | command routing moved; `entry.py` delegates (judgment call) |
  | `mcp-protocol` | `serve.py` | `mcp_server/protocol.py` | `serve.py` is a self-declared compatibility facade |
  | `filter-output` | `filter_output.py` | `output/processors.py` | `filter_output.py` is a facade; `GenericProcessor.compress` compresses successful output there |

  In each case the old file became a facade or delegator in a refactor, so the
  task no longer described it. The `filter-output` target was chosen after an
  initial choice (`output/text.py`, where `filter_text` now lives) turned out to
  share no terms with the query; treat it as a judgment call. These edits change
  the manifest's ground-truth hash and start a new calibration cohort.
- **Four tasks were ranking gaps, fixed by three general changes.** In each
  (`pricing`, `benchmark-runs`, `pack-cli`, `mcp-audit`) the expected file had
  the highest or near-highest BM25 score but was outranked by additive boosts:
  1. The `path` boost counts only the file's own name. A directory term
     (`packing/`, `mcp_server/`) is shared by every file beneath it, cannot tell
     them apart, and gave each the same +8. Directory terms still reach BM25.
  2. Python outlines lead with the module docstring summary, and argparse
     option names are weighted like outline terms for relevance but kept out
     of the stored outline (they are not symbols; putting them in the symbol
     boost let unrelated CLI handlers outrank `pricing.py`). `INDEX_VERSION` is
     bumped to 12 so cached indexes are rebuilt.
  3. While more candidates remain, an ordinary file may use 2/5 of the
     remaining budget instead of 3/5, so more ranked files fit. Files with
     `structural-symbol` evidence keep 3/5, because a uniform 2/5 share
     truncated defining files and dropped their target symbols on external
     holdouts.
- **External validation.** Every candidate was measured on 471 tasks from
  holdout suites 1-12 whose pinned repositories could be reproduced
  (`runtime`, `efcore`, `spring`, and `uuid` were not). The shipped
  combination: file recall 97.88%, symbol recall 90.45%, scoped symbol recall 87.26%
  (baseline 97.66% / 89.92% / 87.15%), with 4 tasks improved and 0
  regressed. The frozen CI floor (holdout #1) is unchanged at 83.3% / 83.3% /
  66.7%. These are burned suites: this is regression evidence, not fresh
  generalization evidence.
- **Candidates rejected** for regressing external tasks: inverse-document-
  frequency weighting of the `path`/`symbols` boosts (4 file regressions); a
  uniform 2/5, 1/2, or 1/3 budget share (1-3 symbol regressions each); a gate
  on `structural-authority` for single-word helpers (broke `outline`); a
  member-hint regex fix recovering overlapping `Container member` pairs (fixed
  `retrofit-builder-build`, broke `serilog-logger-information` on an
  identically shaped query); argparse flags added to the stored outline
  (displaced `pricing`).
- **Symbol selection and index coverage (follow-up).** After the change above,
  65 of the 471 reproducible external holdout tasks still missed. Classifying
  them (no ranking change) found 46 symbol-window-selection misses, 10
  file-ranking misses, 6 budget truncations, and 3 missing definitions. Two
  general fixes shipped:
  1. A request that spells a callable or variable's full name in code form
     (`Get`, `get()`, `` `run` ``, `should_bind_json`) credits that definition
     like an explicit `Container member` mention (+120), so a longer name that
     merely contains it (`ShouldBindBodyWithJSON` for `ShouldBindJSON`) no
     longer wins on term overlap. Lowercase prose words, types, constructors,
     and members that share a name with a type in the same file are excluded:
     a type named in a request is as often context as the answer.
  2. The index now records public Python module-level names bound to a call
     (`current_app = LocalProxy(...)`), CommonJS exports with a real value
     (`exports.etag = createETagGenerator(...)`, but not the alias
     `exports.request = req`), and a named function expression that is itself
     an export's value (`export default ok && function httpAdapter(...)`).
     `INDEX_VERSION` is now 13.

  External result (471 tasks): file 97.88% (unchanged), symbol 90.45% ->
  91.30%, scoped symbol 87.26% -> 88.75%; 8 tasks improved, 0 regressed
  (`axios-follow-redirects`, `express-generate-etag`, `lodash-get-path`,
  `flask-current-app-proxy`, `gin-json-response`, `viper-global-get`,
  `ct-function-instance-instance-impl`, `logrus-package-print`). Tasks with any
  miss: 65 -> 59. Self-benchmark stays at 100% / 100% / 100%.

  **Disclosure.** The first version of the exact-mention credit (all symbol
  kinds) was +7 / -6, and the first version of the index change also indexed
  `exports.request`-style aliases; the type exclusions and the alias rule were
  added after studying those regressions on these burned suites. Each rests on a stated mechanism rather than a score,
  but they were holdout-motivated, so only a fresh frozen holdout can show they
  generalize.

  **Duplicate child slot, budget-aware (shipped separately).** When one of a
  file's two symbol windows only repeats a child its selected container
  already renders, the next distinct definition is rendered as a backfill.
  A first version gave the backfill the freed slot's priority and regressed
  `tornado-schedule-callback` and `serilog-message-template-parse`: its source
  displaced lexical windows, and in tornado it clipped the outline, whose
  numbered lines are themselves visible evidence for a credited member
  (`call_later@598`). The shipped version keeps the primary selection exactly
  as before and renders the backfill after the outline, adding only lines no
  other window covers, so section fitting clips it before anything else.
  External result against the change above (471 tasks): file 97.88%
  (unchanged), symbol 91.30% -> 91.72%, scoped symbol 88.75% -> 89.17%;
  3 tasks improved (`scrapy-duplicate-request-filter`,
  `jackson-writer-write-string`, `pydantic-email-validation`), 0 regressed.
  Tasks with any miss: 59 -> 57. It recovers fewer tasks than the first
  version (2 scoped instead of 5) because it only spends budget nothing else
  needed. The remaining misses are dominated by requests that describe
  behavior without naming the target (40 of the 52 window-selection cases),
  which lexical scoring cannot close.
- **Compact fitting for clipped sections.** Budget fitting clips a section
  from the end, so a long early window could push the declaration of a later
  selected symbol out of the pack (`clap` `subcommand` behind an 85-line
  `_build_subcommand` body), and credited members that are only visible
  through the outline were lost when the outline was clipped. When a section
  must be clipped, a compact form (a short head window per labeled symbol,
  then the usual lexical windows and outline) is fitted as well and used only
  if it shows a strict superset of the clipped section's symbol labels and
  identities in no more tokens; otherwise the clipped section is kept
  unchanged. External result against the change above (471 tasks): file
  97.88% (unchanged), symbol 91.72% -> 92.04%, scoped symbol 89.17% -> 89.49%;
  2 tasks improved (`flask-exception-to-response`, `clap-command-subcommand`),
  0 regressed. Tasks with any miss: 57 -> 55. Four other truncation misses
  (`fastapi-validation-error-response`, `scrapy-scheduler-next-request`,
  `tornado-exception-to-error-response`, `rich-console-init`) are unchanged:
  their compact form did not strictly improve on the clipped section.
- **Semantic symbol matching: measured, not built.** Most remaining misses
  are requests that describe behavior without naming the target, which lexical
  scoring cannot close. Before building anything, the optional `semantic`
  extra (`all-MiniLM-L6-v2`) was measured as a within-file symbol ranker on
  every holdout task whose expected file is packed (488 expected symbols,
  suites 1-12). Top-2 placement of the expected symbol:

  | Ranking | Top-2 | Misses fixed | Current hits broken |
  |---|---:|---:|---:|
  | Lexical (current) | 426 | - | - |
  | Embedding similarity alone | 320 | 13 | 119 |
  | Reciprocal-rank fusion, k=60, untuned | 400 | 19 | 45 |

  Fusion fixes the intended cases (15 of its 19 gains are targets the request
  never names) but breaks 45 current hits, 20 of them named verbatim in the
  request: a general sentence model dilutes exact identifier evidence. Making
  it net-positive would require fitting a fusion weight or confidence gate on
  these burned suites, so it was not pursued. Top-2 placement is a proxy, not
  a full pack evaluation. Any future semantic approach (a lexical-confidence
  gate designed in advance, or a code-specific embedding model) should be
  judged on a fresh frozen holdout.
- This repository-local benchmark is a diagnostic signal, not the main
  generalization claim and not the frozen release floor. The external holdout
  program below is the stronger retrieval-regression evidence.
- Package metadata for this release is **ai-coding-context-optimizer 1.10.0**; the import
  remains `acco` and the CLI remains `acco`.

## Ranking observability and regression validation

Version 1.5.0 adds evidence around *why* ranking changes:

- normal ranking keeps score tracing disabled, preserving the default execution
  path;
- `ranking-explain` verifies trace endpoints against final scores;
- registered post-score stages are traced automatically;
- snapshots retain expected files even when they fall below the ordinary
  display top-N;
- `ranking-diff` refuses incompatible frozen ground truth;
- PR CI captures the baseline with base-commit code against the immutable base
  checkout and the candidate with candidate code;
- both PR snapshots use the base manifest so a PR cannot redefine its own
  comparison ground truth;
- ranking history de-duplicates workflow reruns and selects the newest artifact
  per PR by explicit `(created_at, artifact_id)` comparison;
- historical gate calibration separates frozen ground-truth cohorts and remains
  descriptive until the configured independent-PR evidence floor is reached.

These checks make ranking regressions explainable and reproducible. They do not
turn the current historical sample into a hard merge threshold prematurely.

## Integration lifecycle validation

The setup lifecycle is tested for:

- auto-detection and explicit Claude Code / Cursor / Codex selection;
- idempotent repeated setup;
- preservation of unrelated MCP servers, hooks, and TOML;
- refusal to overwrite malformed JSON or unmanaged conflicting Codex sections;
- preflight of all selected hosts before the first multi-host mutation;
- safe uninstall of only ACCO-owned entries;
- preservation of a user-modified generated Claude skill;
- project `.acco.toml` discovery and environment-variable precedence;
- repository-relative guard allowlist globs;
- Python 3.10 TOML support through the conditional `tomli` dependency;
- top-level dispatcher, doctor, command-discovery, and shell-completion
  behavior.

`doctor` validates configuration/index health; `host-check` remains the
stronger transport/live-host diagnostic. Configuration health alone is not
claimed as proof that an external host accepted model-visible replacement
output.

## Output optimization validation

The failure-aware output subsystem introduced in 1.4 remains a separate
validation surface alongside source retrieval:

- failure-aware routing is tested so success-oriented processors do not
  automatically compress failed commands;
- complex JavaScript test failures with stack frames and multiline diffs are
  preserved verbatim when the processor cannot safely reduce them;
- the shared critical-line recovery path is exercised independently of any
  one processor;
- output replay contracts test exact diagnostic preservation, token budgets,
  minimum reductions, and nonzero exit status on contract failure;
- graph-aware Delta tests diagnostic identity, unchanged compression,
  changed-diagnostic source/symbol mapping, related repository edges, and
  RESOLVED diagnostics after a clean rerun;
- the historical large-Read and Bash `cat` guard regressions remain in the
  suite.

These tests establish mechanics and preservation behavior for covered fixtures.
They are not a universal lossless guarantee for arbitrary command output.

The checked-in `benchmarks/output-quality.example.json` demonstrates the
portable quality-contract format. See `OUTPUT_OPTIMIZATION.md` for the
processor and Delta contracts.

The CLI-compression parity work adds a separate frozen ratchet at
`benchmarks/cli-output-compression-ratchet-v1.frozen.json`. It contains one
representative canonical case for each of the 40 built-in processors and seals
the case definitions with SHA-256. Each case can lock the expected processor,
required evidence, forbidden fabricated evidence, and a minimum token-reduction
floor. CI replays the suite with `--require-frozen`, and the shell uses
`pipefail` so a failed quality contract cannot be hidden by report capture.

The current 40-case replay passes **40/40 cases**, with **74.52% weighted
estimated token reduction**, **100% required-evidence preservation**, **100%
processor-identity match**, and **100% no-hallucination rate**. These fixtures
model documented real-world CLI output shapes; they are not claimed to be
production-log captures, model-token billing measurements, or evidence of
end-to-end coding-task cost reduction.

### Frozen provenance-backed CLI corpus v1

A second output-compression validation layer uses raw output from **real CLI
executions**, captured before inspecting or tuning against those outputs. The
capture harness attempted 31 commands on a GitHub-hosted Ubuntu 24 runner and
successfully captured **30**; Terraform was the only skipped tool because its
executable was absent. Every raw capture is committed under
`benchmarks/cli-output-real-v1/`, with the exact tool version, command, exit
code, byte/line counts, and SHA-256 in the frozen manifest. The original Actions
artifact SHA-256 is also recorded.

The first same-input comparison pins `ppgranger/token-saver` at
`19d47b2cc19457c865f2414ad78f8efa80204b43`. Both engines receive the exact
same 30 raw outputs and are scored with the same ACCO token estimator and
critical-line survival predicate:

| Engine | weighted estimated token reduction | critical-line survival | changed cases |
| --- | ---: | ---: | ---: |
| elyeshkiri/ai-coding-context-optimizer | **23.72%** | **100.00%** | 8/30 |
| ppgranger/token-saver @ 19d47b2c | **23.95%** | **81.25%** | 21/30 |

The reduction difference is **6 estimated output tokens across the full
corpus** (2,016 versus 2,010). The largest peer reduction advantages occur on
Git log/status/diff and small Go outputs; the current project is substantially
smaller on the captured Cargo build/test, Docker build, and Ruff outputs.

This is stronger evidence than representative synthetic fixtures, but its scope
is still bounded. These are controlled CI executions rather than production
user logs; several available-tool cases are version/configuration outputs rather
than large workloads; and critical-line survival is a mechanical diagnostic
predicate, not a semantic proof that every useful detail survived. Corpus v1 is
kept immutable. Any tuning informed by its case-level results must treat v1 as
burned development evidence and validate the change on a fresh corpus version.

Corpus v1 was subsequently used exactly that way: Git log/status/diff and Go
compression were tuned from its case-level deltas. On the **burned development
corpus**, the candidate moved from **23.72% to 28.91%** weighted estimated token
reduction while retaining **100%** critical-line survival; the pinned peer
remained at **23.95% / 81.25%**. These post-tuning v1 numbers are development
evidence only and are not used as the proof claim.

### Fresh provenance-backed CLI corpus v2

Corpus v2 was constructed with a different Git history/worktree shape and
different Go failure modes, plus unrelated control commands. Processor behavior
was locked at commit
`bb246458069527e5555bfb9c9625f2750fe53936` before capture. The capture-only
workflow then executed **27/27 real commands with 0 skips**, producing 9,025 raw
bytes. No compressor comparison was run before the exact Actions artifact was
frozen into Git at `benchmarks/cli-output-real-v2/corpus.zip`.

The frozen proof records source workflow run `35581545244`, source artifact
`10629774546`, artifact SHA-256
`6fc01f573b80a6f4768118d27fe38dedddab1543a2d499ee477e286e36051253`,
and capture-definition SHA-256
`ea2461863c384c4c0b56437882a961a817632e6d2af99e81c83b157d220b404b`.
Only after that freeze was committed was the same pinned ppgranger revision
enabled in the comparator.

On this untouched v2 proof set:

| Engine | weighted estimated token reduction | critical-line survival | estimated output tokens |
| --- | ---: | ---: | ---: |
| elyeshkiri/ai-coding-context-optimizer | **30.80%** | **100.00%** | **1,777** |
| ppgranger/token-saver @ 19d47b2c | **28.23%** | **76.92%** | 1,843 |

That is a **2.57 percentage-point overall reduction advantage** and 66 fewer
estimated output tokens for the candidate on the same 27 raw outputs, while all
mechanically detected critical lines survive.

The tuned subfamilies are not uniformly ahead, so the result is reported
without hiding the remaining gap:

| Fresh v2 subset | elyeshkiri reduction | ppgranger reduction | elyeshkiri critical survival | ppgranger critical survival |
| --- | ---: | ---: | ---: | ---: |
| Git diff | **31.84%** | 28.86% | 100% | 100% |
| Go build/test | **36.67%** | 24.29% | **100%** | 75% |
| Git status | 49.71% | **54.91%** | 100% | 100% |
| Git log | 62.62% | **79.05%** | 100% | 100% |
| Git status/diff + Go, excluding Git log | **38.87%** | 34.93% | **100%** | 75% |
| All targeted Git status/diff/log + Go | 48.80% | **53.39%** | **100%** | 75% |

The fresh corpus therefore validates a real overall gain and specifically
validates the Git-diff and Go improvements, but it also shows that Git log
compression remains materially more aggressive in the pinned peer and Git
status retains a smaller residual gap. No processor tuning was performed after
observing v2. Any future work on those remaining gaps must treat v2 as burned
and prove changes on a fresh v3 corpus.

### Fresh provenance-backed CLI corpus v3

Corpus v3 targets the remaining Git log/status gap using a new nine-commit Git
history, mixed staged/unstaged/untracked worktree state, porcelain v1/v2 status,
verbose/stat/reverse/fuller/oneline/graph log variants, and unrelated control
commands. Git log/status behavior was locked at commit
`18ebda5d623fc01ef2ea5cdf79054ecee7ba76e6` before capture.

The capture-only workflow executed **29/29 real commands with 0 skips** and
produced 14,068 raw bytes. The source workflow is `35584642288`, source
artifact `10630834204`, source artifact SHA-256
`f5345e19b1b77ccf41257c7393242c14b6e5dc88d7cc72f0833e0f032241742b`,
and capture-definition SHA-256
`0866719efa899c3d1d81fc2aa70eabe116ceb4401148ced000d854571581baae`.

The first archive-backed comparison attempt was rejected before evaluation
because the committed ZIP digest did not match the source artifact. No result
was produced from that attempt. The corpus was then stored as the independently
verified raw capture files with their original per-file SHA-256s; CI verifies
all raw hashes and the frozen definition before invoking either compressor.

On this untouched v3 proof set:

| Engine | weighted estimated token reduction | critical-line survival |
| --- | ---: | ---: |
| elyeshkiri/ai-coding-context-optimizer | 50.50% | **100.00%** |
| ppgranger/token-saver @ 19d47b2c | **51.25%** | 80.00% |

The overall compression difference is only **0.75 percentage points** on the
same 29 raw outputs, while the candidate preserves every mechanically detected
critical line.

The target families show that the original gap is now close to parity:

| Fresh v3 subset | elyeshkiri reduction | ppgranger reduction |
| --- | ---: | ---: |
| Git status (4 cases) | **62.90%** | 61.75% |
| Git log (6 cases) | 78.21% | **79.63%** |
| Git log + status (10 cases) | 75.28% | **76.20%** |

Compared with v2, Git status moved from a peer advantage to a **1.15-point
candidate advantage**, and the Git-log gap contracted from **16.43 points**
(62.62% versus 79.05%) to **1.42 points**. Combined Git log/status is now within
**0.92 percentage points** of the pinned peer on fresh evidence.

The per-shape results remain intentionally visible. The candidate is ahead on
the fresh long-status and porcelain-v2 cases and on `--format=fuller --stat`,
while the pinned peer remains more aggressive on several standard
`git log --stat` variants. Already compact one-line and graph log outputs are
left unchanged by both implementations in this corpus.

No processor tuning was performed after observing v3. Corpus v3 is now burned
proof evidence; any further Git-log compression work requires a fresh v4 corpus.

The previously recorded broad 24-task SWE-bench run remains
**non-publishable evidence** (historical only): it exposed harness/grader issues rather
than a trustworthy product-effect estimate. Version 1.6.0 repairs the
experiment, telemetry, blind-grading, cache-pricing, and publication-gate path
and wires the same frozen **24 tasks × 3 trials** into a paid/manual workflow.
That workflow has not yet been executed for this release candidate.
**No 144-run aggregate savings claim is made for 1.7.0** until the frozen
workflow actually completes and its strict publication gate passes.

## Frozen external holdout program

ACCO now maintains twelve frozen external holdout suites. Ground truth is
written before evaluation, normalized into a path-independent payload, sealed
with SHA-256, and enforced with `--require-holdout`. Once a suite is evaluated,
it is considered burned for tuning.

### Query difficulty and comparability

The frozen suites do **not** all measure the same query difficulty.

The original 6-task external holdout uses natural-language behavior descriptions
without embedding the target symbol/type identity. By contrast, later suites
including #11 and #12 contain many **identifier-bearing queries** whose wording
names the target class/type and member (for example, asking for a named method
on a named type). Their strong exact-identity numbers therefore validate
navigation, scoping, overload resolution, and identity recovery under
identifier-bearing tasks; they must not be read as evidence that semantic
natural-language retrieval improved monotonically from the early suites to
100%.

This distinction is now part of the benchmark protocol. Future headline
semantic holdouts must follow the no-identifier-leakage query-construction rule
in [BENCHMARKING.md](BENCHMARKING.md#query-construction-protocol), and should
publish a trivial lexical baseline on the same frozen tasks. Identifier-bearing
tasks remain valid when that vocabulary genuinely appears in the upstream user
task, but are reported as a separate query class.

### Holdout #12 — latest fresh external evidence

Holdout #12 follows the pre-declared design from the #11 review: **72
source-grounded tasks across 12 repositories never used in holdouts #1-#11**,
with **6 tasks per repository across 6 languages** (Python, Go, Rust, Java,
TypeScript, and C#).

Repositories: itsdangerous, encode/httpcore, gorilla/websocket, zerolog, uuid,
crossbeam, Apache Commons Text, Apache Commons Codec, Zustand, React Hook Form,
Humanizer, and Newtonsoft.Json.

Frozen ground-truth SHA-256:

`625de623c409f6e77ac695612533f722330db3fd329dfc4b0eb82a0bb6994f54`

Ground truth freeze commit: `6cd5fc8bb5efe16e43e2e5e9625cc12420165135`.
First and only canonical fresh evaluation: GitHub Actions run **35442135225**
from launch commit `20d109d37ea467fe03767cb491b1fe892371d74d`.

| Metric | Fresh first run |
| --- | ---: |
| File recall | **100.00% (72/72)** |
| Bare symbol recall | **100.00% (72/72)** |
| Symbol recall in expected files | **100.00% (72/72)** |
| Qualified-symbol recall | **100.00% (72/72)** |
| Exact symbol-identity recall | **100.00% (72/72)** |
| Mean estimated context reduction | **94.30%** |

All 12 repositories are perfect through exact identity. This is the first fresh
suite in the program to reach 100% at every retrieval/identity level while also
meeting the larger 72-task / 12-repository design.

The context-reduction result must be reported just as literally: **94.30%** is
below the `>=97%` efficiency target proposed after holdout #11. The main reason
is corpus size sensitivity under a fixed 6,000-token budget: the smallest
repository in this suite, itsdangerous, averages only **65.65%** reduction,
while several large repositories exceed 99%. No repository or task is excluded
or reweighted to improve the aggregate.

The exact untouched first-run artifact is checked in as
`benchmarks/holdout-external-12.result.json`. Holdout #12 is now burned for
tuning; later reruns can be regression evidence only.

Two earlier attempts are retained explicitly as rejected audit evidence and are
not counted as canonical holdout #12:

- run **35441174123** reused repositories already present in holdouts #1-#11;
  its manifest/result remain under
  `benchmarks/holdout-external-12-candidate-rejected*.json`;
- run **35441476809** used genuinely unseen repositories but only **25 tasks
  across 5 repositories / 5 languages**, so it did not satisfy the already
  documented 72-task / 12-repository / 6-language design. Its manifest/result
  remain under `benchmarks/holdout-external-12-pilot-rejected*.json`.

Neither rejected attempt was used to tune ranking before the canonical #12
first run.

### Holdout #11 — previous fresh external evidence

Holdout #11 contains **60 source-grounded tasks across 10 repositories never
used in holdouts #1-#10**, spanning C#, Java, TypeScript, Rust, Go, and Python.

Frozen ground-truth SHA-256:

`011dffedad4fe5ea99400cc58655850dcf43f38b3664b9219b4f5cf92a7f94ec`

First and only fresh evaluation: GitHub Actions run **35395304893**.

| Metric | Fresh first run |
| --- | ---: |
| File recall | **96.67%** |
| Bare symbol recall | **96.67%** |
| Symbol recall in expected files | **93.33%** |
| Qualified-symbol recall | **91.67%** |
| Exact symbol-identity recall | **88.33%** |
| Mean estimated context reduction | **99.71%** |

Six repositories were perfect through exact identity: .NET Runtime, EF Core,
Spring Framework, tracing, gRPC-Go, and SQLAlchemy. The fresh C# results are
especially important because .NET Runtime and EF Core independently validate
the C# 14 extension-block recovery introduced after holdout #10.

The seven non-perfect tasks were concentrated in four general classes: dense
Java overload identity, TypeScript interface/generic-member identity, a
same-name TypeScript function in the wrong file, and a Go receiver/member query
overwhelmed by common call-site noise.

After those classes were fixed generically, frozen #11 was rerun **once** as a
burned development diagnostic (run **35399929752**). That diagnostic reached
**100% file, bare, scoped, qualified, and exact identity recall across all
60 tasks**, with **99.71% mean context reduction** and zero misses. This is
regression confirmation only; it does **not** replace the fresh 88.33% exact
first-run result above.

The exact untouched first-run artifact is checked in as
`benchmarks/holdout-external-11.result.json`.

## Historical first external holdout (1.2-era)

A 6-task suite against independently-authored public repositories at
pinned revisions -- [encode/httpx](https://github.com/encode/httpx)
`b5addb6` and [colinhacks/zod](https://github.com/colinhacks/zod)
`59bbc03` -- with ground truth (target files/symbols for a
natural-language query) written from reading the actual source before
ever running the tool, frozen via `--print-ground-truth-hash`, and
evaluated with `--require-holdout` (`benchmarks/holdout-external.json` /
`.result.json`).

- **First run (1.1.0 validation cycle): 83.3% mean file recall, 16.7%
  mean symbol recall**, ~98.5% mean estimated token reduction -- the
  honest, frozen number, not a cherry-picked one, and materially worse on
  symbol recall than this repository's own self-benchmark, exactly the
  generalization gap freezing ground truth in advance exists to catch.
  Two disclosed root causes: per-file symbol sub-ranking could prefer a
  densely-worded helper method over the semantically-correct class/
  function the query was about, and file-level BM25 ranking could prefer
  a prose-rich file discussing a topic over a terser file that is
  actually the correct answer.
- **Current result: 83.3% mean file recall, 83.3% mean symbol
  recall**, ~98.5% mean token reduction unchanged. `httpx-digest-auth`,
  `httpx-redirects`, `httpx-multipart`, `zod-error-tree`, and
  `zod-flatten-error` are all now at 1.0/1.0 symbol recall. Each fix
  along the way was designed and validated against this repository's own
  25-task self-benchmark first (never iterated against this frozen
  suite), then measured against it once, after the fact, purely as an
  observation of generalization -- consistent with this project's
  standing rule against tuning against the same suite that found a gap.
  That process surfaced two of its own regressions along the way (a
  parent-credit symbol-window fix that briefly broke `httpx-redirects`,
  and a file-ranking dampening attempt that broke it again while fixing
  `zod-email-regex`); both are disclosed in full, with root cause and
  resolution, in CHANGELOG.md.
- **Correction (bisected after 1.3.0):** the per-task attribution above is
  stale, and `benchmarks/holdout-external.result.json` (6/6 at 1.0/1.0) no
  longer reproduces. That artifact was accurate when written -- the suite
  scored 6/6 at `3462828` -- but regressed twice afterwards, undetected,
  because this suite ran in no CI job:
  - `6f47fd2` "stop containers from double-counting descendant relevance"
    broke `zod-error-tree` symbol recall (1.000 -> 0.667; partially
    recovered to 0.833 at `3361bdb`, and `zod-error-tree` has failed ever
    since);
  - `7acb0d8` "align structural leaf gates with query tokenization" broke
    `zod-email-regex` file recall (1.000 -> 0.833).

  Current main therefore measures 83.3% file recall, 83.3% bare-symbol
  recall, and 66.7% symbol recall in expected files. The scoped metric is
  lower because `zod-email-regex` can still find a same-named symbol outside
  `regexes.ts`, while `zod-error-tree` misses its expected symbol. The
  aggregate 83.3% bare figures matching the 1.2.0 result are therefore a
  coincidence of offsetting changes.

  `.github/workflows/ci.yml` now runs this suite on every pull request and
  again on every push to `main` via `scripts/check_holdout.py`, enforcing
  file, bare-symbol, and expected-file-scoped symbol floors recorded in
  `benchmarks/holdout-external.floor.json`. The floor update command is
  monotonic and refuses to lower any existing threshold. Neither regression has been
  "fixed" by adjusting ranking: this is a burned holdout, and tuning
  against it to move the number is exactly what the protocol forbids. The
  floor is set at the current value and should be ratcheted upward only
  when a root-cause fix, validated on the self-benchmark first, raises it.
- **Remaining known gap: `zod-email-regex` (0.0 file recall).** Root
  cause identified precisely: `rank_files()`'s outline-term bonus is
  presence-only, not normalized by outline size, so a large file with a
  sprawling outline (`schemas.ts`) picks up more distinct query-term hits
  than a small, precisely on-topic file (`regexes.ts`) purely from having
  more surface area -- even though raw BM25 alone already correctly
  favors the smaller file. A fix (dampening the bonus by outline size)
  was tried and reverted after it broke a different, previously-fixed
  task (`httpx-redirects`, itself a large file that is genuinely the
  correct answer) -- a flat per-file size penalty can't distinguish
  "large and diffusely matching" from "large and genuinely on-topic."
  PR #4 (`fix/authoritative-file-ranking`, see below) targeted this same
  gap via a different mechanism and does not resolve it either:
  `regexes.ts` has no direct incoming `semantic-ref` edge from a file
  that independently outranks `schemas.ts`. Deliberately left unfixed
  pending a *new*, separately-frozen holdout suite to validate a future
  fix against -- re-running a change against the same frozen tasks that
  found the weakness would not demonstrate generalization.

## Merged without their own release (PR #1-#4)

PR #1 (`feat/index-backed-retrieval`), PR #2 (`feat/semantic-retrieval-v2`),
PR #3 (`fix/graph-aware-symbol-ranking`), and PR #4
(`fix/authoritative-file-ranking`) all merged directly to `main` between
1.1.0 and this release, without their own version bump or CHANGELOG entry;
summarized here rather than individually re-documented (see each PR's
description and CHANGELOG.md's entries for full detail):

- PR #1/#2: index-backed retrieval performance, stronger JS/TS module
  semantics, adaptive retrieval budgeting, provider-aware exact token
  counting, multi-repository/frozen-holdout evaluation infrastructure, a
  TypeScript-compiler semantic overlay, and `acco host-check`.
- PR #3: caller-graph-aware symbol ranking and exact incoming
  semantic-reference evidence in `_symbol_windows()`.
- PR #4: a strong, deliberately non-transitive one-hop ranking weight for
  exact `semantic-ref` edges. Merged with its own CI check failing on
  every push (only a separate, narrower frozen-holdout workflow was
  green); the underlying gap (`dependency_closure`'s seed set is too
  small to discover a relevant-but-low-raw-score provider) was diagnosed
  and fixed as part of this release -- see CHANGELOG.md.

## Other validation carried over from 1.1.0

- Differential testing verified the `RepositoryIndex` reverse-index
  caching (`symbol_callers`/`neighbors`/test-file signatures) produces
  byte-for-byte identical output to the pre-caching per-call scan it
  replaced, checked across 625 real files and 10 symbols in a separate
  application's repository (not included here).
- Real-world validation: a real 129-file diff from a separate production
  application (private, not included in this repository) was reviewed by
  an isolated model instance with no access to that repository, at a fixed
  4,000-token `pack-diff` budget, against a full-repository-access baseline
  (100,416 tokens, 42 tool calls) and an independently-built 15-item
  ground-truth list. Result: roughly 12-13/15 ground-truth items
  recovered, including two findings the baseline missed, at effectively
  flat token cost (37,306 -> 37,036 tokens). Single diff, not a
  statistically validated benchmark; see
  `tests/test_evidence.py::test_mixed_diff_represents_every_evidence_category_within_budget`
  for the checked-in regression fixture that guards this result without
  depending on the private repository.
- Live host validation executed against a real, separate Claude Code host
  process (version 2.1.274), not a simulated payload: a headless
  `claude -p` session with ACCO's hooks installed produced a
  captured debug log showing the host receiving
  `hookSpecificOutput.updatedToolOutput` and logging `Hook PostToolUse
  (acco hook) replaced tool output`. `acco host-check
  --live-evidence <captured-log> --require-live` exits 0 with
  `live_verified: true`.
- Paired coding-agent trials against real bug-fix tasks in
  [encode/httpx](https://github.com/encode/httpx), full-context baseline
  vs. ACCO's hooks, outcomes independently verified by running the
  target tests directly. Both conditions produced the byte-for-byte
  identical correct fix in both trials. No reliable cost effect was
  demonstrated either way: ACCO's filtering/guard mechanism never
  actually activated in either trial (both file reads and command output
  stayed under its size thresholds). See CHANGELOG.md.
- Regression coverage exercises bounded dependency closure,
  Tree-sitter-backed JS/TS/JSX/TSX symbol ranges, patch-aware context
  generation, public-signature/removed-symbol/missing-test detection, the
  persistent MCP index service, paired agent-outcome evaluation,
  incremental index reuse, near-duplicate suppression, task-session
  continuity, hard context-pack token caps, exact line-numbered source
  windows, sensitive-path rejection, symlink containment, secret
  redaction, structured Bash output, subprocess hook transport, and
  model/TTL pricing.

## Not executed

- Windows execution of the locking branch.
- A production benchmark proving that task-aware packs reduce total task
  cost for a representative workload; the pack tests prove ranking/budget
  invariants, not end-to-end model quality.
- A fresh, never-seen frozen holdout suite to validate a `zod-email-regex`
  fix against (the original suite is now burned for that specific gap,
  having been used to diagnose and disprove two fix attempts).

No real-world token savings percentage is claimed beyond the private-diff
review and the external holdout benchmark described above, both explicitly
hedged (single diff; six tasks across two repositories), and the paired
coding-agent trials explicitly demonstrated no reliable cost effect either
way rather than a savings claim. Synthetic and unit tests exercise
mechanics and validation, not general product efficacy. See BENCHMARKING.md
for live integration and paired-task measurement procedures.
