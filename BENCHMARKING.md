# Verify integration, then benchmark successful work

## Deterministic context-quality benchmark

Before paid paired-agent trials, run the included 25-task ground-truth selector
benchmark. It measures relevant-file recall, relevant-symbol recall, and context
reduction; selection metrics alone do not prove agent success.

```bash
acco evaluate benchmarks/context-quality.json --path . --max-tokens 6000
```

Each item also reports `symbol_recall_in_expected_files`, which counts a
symbol only when it was selected from one of the task's expected files. Bare
`symbol_recall` can be satisfied by a same-named symbol in an unrelated file;
prefer the scoped figure (or `qualified_symbols` / `symbol_identities`) when
names are common.

Add project-specific tasks using `query`, `files`, and `symbols`. Keep the
manifest under version control so ranking changes can be compared reproducibly.

## Multi-repository holdout benchmark

### Query-construction protocol

A frozen hash prevents post-hoc edits to the **query text**, expected files, and
expected symbols. It does not make an easy query difficult. New holdouts must
therefore declare which retrieval behavior they are measuring before the first
ACCO run.

For a **semantic natural-language holdout**, construct each query from the
upstream issue, bug report, user request, or behavior description **before
looking up the answer identity**. The query must not contain:

- the target symbol/member name;
- the target's containing class/type/module name when that name directly
  identifies the answer;
- the target file basename/path;
- the exact qualified symbol identity used as ground truth;
- a distinctive implementation literal copied from the answer solely to make
  retrieval easier.

Example:

```text
acceptable:   "reject malformed email addresses before schema validation"
not semantic: "where is emailRegex in regexes.ts"
```

If the real user task already contains an identifier (for example, a compiler
error names `refreshSession`), keep it: removing genuine task evidence would
make the benchmark artificial. Classify that task/suite as **identifier-bearing**
rather than semantic-natural-language and report it separately.

Do not present identifier-bearing recall as a continuation of a
natural-language difficulty trend. The two answer different questions:

- semantic suites test whether ACCO can discover the identity from a
  behavior/problem description;
- identifier-bearing suites test exact navigation, overload resolution,
  scoping, and identity recovery once some answer vocabulary is already known.

For future headline semantic holdouts:

1. pre-register the query source/rule and freeze the exact query text;
2. keep target symbol, containing type, file path, and qualified identity out of
   the query unless they genuinely appeared in the upstream task;
3. record any unavoidable identifier-bearing tasks explicitly;
4. run a trivial lexical baseline (for example grep/ctags/exact identifier
   lookup where applicable) on the same frozen tasks;
5. report ACCO recall alongside that baseline rather than quoting only an
   absolute recall percentage;
6. never rewrite queries after seeing retrieval misses.

The query source/rule belongs in the same committed evidence package as the
manifest. The manifest's query strings themselves are part of the ground-truth
freeze hash, so changing the wording after freeze changes benchmark identity.

The repository-local selector benchmark is useful for regressions, but because
ACCO is developed against this codebase it is not independent evidence of
generalization. For unseen evaluation, define ground truth before running the
tool and point one manifest at repositories that were excluded from ranking
work/tuning. `benchmarks/holdout.example.json` contains the full schema.

Repository paths are resolved relative to the manifest. Pin exact Git commits so
the corpus cannot move between runs. A publishable holdout also records a freeze
timestamp and a SHA-256 of the task/repository ground-truth definition:

```json
{
  "suite_version": 1,
  "protocol": {
    "ground_truth_frozen": true,
    "development_excluded": true,
    "frozen_at": "2026-09-17T12:00:00Z",
    "ground_truth_sha256": "HASH_FROM_COMMAND_BELOW"
  },
  "repositories": {
    "app-a": {"path": "../app-a", "revision": "ACTUAL_COMMIT_SHA"},
    "app-b": {"path": "../app-b", "revision": "ACTUAL_COMMIT_SHA"}
  },
  "tasks": [
    {
      "id": "auth-refresh",
      "repository": "app-a",
      "query": "session refresh after logout",
      "files": ["src/auth/session.ts"],
      "symbols": ["refreshSession"]
    }
  ]
}
```

After the tasks, expected evidence, and revision pins are final, calculate the
freeze hash without running retrieval:

```bash
acco evaluate benchmarks/holdout.json --print-ground-truth-hash
```

Put that value in `protocol.ground_truth_sha256`, commit the manifest, then run:

```bash
acco evaluate benchmarks/holdout.json --require-holdout --max-tokens 6000
```

`--require-holdout` rejects a manifest unless both protocol flags are true,
`frozen_at` is present, the SHA-256 still matches the frozen task definition,
and every pinned repository `HEAD` matches its declared revision. Filesystem
paths are excluded from the freeze hash so the same manifest can be replicated
on another machine without changing the benchmark identity. The output includes
aggregate metrics, per-repository summaries, and the verified hash.

A valid hash proves the evaluated definition did not change after it was frozen;
it does not by itself prove the labels were independently authored before tuning.
Preserve manifest history and the task-definition process as audit evidence.

### Frozen semantic holdout #13

Version 1.10 includes a fresh **no-identifier-leakage semantic holdout** for
measuring whether hybrid chunk retrieval improves natural-language file
discovery beyond ACCO's lexical/structural pipeline.

The benchmark uses 24 behavior descriptions from public upstream issues across
six repositories that were not used in external holdouts #1-#12:

- Python: `Kludex/uvicorn`;
- Go: `spf13/afero`;
- Rust: `rust-lang/regex`;
- Java: `resilience4j/resilience4j`;
- JavaScript: `fastify/fastify`;
- C#: `dotnet/command-line-api`.

The audit sequence is intentionally stronger than a single final-manifest hash.
The exact 24 queries and repository revisions were committed **before target
files or fixes were inspected** in
`benchmarks/semantic-holdout-13.query-freeze.json`.

Query-only freeze:

- commit: `f3247c1d4c8e388de653aea1a5de4fa4624f82ce`;
- canonical SHA-256:
  `8cdf871ea2fcbe59161a332f1f0ce0f93b087a6c3560acebadb5ee338c4169bf`.

Ground truth was then collected without changing those queries. A post-freeze
answer-identity audit excluded two tasks from the semantic headline rather than
rewriting them: one Uvicorn task contains exact target member names
(`restart` / `shutdown`), and one System.CommandLine task is too close to
the public `CustomParser` member identity. Both remain visible in the frozen
manifest with exclusion reasons. The headline cohort is therefore **22 of the
24 frozen tasks**.

Final semantic ground-truth SHA-256:

`dc6ea6c3641db573b5b05473f2bc4ee13e0f05a4f093cb86f803e68c7b265d25`

Every eligible task is evaluated under the same file-count and token limits
against three arms:

1. **ACCO lexical/structural** — the current validated pipeline with
   semantic retrieval disabled;
2. **ACCO hybrid semantic** — the same pipeline with persistent
   chunk-level semantic retrieval enabled;
3. **trivial lexical baseline** — distinct normalized query-term overlap only,
   with no structural authority, fuzzy correction, dependency graph, feedback,
   or semantic evidence.

The semantic arm is pinned to `all-MiniLM-L6-v2` revision
`bc57282bc374d33e0d6c4de27f12dc1c2a87f37a`. Model revision participates in
ACCO's semantic vector/query-cache identity. The evidence workflow
explicitly removes `hnswlib`, so the canonical first run uses exact cosine
over the persistent vectors rather than approximate nearest-neighbor search.

The first real evaluation ran once in GitHub Actions
**35537362040** and permanently burned this suite for tuning. The exact-cosine
result over the 22 eligible tasks was:

| Arm | File recall |
| --- | ---: |
| ACCO hybrid semantic | **50.00% (11/22)** |
| ACCO lexical/structural | **45.45% (10/22)** |
| Trivial lexical baseline | **40.91% (9/22)** |

Hybrid semantic retrieval recovered one task missed by ACCO's lexical
arm and regressed none. Mean estimated context reduction was effectively flat
(97.8374% vs 97.8373%).

The result is useful precisely because it is not inflated: the semantic
mechanism shows a real but small improvement, while several repositories still
have difficult behavior-only misses. Holdout #13 must not be used as the tuning
loop for those misses.

Fresh holdout #14 was subsequently frozen before evaluation with 24
issue-derived natural-language tasks across six repositories; four were
conservatively excluded after ground-truth review, leaving 20 eligible tasks.
Its first complete exact-cosine run was GitHub Actions **35615316639**:

| Arm | File recall |
| --- | ---: |
| ACCO hybrid semantic | **82.50%** |
| ACCO lexical/structural | **80.00%** |
| Trivial lexical baseline | **70.00%** |

The semantic arm improved aggregate file recall by 2.5 percentage points with
zero regressions. One two-file target was partially recovered, so the run
reported zero complete `semantic_recovered_tasks`. Mean estimated context
reduction remained essentially identical (98.9516% semantic vs 98.9515%
lexical). That first run burned #14.

Any rerun after tuning against #14 is development evidence only. In particular,
the later 87.5% semantic development result must not be reported as fresh
generalization evidence. The next independent cohort is semantic holdout #15: its queries and
pinned repository revisions were frozen first, and its ground truth is now
frozen in `benchmarks/semantic-holdout-15.frozen.json` (13 eligible, 8
identifier-bearing reported separately, 3 excluded; see `VALIDATION.md` for the
rule and an independence disclosure). The first evaluation is still pending.

These are retrieval benchmarks. File-recall improvement does not by itself
establish lower API cost, coding-task success, or cost per successful task.

## Automated end-to-end cost-per-success experiment

> **Development evidence (not a publishable claim):** a 144-run paired run of
> the 24 SWE-bench tasks on a Claude subscription, with each agent inside its
> task's SWE-bench image, measured ACCO `4856959` at −21.1% cost per success
> (task-cluster 95% CI 9.7–31.4%) with 55/72 vs 56/72 solved. The suite was not
> frozen and success was one run lower, so the gate below withholds the
> headline. See
> [`benchmarks/e2e-subscription-swebench-24-2026-09-27.md`](benchmarks/e2e-subscription-swebench-24-2026-09-27.md).

For evidence that supports a public cost claim, use the executable experiment
harness rather than hand-assembling a few runs. It exports history-isolated snapshots at pinned revisions, randomizes
baseline/enabled order deterministically, runs multiple trials, applies Token
Saver only in the enabled arm, executes the task's verifier outside the agent,
captures the real Claude Code transcript, and checkpoints after every run so an
interrupted paid experiment can resume safely. The exported snapshot is
re-initialized as a one-commit Git repository, so an agent cannot recover the
historical gold fix from later commits or remote branches.

The publication gate deliberately requires **at least 20 distinct tasks and at
least 3 paired trials per task**. A 20-task suite therefore means 120 agent runs
(20 tasks × 3 trials × 2 conditions). Prefer 20–50 historical real-world bug
fixes/refactors across several repositories and task types rather than many near-
duplicates from one project.

Start from `benchmarks/e2e-suite.example.json`. Each task must pin a repository
revision, preserve the exact prompt (plus its SHA-256), and specify one or more
independent verifier commands. Do not use the agent's own "done" statement as
the success label.

A production-ready frozen suite is checked in as
`benchmarks/e2e-swebench-24.frozen.json`. It contains 24 historical SWE-bench
Verified issues across scikit-learn, pytest, Astropy, Pylint, Requests, Xarray,
and Seaborn, with three paired trials per task (**144 agent runs**). The public
repository URL, task revision, prompt, hidden regression patch, official
SWE-bench evaluation image, and canonical test command are frozen into the suite
hash; only the machine-local clone path is excluded.

Prepare its external repositories without checking them into this repository:

```bash
python scripts/prepare_e2e_repos.py benchmarks/e2e-swebench-24.frozen.json
```

For these tasks, the hidden regression patch is not present while the coding
agent runs. After the agent exits, its diff is captured, then a fresh official
SWE-bench Docker image applies the agent patch and hidden test patch and executes
the canonical test command inside the benchmark's prepared environment.

A run is graded per test, not by the exit code of the whole command, because
official images can carry pre-existing errors (for example broken fixtures)
that make it nonzero even for a correct fix. A run is **resolved** when every
`source.fail_to_pass` test passes and no test that passed on the unpatched
reference regressed. The reference is the same image with the hidden tests
applied and no agent patch; it is computed once per task and cached under
`<out>.artifacts/_reference/`. Agent edits to files the hidden test patch
modifies are removed before verification (the full patch stays recorded as
`agent.patch`; the verified one is `agent.graded.patch`), so an agent that also
edits a test file cannot make the hidden tests fail to apply.

Before any paid run, finalize the task definitions and experimental design, then
freeze them:

```bash
acco experiment benchmarks/e2e-suite.json \
  --print-task-definition-hash
```

Copy that SHA-256 into `protocol.task_definition_sha256`, set `frozen_at`,
commit the suite, and inspect the randomized schedule without calling a model:

```bash
acco experiment benchmarks/e2e-suite.json \
  --out benchmark-runs.json \
  --dry-run
```

Run the experiment:

```bash
acco experiment benchmarks/e2e-suite.json \
  --out benchmark-runs.json
```

The baseline arm exports `ACCO_DISABLED=1`, which makes any inherited
ACCO hook a true no-op. The enabled arm installs project-local hooks.
Both arms receive the same history-isolated source snapshot, exact prompt, model,
turn limit, and verifier. Hidden SWE-bench regression tests are applied only
after the agent process has ended.
To avoid double instrumentation, the runner refuses to start when it detects a
user-level `acco hook`; use a clean host configuration for publishable
runs rather than bypassing that guard.

For development/smoke experiments with fewer tasks or an unfrozen suite, pass
`--allow-development`. Those runs are intentionally rejected by the publication
gate.

After the runs finish, price the exact recorded model usage and require the broad
protocol:

```bash
acco benchmark benchmark-runs.json \
  --rates rates.json \
  --require-publishable
```

The result includes success rates, failed-run cost, cost per success, per-task
improvements/regressions, and deterministic **95% task-cluster bootstrap
intervals**. Repeated trials are resampled as one task cluster; three trials of
one task are not treated as three independent tasks. The report separately marks
whether the frozen protocol is valid, whether a quality-parity cost claim is
allowed, and whether the 95% interval for cost-per-success reduction is entirely
above zero.

Raw transcripts and verifier outputs can contain source code or secrets. Keep
them private when needed; the checked-in suite definition, revision pins, prompt
hashes, verifier definitions, rates, and aggregate result are sufficient to make
the experimental design auditable.

### v1.13 optimization-platform treatment exposure

The v1.13 recovery/schema/prefix/proxy/browser/optimizer additions are not
assigned a new savings percentage merely because their mechanism tests pass.
A publishable bundle experiment must keep the task, repository revision, model,
turn/tool limits, verifier, and pricing source identical between paired arms.

For the broad platform bundle, the control should use the same installed Token
Saver binary with the new treatment surfaces disabled or left at their
backward-compatible defaults. The treatment may enable adaptive MCP disclosure,
recoverable schema compression, provider request transformation, and other
declared v1.13 surfaces. **Do not change the model between arms** when the goal
is to measure this bundle; model-routing savings require their own calibrated
experiment or a design that explicitly isolates model choice.

The experiment artifact must prove treatment exposure rather than assuming that
configuration implies use. At minimum, report:

- MCP profile/tool-list exposure and whether schema compression actually changed
  an advertised catalog;
- provider transform activation and before/after request-token estimates;
- stable-prefix hit/miss counters when prefix tracking is part of the treatment;
- recovery handles emitted and successful exact-recovery spot checks;
- memory/tool-result/browser optimizations only on tasks where those surfaces
  were actually exercised;
- total tool calls, repeated Reads/commands, provider input/cache/output usage,
  latency, verifier success, and blind response quality.

A feature that never activates is not evidence for that feature. Bundle-level
cost-per-success may still be measured when the randomized treatment is the
whole declared platform, but the report must preserve per-feature activation so
readers can distinguish “enabled” from “used.”

The existing publication gate remains authoritative: enough distinct tasks and
paired trials, independent verification, blind quality parity, complete
model/cache-aware pricing evidence, and a strictly positive task-cluster 95%
confidence-interval lower bound for cost-per-success reduction. There is
currently **no completed publishable v1.13 bundle experiment** in the repository.

## Paired agent outcomes

Record independently validated baseline and ACCO runs using the schema in
`benchmarks/agent-runs.example.json`, then run:

```bash
acco agent-evaluate benchmarks/agent-runs.json
```

The evaluator pairs runs by `(task, trial, condition)`. `trial` defaults to
`1` for backward-compatible single-pair manifests, but repeated experiments
should number trials explicitly. It reports input and output tokens, output
tokens per successful run, retries, elapsed time, context failures, success
rate, and total tokens per success. It also summarizes paired per-trial
reductions with median, p10/p90, standard deviation, and a deterministic 95%
bootstrap confidence interval.

Raw token reductions remain measurable without a quality grader, but
`claim_allowed` is **false unless blind quality evidence is present**, task
success is at parity, correctness/safety and weighted quality remain within the
documented tolerance, blockers do not increase, and the per-success denominator
is available.

For generation-time output-policy experiments, the same manifest can carry
optional **blind response-quality evidence**. Score both conditions on identical
tasks/trials after relabelling them so the grader cannot see which response came
from ACCO. The built-in rubric weights correctness 40%, completeness
20%, actionability 15%, safety 15%, and concision 10%.

```json
{
  "quality_evaluation": {
    "blinded": true,
    "judge": "independent-response-grader"
  },
  "runs": [
    {
      "task": "fix-session-refresh",
      "trial": 1,
      "condition": "baseline",
      "success": true,
      "input_tokens": 18000,
      "output_tokens": 1200,
      "quality": {
        "correctness": 5,
        "completeness": 5,
        "actionability": 4,
        "safety": 5,
        "concision": 3
      },
      "blocker": false
    }
  ]
}
```

When quality scores are supplied, every paired run must be scored. ACCO
then requires task-success parity, no material correctness/safety regression,
no increase in blockers, and weighted-quality parity before authorizing a
savings claim. `raw_output_token_reduction` remains a descriptive measurement;
`output_tokens_per_success_reduction` is the stronger generated-output metric,
and `tokens_per_success_reduction` measures total input + output efficiency per
successful run. Unblinded or missing quality evidence is reported through
`claim_blockers` and cannot authorize a savings claim.

For a publishable output-cost claim, use at least 20 distinct frozen tasks and
three randomized paired trials per task, keep the model/prompt/tool settings
identical, independently verify task success, and report output-token reduction
next to cost per success rather than treating response length alone as quality.

### Automated end-to-end evidence pipeline

The high-level production path is now:

```bash
acco evidence-run benchmarks/e2e-swebench-24.frozen.json \
  --out benchmark-runs.json \
  --require-publishable
```

The command is checkpointed across paid agent runs and judge calls. It runs the
frozen randomized experiment, executes independent hidden verification, extracts
only final assistant response text for a balanced deterministic blind A/B judge,
writes quality scores back into the same run identities, evaluates exact
cache-TTL-aware cost per successful task, and emits an adaptive-budget
calibration artifact. The judge never receives baseline/ACCO labels,
patches, verifier outcomes, or billing data.

The repository also ships a paid GitHub workflow for the existing **24-task ×
3-trial SWE-bench Verified suite**. A smoke pair must first prove real agent
usage, output-policy telemetry, blind grading, and pricing. Only then does the
24-task matrix run. Aggregation blind-grades all 72 pairs and enforces the
publishability gate. The workflow requires an explicit paid-run confirmation;
merging the feature alone is not a savings result.

### Joined output-effectiveness evidence

The paired experiment artifact now carries transcript-measured fresh input,
cache creation, cache read, output tokens, and model calls for both arms.
Enabled runs also carry the selected output task/mode/budget when Claude hooks
emit policy telemetry. After blind response grading has been attached to the
same task/trial records, run:

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

The publication gate requires the existing broad design (>=20 distinct frozen
tasks and >=3 trials/task), recomputes and verifies the frozen task-definition
SHA-256, and checks each run's model/revision/prompt hash against that frozen
suite. It also requires no task-success regression, blind correctness/safety
and weighted-quality parity, complete optimized-arm policy telemetry with a
measured task/mode/budget, exact telemetry/transcript usage agreement, and
complete cost evidence. Cache-creation usage is split into 5-minute, 1-hour,
and unknown-TTL buckets; any nonzero bucket without a supplied rate makes
derived cost incomplete. A positive point estimate is not enough: the 95%
task-cluster bootstrap interval for cost-per-success reduction must remain
strictly above zero. Repeated trials are resampled as one task cluster rather
than treated as independent evidence.

This is the preferred end-to-end output-cost claim surface. Raw context
reduction, response length, or a low budget-utilization ratio are not
substitutes for cost per independently verified successful task.

### Frozen session-efficiency causal holdout

Operational dashboard savings are not enough to establish that continuity,
cross-turn dedup, or waste prevention improve coding-agent economics. Version
1.8 therefore adds a separate frozen paired-agent holdout:

```bash
acco session-holdout \
  benchmarks/session-efficiency-swebench-24.frozen.json \
  --out session-holdout-runs.json \
  --require-publishable
```

The suite reuses the already frozen 24 SWE-bench Verified tasks and hidden
verification definitions, with three randomized trials per task. The control is
**not a historical 1.6 executable**. Both arms install the same current Token
Saver build; the baseline sets only the four session-efficiency controls to
zero, while treatment sets them to one. This holds retrieval, output processors,
model, host adapter, prompt, revision, and grader constant.

Every arm uses the same two-session protocol:

1. phase 1 receives the frozen task and is restricted to Read/Grep/Glob/Bash;
2. phase 1 must leave benchmark-visible repository state unchanged;
3. the runner invokes ACCO's actual `SessionStart:resume` hook;
4. phase 2 starts in a new Claude home/session and implements/verifies the task;
5. treatment may receive the structured continuity checkpoint; control cannot.

That forced boundary gives continuity a deterministic opportunity to affect the
second session without feeding phase-1 prose directly to phase 2.

#### Independent outcome metrics

The evaluator derives behavioral outcomes from raw Claude transcripts for both
arms:

- total tool calls;
- total input tokens, with exact cache fields retained for pricing;
- normalized repeated Bash calls;
- repeated identical failing Bash-result attempts;
- duplicate full-file Reads;
- independent task success;
- blind final-response quality;
- cache-TTL-aware cost per successful task.

Treatment-side ACCO efficiency events are kept in a separate
`feature_activation` block. They prove whether continuity, dedup, and waste
signals fired, but they are not substituted for outcome metrics.

#### Statistical design

The frozen suite contains 24 task clusters and 3 trials/task. Point estimates
are accompanied by deterministic 2,000-sample task-cluster bootstrap 95%
intervals for tool-call reduction, input-token reduction, retry reduction, and
cost-per-success reduction. Trials from the same task are sampled together to
avoid treating repeated trials as independent tasks.

The publication gate requires:

- at least 20 distinct tasks and 3 trials/task;
- exact frozen definition hash and isolated condition profiles;
- matching model/prompt/revision identity between arms;
- no manual intervention;
- independent task-success parity;
- blind response-quality parity;
- complete cache-TTL-aware pricing;
- zero session-efficiency events in control;
- exactly the forced continuity exposure path, with at least one restore for
  every treatment arm-run;
- observed dedup, continuity, and waste feature families somewhere in treatment;
- positive cost-per-success point reduction;
- cost-per-success 95% task-cluster CI lower bound strictly above zero.

The design estimates the **combined session-efficiency bundle**. Feature
activation counts do not identify each mechanism's individual causal effect; a
future ablation design would be required for that.

The dedicated GitHub workflow requires `RUN_SESSION_288` because the 144
arm-runs contain 288 paid Claude task phases, before blind-grader calls. A paid
smoke proves the two-phase runner, control isolation, continuity hook, transcript
metrics, blind grader, and pricing path before the full matrix starts.

No session-efficiency savings percentage should be published from the frozen
definition alone. A claim starts only after the paid workflow completes and this
gate passes.

### Frozen session-efficiency output-quality gate

The session-efficiency layer does not replace retrieval or end-to-end evidence.
Its expanded command processors have a separate deterministic frozen fixture:

```bash
acco output-replay \
  benchmarks/output-quality-session-v17.frozen.json \
  --require-frozen
```

The fixture definition is SHA-256 frozen and covers search, lint, typecheck,
compiled tests, build diagnostics, git status, and container logs. Each case can
require exact preserved evidence, minimum token reduction, and strings that the
transformer must not introduce. CI runs this gate in addition to the external
retrieval holdout and base-vs-candidate ranking checks.

Cross-turn dedup itself is intentionally simpler than fuzzy compression: it only
fires when the normalized command and exact output digest match. Unchanged
full-file Read dedup uses the existing verified read digest. These mechanics are
covered by deterministic tests; any real end-to-end savings claim still belongs
to the randomized `evidence-run` protocol with task success and blind quality.

The local `dashboard` is also an operational surface, not a benchmark. Its
tool-context savings are estimated from observed before/after text, while its
Claude usage counters come from available transcript billing fields. Those
categories stay separate and are never promoted to cost-per-success evidence.

### Runtime budget telemetry

For ordinary Claude Code use, `output-telemetry` records actual transcript
usage counters against the selected policy budget without storing conversation
content. Use it to discover candidate task/mode groups for future experiments:

```bash
acco output-telemetry . --json
```

A low p90 budget-utilization ratio is only an **observational tuning signal**.
Do not feed it directly into calibration. A completed `Stop` turn is not proof
of task success, and telemetry has no blind response-quality score. Validate
candidate budget changes with paired successful runs before calibrating them.

### Calibrating adaptive output budgets

ACCO can turn the same blind paired evidence into conservative learned
task/mode bases. Add `output_task` and `output_mode` to ACCO runs, then:

```bash
acco output-calibrate benchmarks/agent-runs.json \
  --out .acco.output-calibration.json
```

The calibrator considers only pairs where baseline and ACCO both succeed,
the ACCO response has no blocker, and correctness, safety, and weighted
blind quality remain within the evaluator parity tolerance. At least three valid samples spanning at least three distinct task IDs are
required per task/mode. The recommendation is p90 observed output
tokens plus a 15% safety margin, bounded by the mode safety range. Failed,
unblinded, or degraded short runs therefore cannot train the controller toward
an artificially small budget.

## Live host validation is a separate manual gate

Start with the consolidated configuration/index check, then run the deeper host
transport check before a live host trial:

```bash
acco doctor . --require-ready
acco host-check . --require-ready
```

This checks project/user hook configuration, probes the host executable version,
runs a synthetic 500-line Bash response through the real PostToolUse hook, and
retrieves an omitted middle line from ACCO's saved original output. That
is a local transport test; it does **not** prove the host actually feeds
`hookSpecificOutput.updatedToolOutput` back to the model.

For that final gate, capture a real host debug transcript and supply it explicitly:

```bash
acco host-check . \
  --live-evidence /path/to/claude-debug.log \
  --require-live
```

`live_verified=true` is reported only when the supplied evidence contains both
the host replacement field and ACCO's filtered-output recovery marker.
The manual validation protocol remains:

1. Record `claude --version`, model ID, configuration, and ACCO version.
2. Use a disposable project. Install the package and its project hooks. Check
   that inherited user hooks do not run ACCO a second time.
3. Start Claude Code with debugging enabled. Ask it to run a harmless command
   that prints 500 distinct progress lines. Do not use a command with side effects.
4. Verify the host accepts `hookSpecificOutput.updatedToolOutput` without a
   validation error. The model-visible result should include the recovery note,
   show the shortened head/tail, and preserve the structured Bash fields.
   Hook stdout alone is not sufficient evidence of host acceptance.
5. Ask it to retrieve a known omitted middle line using the supplied
   `acco output` command. Verify the exact line without rerunning the
   original command. Test stderr independently and test a failing Jest-style
   output containing a test name, stack location and multiline assertion diff.
6. Test a >220-line source read. A bounded Read must return actual bytes, and a
   subsequent Edit must succeed. Repeat after `/compact`; prior full-read state
   must not block access to needed source. Test two independent sessions.
7. Save the version, debug evidence and outcomes. If the installed host does not
   support structured replacement, use manual `filter` until upgraded. Do not
   claim automatic savings based on an ignored hook field.

No paid model call or live Claude Code session was executed in the repair
workspace. Automated tests cover the documented contract, subprocess transport,
state isolation, retrieval, and accounting. Live behavior remains a separate gate.

## Paired task protocol

- Choose representative tasks before measuring: bug fixes, refactors, unfamiliar
  repo navigation, noisy passing tests, and failures requiring deep diagnostics.
- Use independent fresh worktrees at the same commit and the same exact prompt,
  model, effort, tools, system instructions, and approval configuration.
- In baseline, disable all ACCO hooks (including user-scope hooks). In
  enabled runs, use the release's hooks. Do not add orientation maps to only one
  arm unless that is the specific intervention being tested.
- Randomize condition order and run multiple trials per task. Record cache
  policy and cold/warm conditions rather than assuming a five-minute TTL.
- Keep tests/evaluation independent of the agent. Record success, regression
  checks, elapsed time, retries and any manual intervention. A smaller context
  that fails the task is not a win.
- Preserve each run's complete transcripts, including nested subagent
  transcripts where applicable. Do not reuse a transcript across runs.
- Keep raw transcripts local; they may contain code or secrets.

`acco benchmark` analyzes recorded runs; it does not execute coding agents
or certify evaluator outcomes. It verifies paired task/trial identity, revision,
model and prompt metadata, requires measured usage and explicit prices, and
rejects incomplete or duplicate runs. Metadata must be recorded honestly by the
runner; the evaluator does not independently attest your checkout or prompt.

## Run manifest

Paths are relative to the manifest file. `success` is determined by independent
validation, not by the agent's own assertion. Use the actual SHA-256 of the prompt.

```json
{
  "runs": [
    {
      "task": "fix-user-lookup",
      "trial": 1,
      "condition": "baseline",
      "revision": "ACTUAL_COMMIT",
      "model": "EXACT_MODEL_ID",
      "prompt_sha256": "ACTUAL_PROMPT_SHA256",
      "success": true,
      "validation": "Independent tests passed; no regressions in required suite",
      "seconds": 120.5,
      "transcripts": ["runs/baseline.jsonl"]
    },
    {
      "task": "fix-user-lookup",
      "trial": 1,
      "condition": "enabled",
      "revision": "ACTUAL_COMMIT",
      "model": "EXACT_MODEL_ID",
      "prompt_sha256": "ACTUAL_PROMPT_SHA256",
      "success": true,
      "validation": "Same independent checks passed",
      "seconds": 118.2,
      "transcripts": ["runs/enabled.jsonl"]
    }
  ]
}
```

The times above demonstrate the schema; they are not measured results.

## Rate file

Create a JSON object mapping each exact model ID to numeric USD-per-million
rates: `input`, `cache_write_5m`, `cache_write_1h`, `cache_read`, `output`.
For example, this object is syntactically valid but deliberately uses a fictitious
model and synthetic prices. **It must not be used to price actual models.**

```json
{
  "synthetic-test-model": {
    "input": 1,
    "cache_write_5m": 1.25,
    "cache_write_1h": 2,
    "cache_read": 0.1,
    "output": 5
  }
}
```

Only add `cache_write_unknown` when the run's actual cache configuration permits
an explicit rate for missing TTL details. Missing prices or unexplained cache
creation prevent a complete cost result.

```bash
acco benchmark runs.json --rates rates.json
```

The output includes per-condition success rates, total tokens by usage type,
tool-result counts, repeated reads, elapsed time, total cost, and cost per success.
Costs from failed attempts are included. A reduced success rate suppresses the
headline cost-per-success reduction. Inspect per-task outcomes too: aggregate
success parity does not prove each task retained the same quality.

For the automated experiment path above, `acco benchmark` reports a
deterministic task-cluster bootstrap 95% interval. This is still an empirical
benchmark, not a proof that savings generalize to every repository or model.
Before publishing savings, retain the frozen task definitions, repeated trials,
model and host versions, prices, independent checks, and raw results needed to
reproduce the claim.


## Frozen knowledge-efficiency holdout

Knowledge-assisted read avoidance is evaluated separately from retrieval recall
and from the existing session-efficiency bundle. The frozen definition is:

```text
benchmarks/knowledge-efficiency-swebench-24.frozen.json
24 SWE-bench Verified tasks
3 trials per task
2 conditions
= 144 arm-runs
= 288 fresh Claude task phases
```

The causal contract intentionally equalizes memory creation. Phase 1 is
investigation-only in both arms and requires the agent to persist 1–3
`verified` ACCO findings backed by source it actually inspected.
Repository state must remain unchanged. Phase 2 uses a fresh Claude home/session
and receives no conversation transcript or continuity checkpoint.

The control and treatment install the **same current ACCO binary**.
Both disable continuity, cross-turn command/read dedup, reread blocking, and
behavioral waste detection. The control disables knowledge read avoidance and
cache economics; the treatment enables those two switches. This tests the
combined **knowledge read-avoidance + cache gate** effect without attributing
savings to unrelated 1.7 session features.

Outcome metrics come from independent evidence:

- raw transcripts: total tool calls, input tokens, and duplicate Reads;
- hidden task verifier: task success;
- blinded judge: response quality parity;
- transcript cache-usage fields plus frozen rates: billed cost/cost per success;
- ACCO's efficiency ledger: feature exposure only (knowledge seeds,
  read-avoidance interventions, and cache-economics-approved interventions).

The ledger never grades its own success. A publishable claim requires at least
20 tasks, three trials per task, all paired identities intact, no manual
intervention, success parity, blind-quality verification, complete pricing,
verified knowledge seeding in every arm-run, zero control avoidance activation,
observed treatment activation, positive cost-per-success reduction, and a
task-cluster 95% confidence interval with a strictly positive lower bound.

Run the frozen preflight without paid execution:

```bash
acco knowledge-holdout \
  benchmarks/knowledge-efficiency-swebench-24.frozen.json \
  --out /tmp/knowledge-holdout-runs.json \
  --dry-run
```

The paid workflow is
`.github/workflows/knowledge-efficiency-holdout.yml` and requires the explicit
`RUN_KNOWLEDGE_288` confirmation. Until it completes successfully, the
mechanism has **no publishable end-to-end savings percentage**.

