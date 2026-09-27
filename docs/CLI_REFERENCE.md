# CLI reference

ACCO now exposes one discoverable top-level command surface:

```bash
acco --help
acco commands
acco <command> --help
```

`acco --help` lists both registry-backed commands and
legacy-compatible commands. `acco commands` lists the registry-backed
surface used for new development. The pages below document **all shipped
commands**, including accepted arguments/options, exit semantics, and structured
output contracts.

For machine-readable fields, see [Machine-readable CLI contracts](JSON_OUTPUTS.md).

## Everyday product flow

- [`bootstrap`](commands/bootstrap.md) — persistently install ACCO, then run safe setup in one command.
- [`setup`](commands/setup.md) — one-command detect/configure/index/verify onboarding.
- [`start`](commands/start.md) — launch the detected/preferred coding agent with ACCO.
- [`status`](commands/status.md) — simple project health and local efficiency evidence.
- [`demo`](commands/demo.md) — provider-free repository context demonstration.
- [`savings`](commands/savings.md) — summarize locally observed context reductions.
- [`update`](commands/update.md) — inspect/apply the recommended package-manager upgrade.
- [`advanced`](commands/advanced.md) — list the full expert command surface.
- [`uninstall`](commands/uninstall.md) — remove only ACCO-owned entries.

## Setup and host lifecycle

- [`doctor`](commands/doctor.md) — deeper CLI/config/host/index troubleshooting health.
- [`completion`](commands/completion.md) — generate Bash/Zsh/Fish completion.
- [`commands`](commands/commands.md) — list registry-backed commands.
- [`host-check`](commands/host-check.md) — deeper Claude transport/live-host validation.
- [`client-capabilities`](commands/client-capabilities.md) — inspect conservative per-host interception/integration guarantees.
- [`serve`](commands/serve.md) — run the local MCP server.
- [`sdk-serve`](commands/sdk-serve.md) — run the loopback SDK bridge for TypeScript and other custom agents.
- [`install`](commands/install.md) — legacy/low-level Claude hook installer.
- [`wrap`](commands/wrap.md) — zero-config launch for known or inferable coding CLIs through an ephemeral/existing ACCO provider proxy.
- [`proxy`](commands/proxy.md) — install/manage persistent background provider proxies with durable Claude/Codex attachment.
- `transport-status` — report whether each host supports automatic foreground interception, automatic persistence, environment-only persistence, or manual settings.
- [`claude`](commands/claude.md) — launch Claude Code through the ACCO provider wrapper.
- [`codex`](commands/codex.md) — launch Codex through the ACCO provider wrapper.
- [`gemini`](commands/gemini.md) — launch Gemini CLI through the ACCO provider wrapper.
- [`lean-skill`](commands/lean-skill.md) — print/install the portable terse-output skill.

## Repository context and navigation

- [`pack`](commands/pack.md) — build a bounded task-aware context pack.
- [`browse`](commands/browse.md) — inspect ranked candidates/symbols/previews.
- [`impact`](commands/impact.md) — analyze callers/dependencies/tests.
- [`feedback`](commands/feedback.md) — record ranking feedback.
- [`ranking-explain`](commands/ranking-explain.md) — trace ranking score contributions.
- [`remember`](commands/remember.md) — persist an evidence-backed cross-session project finding.
- [`recall`](commands/recall.md) — retrieve current project findings relevant to a task.
- [`knowledge-status`](commands/knowledge-status.md) — inspect active/stale/superseded finding counts.
- [`semantic-index`](commands/semantic-index.md) — build/incrementally refresh persistent chunk vectors.
- [`semantic-status`](commands/semantic-status.md) — inspect semantic vector/HNSW state without loading the model.
- [`map`](commands/map.md) — build a structural repository map.
- [`outline`](commands/outline.md) — show signatures/structure for one source file.
- [`snippet`](commands/snippet.md) — extract one exact symbol body.

## Patch and review workflows

- [`pack-diff`](commands/pack-diff.md) — build bounded context around a Git diff.
- [`review`](commands/review.md) — review a diff using bounded repository evidence.

## Output optimization and recovery

- [`filter`](commands/filter.md) — compress stdin with command-aware processors.
- [`output-explain`](commands/output-explain.md) — explain processor selection/failure routing.
- [`output-replay`](commands/output-replay.md) — replay preservation/savings contracts.
- [`output-benchmark`](commands/output-benchmark.md) — evaluate deterministic output fixtures.
- [`output-calibrate`](commands/output-calibrate.md) — learn quality-gated adaptive task/mode budgets.
- [`output-effectiveness`](commands/output-effectiveness.md) — join real usage, success, blind quality, and cost-per-success evidence.
- [`output-policy`](commands/output-policy.md) — generate model-response policy instructions.
- [`output-save`](commands/output-save.md) — compact an already-generated response.
- [`output-telemetry`](commands/output-telemetry.md) — inspect real turn usage against selected output budgets.
- [`corpus-analyze`](commands/corpus-analyze.md) — mine real transcripts for highest-token generic processor gaps.
- [`output`](commands/output.md) — page a saved original command result.
- [`outputs-prune`](commands/outputs-prune.md) — prune old saved outputs.
- [`hook`](commands/hook.md) — Claude hook stdin/stdout adapter.
- [`recover`](commands/recover.md) — recover exact bytes from a `tsr_...` handle.
- [`recovery-status`](commands/recovery-status.md) — inspect exact-recovery capacity.
- [`browser-context`](commands/browser-context.md) — focus captured HTML/AX-like context with exact recovery.

## Measurement and context hygiene

- [`audit`](commands/audit.md) — consolidated context, retrieval, processor, recovery, host, and efficiency audit.
- [`sessions`](commands/sessions.md) — analyze Claude transcript token/tool evidence.
- [`dashboard`](commands/dashboard.md) — local savings, usage, continuity, and waste telemetry.\n- [`learn`](commands/learn.md) — analyze historical sessions and rank evidence-backed token/context opportunities.
- [`continuity`](commands/continuity.md) — inspect the structured resume/compaction checkpoint.
- [`guardian`](commands/guardian.md) — inspect the explicit pre-compaction checkpoint.
- [`context-audit`](commands/context-audit.md) — audit cross-host always-on instructions, skills, duplicates, and MCP context.
- [`statusline`](commands/statusline.md) — render one fast live efficiency line.
- [`cache-economics`](commands/cache-economics.md) — compare context rewrites after prompt-cache costs.
- [`budget`](commands/budget.md) — compare measured context with budget guidance.
- [`policy`](commands/policy.md) — generate lifecycle advice from transcripts.
- [`status`](commands/status.md) — inspect ACCO's session ledger.
- [`check`](commands/check.md) — CI context-budget/map-freshness check.
- [`estimate`](commands/estimate.md) — estimate/count tokens.
- [`mcp-prune`](commands/mcp-prune.md) — identify/disable unused MCP servers.
- [`prefix-status`](commands/prefix-status.md) — inspect stable provider-prefix reuse evidence.
- [`optimize`](commands/optimize.md) — plan/apply/evaluate reversible measured config optimizations.
- [`provider-proxy`](commands/provider-proxy.md) — run the opt-in local provider optimization reverse proxy.

## Retrieval validation and ranking regression

- [`evaluate`](commands/evaluate.md) — evaluate retrieval/freeze a holdout definition.
- [`agent-evaluate`](commands/agent-evaluate.md) — evaluate paired agent outcomes.
- [`blind-grade`](commands/blind-grade.md) — blind A/B-grade paired final responses.
- [`ranking-snapshot`](commands/ranking-snapshot.md) — save trace-enabled ranking evidence.
- [`ranking-diff`](commands/ranking-diff.md) — compare ranking snapshots.
- [`ranking-calibrate`](commands/ranking-calibrate.md) — aggregate PR ranking history.

## End-to-end experiments

- [`experiment`](commands/experiment.md) — run randomized paired agent trials.\n- [`trial`](commands/trial.md) — run a simple local baseline-vs-ACCO A/B on one independently verified task.
- [`evidence-run`](commands/evidence-run.md) — run/resume experiment → blind grade → cost/success → calibration.
- [`session-holdout`](commands/session-holdout.md) — run/resume the frozen v1.6-session-behavior vs v1.7-session-efficiency holdout.
- [`session-holdout-evaluate`](commands/session-holdout-evaluate.md) — evaluate merged/blind-graded session holdout evidence.
- [`knowledge-holdout`](commands/knowledge-holdout.md) — run/resume the frozen knowledge read-avoidance/cache-economics holdout.
- [`knowledge-holdout-evaluate`](commands/knowledge-holdout-evaluate.md) — evaluate completed knowledge-efficiency evidence.
- [`cost-report`](commands/cost-report.md) — analyze paired cost/success evidence.
- [`cost-advisor`](commands/cost-advisor.md) — measured local efficiency score, usage pricing, and evidence-linked next actions.
- [`pricing`](commands/pricing.md) — inspect the verified built-in Claude pricing registry and freshness metadata.
- [`model-route`](commands/model-route.md) — choose the cheapest policy-eligible model and emit an orchestrator-ready routing decision.
- [`model-route-calibrate`](commands/model-route-calibrate.md) — promote cheaper exact routing buckets only from frozen independent success + blind-quality evidence.
- [`benchmark`](commands/benchmark.md) — evaluate recorded paired-task evidence.

## Exit-code conventions

The per-command pages are authoritative. Across the CLI, the dominant
convention is:

| Code | Meaning |
|---:|---|
| `0` | Command completed and requested gates passed. |
| `1` | A requested quality/readiness/check condition failed, or required evidence was unavailable. |
| `2` | Invalid input/configuration, malformed evidence, unsafe mutation refused, or argparse usage error. |

Some legacy-compatible commands use `1` for ordinary file/runtime errors; their
pages call this out explicitly.

## Structured output

Commands with JSON output link directly to
[Machine-readable CLI contracts](JSON_OUTPUTS.md), which documents stable
top-level fields, nullability/gating behavior, and compatibility rules for
automation.

## Shell completion

```bash
acco completion bash > ~/.local/share/acco-completion.bash
acco completion zsh
acco completion fish
```

Completion intentionally covers top-level commands. Subcommand options remain
discoverable with `acco <command> --help`.


## Prompt ingress, acceleration, and Claude plugin packaging

- [`ingress-show`](commands/ingress-show.md) — inspect a bounded lossless-recovery packet for a staged oversized prompt.
- [`ingress-read`](commands/ingress-read.md) — retrieve an exact bounded range from the staged original.
- [`fastpath-status`](commands/fastpath-status.md) — inspect optional Rust acceleration and Python fallback state.
- [`claude-plugin-path`](commands/claude-plugin-path.md) — render the complete Claude Code plugin directory used by marketplace installation.
