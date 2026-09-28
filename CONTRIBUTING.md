# Contributing to ACCO — AI Coding Context Optimizer

ACCO optimizes context only when correctness evidence survives. Changes
that make outputs smaller but weaken task success, diagnostic preservation, or
retrieval recall are regressions.

## Development setup

```bash
git clone https://github.com/ehk2509/ai-coding-context-optimizer.git
cd acco
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

The supported CI matrix is Python 3.10, 3.12, and 3.13.

## Before opening a PR

Run:

```bash
ruff check src tests scripts
interrogate src/acco
python -m pytest -q
acco evaluate benchmarks/context-quality.json --path . --max-tokens 6000
python scripts/check_holdout.py benchmarks/holdout-external.floor.json
```

GitHub Actions additionally runs actionlint and the PR ranking-regression
comparison.

## Architectural rules

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing central orchestration.

Important invariants include:

- host adapters stay at the edge;
- repository orchestration flows through `RepositoryContextService`;
- deterministic file scoring is independent of graph/embedding rerankers;
- post-score extensions use `RankingStageRegistry`;
- scoring does not render;
- final file ordering remains centralized;
- ranking tracing is opt-in and must not alter ranking behavior;
- output processors must preserve critical diagnostics;
- every new lossy representation must either retain an exact recovery path or
  fail closed to the original representation;
- provider/network adapters stay opt-in at the edge and must not silently widen
  the trust boundary;
- integration setup must mutate only ACCO-owned host entries.

Compatibility facades should stay thin. New features should normally grow
vertically in the relevant command/application module rather than by adding
branches to central dispatchers.

## Adding a CLI command

1. Put the implementation in the matching `command_handlers/*` module.
2. Register one `CommandSpec` in `command_registry.py`.
3. Preserve `commands.py` exports when compatibility requires it.
4. Add dispatcher tests.
5. Add the command to [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md).

## Adding a ranking stage

Implement the `RankingStage` protocol and compose it through a registry.
Do not add a new hard-coded branch to `rank_files()`.

A new stage should have tests for:

- stable name/order;
- enabled/disabled behavior;
- score/evidence mutation;
- trace visibility when observability is enabled;
- unchanged frozen holdout floor unless the PR intentionally changes ranking.

## Changing ranking behavior

Ranking PRs automatically produce immutable base/candidate snapshots and a
stage-attributed diff.

Treat an unexpected expected-file drop as something to explain, not something
to hide by adjusting ground truth. The calibration history groups frozen
ground-truth cohorts and does not justify a hard gate until the evidence floor
is reached.

## Adding an output processor

Follow [OUTPUT_OPTIMIZATION.md](OUTPUT_OPTIMIZATION.md):

- explicitly declare failed-command handling;
- preserve critical diagnostics;
- keep original output recoverable through the legacy paged-output path and,
  where the universal recovery contract is used, a valid `tsr_...` handle;
- reject compaction that does not produce a meaningful net saving;
- add replayable quality fixtures.

## Changing setup/integration behavior

Tests must prove:

- unrelated JSON/TOML/hook configuration survives;
- setup remains idempotent;
- uninstall removes only owned entries;
- conflicts are detected before mutation;
- user-modified generated content is preserved;
- Python 3.10 remains supported.

## Validation claims

Do not convert:

- estimated context reduction into dollar savings;
- retrieval recall into agent-task success;
- development/burned holdout reruns into fresh evidence;
- non-publishable paired experiments into headline results.

Update [VALIDATION.md](VALIDATION.md) when evidence changes.

## Documentation changes

Documentation is part of the product. User-facing changes should update the
relevant task guide, CLI/config reference, changelog, and examples in the same
PR.

Use concrete commands and distinguish:

- defaults from recommendations;
- deterministic facts from estimates;
- measured evidence from hypotheses;
- first-run fresh holdout evidence from burned/development reruns.

The documentation test suite also rejects broken internal links, missing command
pages, duplicated section headings, duplicated environment-variable rows, and
known semantic-evidence state drift. When a public command gains a new flag or
JSON mode, update its dedicated command page and `docs/JSON_OUTPUTS.md` in the
same PR.

## Pull-request checklist

- [ ] Tests pass locally.
- [ ] New public behavior is documented.
- [ ] Compatibility impact is explicit.
- [ ] No secrets/credentials/real private transcripts are committed.
- [ ] Ranking changes have regression evidence.
- [ ] Output changes have preservation evidence.
- [ ] Version/release docs are updated when publishing a release.
