# `acco context-budget`

Plan one **whole model-context envelope** across exact source, conversation
history, project memory, historical tool results, tool schemas, and unused
reserve.

This is a deterministic planning surface. It does not itself fetch source,
persist memory, rewrite conversation history, or call a model.

## Synopsis

```bash
acco context-budget "Debug the failing auth handler" --total-tokens 12000
acco context-budget --total-tokens 12000 --json < task.txt
```

## Allocation model

The planner starts from task-specific weights, then adjusts them using the same
deterministic prompt-complexity signals used by ACCO's adaptive output budgets.
High-risk task vocabulary increases exact-source and reserve shares.

The six components are:

- `source` — exact repository/workspace evidence.
- `history` — prior conversational/model context.
- `memory` — durable project findings recalled for the task.
- `tool_results` — historical tool/function outputs.
- `schemas` — MCP/provider tool schemas.
- `reserve` — uncommitted headroom for current-turn growth and uncertainty.

Integer allocations always sum exactly to `--total-tokens`.

## Observed demand

Callers may supply known component sizes:

```bash
acco context-budget "Debug parser" \
  --total-tokens 10000 \
  --observed-tool-results 2800 \
  --observed-schemas 450 \
  --observed-memory 200
```

When known demand is below its planned share, ACCO gives unused budget back to
exact source when source demand is unknown/unbounded, then to reserve. This
avoids stranding tokens in empty context categories.

Observed sizes do not authorize ACCO to read or persist those components; they
are numeric planning inputs only.

## Runtime integration

The planner is opt-in. Existing ACCO projects keep their current behavior until
either:

- `acco pack --context-budget N` is used;
- `acco provider-proxy --context-budget N` is used; or
- `[context_budget] enabled = true` is configured.

Source packing uses only the plan's `source` slice while retaining
`--max-tokens` as an additional hard source ceiling.

Provider interception currently enforces the `schemas` and `tool_results`
slices using observed request sizes. It does not silently rewrite arbitrary
history or inject project memory. The `history` and `memory` allocations are
exposed for host/custom-agent orchestration and future quality-gated runtime
integration.

## Arguments and options

- `prompt` — optional task prompt. If omitted, stdin is read.
- `--total-tokens N` — required whole-context token budget; minimum 1000.
- `--task` — optional explicit `general|explanation|planning|coding|debugging|review`.
- `--observed-source N`
- `--observed-history N`
- `--observed-memory N`
- `--observed-tool-results N`
- `--observed-schemas N`
- `--json` — emit the complete allocation/evidence record.

## Exit codes

- `0` — a valid plan was produced.
- `2` — invalid total, task, or observed component input.

## Output contract

JSON contains:

- `total_tokens`
- `task`
- `complexity_tier`
- `risk_level`
- `allocations`
- normalized `weights`
- supplied `observed_tokens`
- bounded deterministic `reasons`

The plan is policy evidence, not a claim that the allocation improves task
success. Such a claim requires paired-agent validation.

## Authoritative runtime help

Run `acco context-budget --help` for the arguments supported by the installed
version.
