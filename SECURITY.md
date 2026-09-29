# Security and privacy

ACCO is designed as a local context-optimization layer. This document
describes what it reads, writes, and deliberately refuses to overwrite.

## Local processing

Core repository indexing, ranking, context packing, hook filtering, output
recovery, and transcript analysis run locally.

Optional external/model integrations can have their own network behavior; use
their documentation and credentials deliberately.

## Native coding-agent hooks

`acco setup` can install project-level command hooks for Claude Code, Codex, Cursor,
Gemini CLI, Qwen Code, and Copilot CLI. Those hooks execute the local `acco`
binary with the current user's privileges and receive the host's documented
event payload over stdin.

ACCO treats native hooks as a local optimization boundary:

- hook input is processed transiently by the same host-neutral `HookRuntime`
  used by Claude Code;
- diagnostics go to stderr; adapters keep stdout reserved for the host's strict
  JSON response contract;
- ACCO does not add hook-payload logging as part of these adapters;
- large original outputs that are safely replaced may enter ACCO's existing
  private exact-recovery/output stores under their normal retention rules;
- Codex/Cursor/Gemini/Qwen shared JSON is mutated only for ACCO-owned command
  entries; Copilot uses a dedicated `.github/hooks/acco.json` and refuses to
  replace a non-ACCO document at that path;
- Codex project hooks remain subject to Codex's own trust/enablement boundary.
  ACCO does not mark its hook definition trusted on the user's behalf and does
  not treat setup completion as proof that Codex will execute the hooks.

Project hook configuration is executable configuration. Review hooks from
untrusted repositories before opening/running their coding agent, and use each
host's repository-trust controls where available. ACCO's ownership checks prevent
it from silently taking over unrelated hook entries; they do not make arbitrary
third-party hooks safe.

Real CLI hook traffic may use ACCO's warm native runtime. That helper binds only
to a random 127.0.0.1 port, publishes an owner-only per-project manifest under
`ACCO_STATE_DIR/native-runtime`, and requires a high-entropy token on every
event request. The transport is bounded to 32 MiB and emits no hook payload or
access log. The server verifies that an event's project root matches the runtime
that received it. Stale endpoint manifests are discarded on connection/schema
failure. The runtime is an optimization layer only: startup/transport failure
falls back to the direct hook path. Timeout handling deliberately does not replay
the same event because local state may already have been updated.

## Searchable session ledger

ACCO can persist a private project-scoped SQLite event ledger under
`ACCO_STATE_DIR/session-ledger`. It is designed to preserve useful working
history without becoming another transcript store.

The ledger stores bounded structured summaries such as:

- session lifecycle and compaction checkpoints;
- file paths/actions;
- redacted shell command labels and validation status;
- failure digests/status;
- narrowly extracted explicit user decision/preference sentences.

It does **not** store full prompt text or raw tool output. Decision snippets are
credential-redacted and length-bounded, but they can still contain ordinary
project/user text. Treat the ledger as sensitive local agent state. The database
uses private permissions where supported and sits inside a private state
directory; it is not encrypted at rest.

FTS5 is used only as a local index over the stored bounded summary/subject/path
fields. Minimal SQLite builds fall back to bounded LIKE search. The ledger is
capped to the newest 20,000 events per project.

## Out-of-context programmable execution

The MCP/SDK `execute`, `execute_file`, and `batch_execute` surfaces are
designed for local aggregation/filtering over large repository text without
first placing the source bytes in model context. `execute_file` loads the
restricted program from inside the repository; `batch_execute` preflights up
to eight jobs, caps aggregate input at 64 MiB, and retains the same per-job
restricted interpreter.

The execution engine:

- accepts only explicit files that resolve inside the configured repository root;
- rejects binary inputs and caps each invocation at 128 files / 32 MiB total;
- parses the submitted Python before execution and rejects imports, class/async
  constructs, dynamic evaluation/introspection helpers, arbitrary `open`,
  private/dunder names and attributes, and repository path escapes;
- runs the accepted program in a separate isolated-startup Python process with a
  minimal environment and a 1–30 second wall-clock limit;
- exposes only a small builtin/data-analysis surface and requires one
  JSON-serializable `result`;
- caps the model-visible result; oversized exact JSON is stored in the same
  project-scoped recovery store and returned by handle.

These controls reduce accidental capability and contain ordinary agent-generated
analysis programs. They are **not a hardened security sandbox** for deliberately
hostile Python. ACCO does not claim kernel/container isolation, seccomp,
namespaces, VM isolation, or a proof that every Python object-model escape is
impossible. Do not expose the local MCP/SDK bridge to untrusted users and do not
execute code supplied by an untrusted remote party merely because the restricted
surface rejected common escape primitives.

The child process receives the selected file contents through its stdin payload;
it does not need direct filesystem APIs. Oversized computed results follow the
normal exact-recovery boundary. The original selected source files are not copied
into the recovery store merely because they were analyzed.

## Repository contents

ACCO may read source files to build structural/retrieval indexes and
bounded context.

Context rendering applies the project's existing secret-redaction path where
documented, but users should still avoid committing credentials or treating an
AI-agent context layer as a secret-management system.

## Exact recovery store

Lossy optimization surfaces can store exact original bytes in a private
project-scoped SQLite recovery database under `ACCO_STATE_DIR`.
Byte recovery handles begin with `tsr_` and are derived from SHA-256 content
identity. Recovery Store v2 also supports canonical-JSON `tsr_obj_` records for
selective RFC 6901 subtree recovery. Retrieval verifies the full stored digest
before returning either record type. Typed records can reference existing
recovery handles through dependency edges; dangling dependencies are refused at
write time.

Recovery handles are identifiers, **not authorization tokens**. Anyone who can
access the local ACCO state directory may be able to recover project
content. The database is not encrypted at rest; protect the state directory with
the same care as agent transcripts. ACCO uses private file permissions
where the platform supports them.

The store has a 512 MiB per-project default hard capacity and does not evict
older exact source merely to make room for a new transform. If an original
cannot be stored, that lossy transform is refused and the unmodified
representation is retained. This prevents model-visible recovery handles from
becoming intentionally dangling.

Recovery databases created by older ACCO releases are migrated in place when
opened by Recovery Store v2; existing byte handles remain valid. There is still
no per-record recovery-prune command. Deleting the project recovery database
manually invalidates every handle it contains, so do that only when no active
session or saved evidence depends on those handles.

## Provider reverse-proxy boundary

`acco provider-proxy` is explicit and opt-in. It can observe provider
request bodies and authorization headers because it sits between the selected
agent/client and the configured provider origin. ACCO does not enable or
install this proxy automatically.

The proxy:

- binds to a loopback IP by default; non-loopback listening requires an explicit
  override and external access control remains the operator's responsibility;
- requires HTTPS for non-local upstreams and refuses credentials embedded in the
  upstream URL;
- strips the incoming Host header and hop-by-hop transport headers;
- joins only the incoming path/query onto the configured upstream origin, so an
  absolute-form request target cannot select another destination;
- disables automatic upstream redirect following, preventing provider
  authorization headers from being silently replayed to a redirect origin;
- transforms only supported JSON request bodies within a bounded size;
- limits provider-boundary request reduction to tool schemas and explicit
  historical tool/function-result surfaces; current user text and fresh source
  context are not provider-boundary compression targets;
- forwards provider response bytes without semantic rewriting, including
  streaming responses;
- optionally observes provider-reported token/model usage while forwarding and
  stores only content-free counters/labels in the local efficiency ledger.

Prefix telemetry stores only canonical SHA-256 fingerprints, component labels,
estimated sizes, and hit/miss counters. Provider usage telemetry stores provider,
request shape, streaming flag, bounded model id, and token/cache counters. It
does not copy provider request or response text. Disable provider usage
observation with `--no-usage-telemetry`.

Provider-cache planning stores content-free economics metadata separately from
provider-observed counters. Conversation epochs are keyed by hashes of stable
system/tool surfaces so concurrent agents do not share one mutable provider
prefix record. Apply mode mutates only supported cache-control fields: currently
a conservative Anthropic/Bedrock breakpoint when the request already has a safe
block/tool surface. ACCO does not fabricate OpenAI cache hits or create Gemini
cached-content resources on the caller's behalf.
Browser-context optimization consumes only caller-supplied textual payloads:
HTML, accessibility/ARIA snapshots, or structured browser JSON. It does not
fetch arbitrary web URLs, execute page JavaScript, control a browser, or inspect
screenshot/image pixels. Accepted lossy transforms store the exact original
locally under the same recovery contract; recovery-capacity failure preserves
the original payload. Hidden/script/style HTML content is excluded from the
focused representation but remains available through exact recovery.

## Oversized-prompt ingress state

Prompt ingress optimization is **disabled by default** because its safety model
requires storing the exact blocked prompt locally so omitted ranges remain
recoverable. When enabled and the threshold fires, ACCO writes:

- the exact original prompt;
- a SHA-256 integrity digest;
- a bounded exact-excerpt packet and line-range metadata.

State is project-scoped under the private ACCO state directory, written
with private permissions, and bounded to the newest 40 staged prompts. It is not
uploaded to ACCO infrastructure. Unlike output-policy telemetry and
session continuity, this store intentionally contains user prompt content.
Treat it as sensitive, relocate `ACCO_STATE_DIR` when appropriate, and
do not enable ingress staging for material that must not be persisted locally.

The hook blocks the oversized prompt before Claude processes it. ACCO
does not send a lossy substitute automatically and never silently truncates a
failed compression attempt.

## Smart Tool Proxy model boundary

Smart Tool Proxy is disabled by default. When enabled with the default
`provider = "ollama"`, ACCO sends a bounded task hint, structural
outline, and bounded exact candidate source windows to the configured Ollama
HTTP endpoint. The default endpoint is loopback
`http://127.0.0.1:11434`.

Changing that endpoint to a remote host changes the privacy boundary: the
bounded task/source evidence is then sent to that host. Configure remote
endpoints only when that provider is approved to receive the repository
material.

The selector is not trusted as source truth. Returned JSON can only nominate
line ranges; ACCO validates/clamps those ranges and re-reads the delivered
code from the original file. Model-generated orientation is labeled
non-authoritative. If the selector fails, deterministic local range selection is
used. Bounded Reads are never proxied.

The latest user task may be read transiently from the local Claude transcript
tail to orient selection. ACCO does not persist that prompt text in Smart
Tool Proxy state. Operational savings telemetry stores only token counts and the
selector label, not the source excerpts or task text.

## Semantic vector state

Opt-in semantic retrieval reads the same repository files already admitted by
the structural index's path-safety policy. Its private project-scoped SQLite
database stores:

- repository-relative file paths and indexed content digests;
- chunk start/end lines and optional symbol labels;
- normalized embedding vectors;
- hashes and vectors for exact repeated queries;
- optional HNSW label mappings.

It deliberately does **not** persist source text inside the vector database.
The optional HNSW sidecar contains derived vector-index data only. Both live
under `ACCO_STATE_DIR`; treat that directory as private because vectors
and filenames are still derived from project contents.

ACCO loads the configured SentenceTransformer with
`local_files_only=True`. Model downloading is an explicit user action outside
normal retrieval. The current feature does not send source chunks or query text
to ACCO infrastructure.

A changed file is re-hashed before embedding and must still match the structural
repository-index digest. A mismatch fails the semantic refresh rather than
storing vectors under stale evidence identity.

When `ACCO_SEMANTIC_MODEL_REVISION` is set, that immutable revision is
part of the local vector-store and query-vector cache identity. This prevents a
pinned evaluation or deployment from silently reusing embeddings produced by
different weights under the same model name.

## Retrieval cache state

Persistent retrieval cache entries contain completed bounded context packs and
ranking metadata, so they may include source excerpts that were selected for an
agent. Cache identity incorporates indexed source digests and index version;
changed repository evidence gets a new key rather than reusing stale context.
The cache is local/private and bounded by `retrieval.cache_max_entries`.
Disable it with `ACCO_RETRIEVAL_CACHE=0` when local persistence is not
appropriate.

## Claude transcripts

`acco sessions` reads Claude Code transcript files under the local
Claude projects directory.

It does not need to upload those transcripts to ACCO infrastructure.
The analysis is local.

## Saved command output

When the Claude hook safely replaces a large command result, the original is
stored locally for recovery. The legacy paged-output id remains supported and
v1.13 also emits a project-scoped `tsr_...` handle when universal recovery
storage succeeds.

Retrieve through either compatible path:

```bash
acco output <id>
acco recover tsr_... --path .
```

MCP clients can resolve the universal handle with `recover_context`.

Prune old outputs with:

```bash
acco outputs-prune --days 7
```

Treat the state/output directory as potentially sensitive because command output
can contain project paths, diagnostics, or application data.

## Blind grading data boundary

`blind-grade` is an explicit evaluation action, not background telemetry. It
sends the configured grader the frozen task prompt and the two agents' **final
response texts** under anonymized A/B labels. It does not send condition names,
repository patches, hidden verifier output, billing data, or full transcripts.
The bundled Claude grader runs in an empty pinned container with shell,
filesystem, and web tools denied.

For private/custom benchmark prompts, treat the configured grader as an external
processor of that prompt and final-response text. Do not enable a remote grader
for material you are not permitted to send to that provider.

## Frozen session-holdout evidence

The optional `session-holdout` workflow is an explicit paid evaluation action,
not normal runtime telemetry. It runs frozen public SWE-bench task prompts
through the configured Claude model and persists benchmark artifacts such as
transcripts, patches, verifier logs, blind-quality scores, usage counters, and
session-efficiency event counts.

The dedicated GitHub workflow uploads per-task evidence for 30 days and merged
aggregate evidence for 90 days. Repository/API credentials are supplied to
isolated runner containers through GitHub Actions secrets; they are not written
into the frozen suite.

The benchmark blind grader receives the frozen task prompt plus anonymized final
A/B response text under the existing blind-grading boundary. Session-efficiency
outcome metrics are derived from raw transcripts locally; ACCO's event
ledger is used only as feature-activation evidence.

Do not reuse the public frozen workflow for private task prompts or repositories
unless the configured model/grader provider and artifact-retention policy are
acceptable for that material.

## Session-efficiency state

The 1.7 continuity layer uses a separate private project-scoped snapshot and
bounded event ledger under the ACCO state directory.

The continuity snapshot may contain:

- an opaque session fingerprint;
- coarse task class;
- repository-relative/absolute working file paths;
- bounded command labels after best-effort credential redaction plus opaque
  command/output fingerprints;
- validation kind/status, failure fingerprints, and counters.

It deliberately does **not** persist raw user prompts, assistant responses, or
raw tool output. Exact output fingerprints are hashes, not copied output.
Compressed Bash originals remain in the existing saved-output store described
above because recoverability is a separate explicit feature.

The efficiency event ledger stores feature names, counts, opaque session
fingerprints, and estimated before/after token savings. It does not contain the
removed command output. Files are written with private permissions and bounded
retention.

Command-label redaction covers common `key=value`, `--token value`,
authorization-header, and URL-credential forms, but it is defense in depth
rather than a secret-management guarantee. Do not pass secrets on command lines
when avoidable, and treat the local state directory as potentially sensitive.

## Durable project-knowledge state

`remember` / `remember_finding` persist the exact claim, evidence,
applicability text, confidence label, file/symbol anchors, and source digests
that the caller explicitly submits. This state is local, project-scoped,
private-permission, and bounded, but unlike continuity state it **can contain
human/model-authored prose**. Do not place credentials, production secrets,
private customer data, or other material you would not store on the local
machine into a finding.

Automatic knowledge-assisted read avoidance never harvests conversation text.
It reads only explicit stored findings, requires current verified anchors, and
does not send knowledge to ACCO infrastructure. The frozen paid
knowledge-efficiency workflow has the same external model/grader and artifact
retention considerations as the session holdout below; do not reuse the public
workflow for private prompts/repositories unless those boundaries are acceptable.

## Session state

ACCO keeps bounded local state for features such as remembered reads,
diagnostic Delta, the active automatic output-policy signature, and bounded
output-budget telemetry. The output policy stores only resolved
task/mode/budget metadata; it does not persist user prompt text. Telemetry stores
policy metadata, opaque session fingerprints, model identifiers, and transcript
usage counters. It does **not** store prompt text, assistant text, tool payloads,
or copied transcript content. The telemetry JSONL file is project-scoped,
created with private permissions, and compacted after it grows beyond 4 MiB,
keeping the newest 2,000 records. The default state area is under the user's Claude directory;
`ACCO_STATE_DIR` can relocate it.

Do not point the state directory at a shared/public location.

## Managed configuration safety

`acco setup` preflights selected host files before mutation.

Ownership boundaries:

- Claude: only ACCO hook commands and `mcpServers.acco`;
- Cursor: only `mcpServers.acco`;
- Codex: only the marked ACCO managed block;
- generated Claude skill: removed only if it still matches the generated
  template exactly.

Invalid JSON and unmanaged conflicting Codex sections are refused rather than
overwritten.

## Credentials

ACCO should not require storing provider API keys in repository config.

Optional exact token counters, embeddings, model runners, or CI publication can
use provider-specific credentials. Keep those in normal secret stores or CI
secrets rather than `.acco.toml`.

## Benchmark privacy

Do not use proprietary repositories, private transcripts, or production secrets
in published benchmark artifacts unless you have explicit permission.

The repository's frozen public holdouts use pinned external repositories and
predeclared task definitions so evaluation evidence can be reproduced without
private source.

## Reporting a security issue

Do not publish an exploit or sensitive reproduction data in a public issue.

Use GitHub's private security-reporting mechanism for the repository when
available. If that mechanism is unavailable, contact the repository owner
privately and disclose only the minimum information needed to reproduce the
issue.

Include:

- affected ACCO version/commit;
- affected command/integration;
- impact;
- reproduction steps using non-sensitive fixtures where possible;
- proposed mitigation if known.
