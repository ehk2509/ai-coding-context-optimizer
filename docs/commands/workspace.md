# `acco workspace`

Build bounded, provenance-preserving context across multiple repositories without
merging them into one giant index.

Each repository keeps its existing ACCO structural/semantic index and ranking
pipeline. The workspace layer scores repositories for the task, reserves a
bounded slot for direct package dependencies, allocates one global token budget,
and combines complete per-repository packs with explicit repository headings.

## Synopsis

```bash
acco workspace init [PATH] [--repo NAME=PATH]... [--discover]
acco workspace add NAME REPO_PATH [--path WORKSPACE]
acco workspace remove NAME [--path WORKSPACE]
acco workspace status [PATH]
acco workspace pack [PATH] --query TASK [options]
```

## Quick start

```bash
mkdir my-product
cd my-product

acco workspace init . \
  --repo frontend=../frontend \
  --repo backend=../backend \
  --repo shared=../shared

acco workspace status .
acco workspace pack . \
  --query "change authentication response shared by frontend and backend" \
  --max-tokens 10000
```

The manifest is `.acco-workspace.json`. Paths inside the workspace are stored
relative when possible. Removing a repository from the workspace never deletes
or edits that repository.

## Retrieval model

Workspace retrieval is deliberately federated:

```text
task
  |
  +--> repo A existing ACCO ranker ----+
  +--> repo B existing ACCO ranker ----+--> repository scores
  +--> repo C existing ACCO ranker ----+
                                          |
                                  package dependency hints
                                          |
                                  global token allocator
                                          |
                       +------------------+------------------+
                       |                  |                  |
                   repo A pack        repo B pack        repo C pack
                       |                  |                  |
                       +------------ provenance ------------+
                                          |
                                  workspace context
```

A workspace never makes one repository's generated summary authoritative for
another repository. Final source context still comes from each repository's
normal exact-source packer.

## Cross-repository dependency hints

ACCO reads a bounded set of package manifests to identify direct relationships
between registered repositories:

- `package.json`
- `pyproject.toml`
- `Cargo.toml`
- `go.mod`

Only package identity and declared dependency names are used. These edges can
earn a bounded workspace slot after the strongest repository seeds have been
selected. They do not override repository-local source ranking.

## Global budget

`workspace pack` treats `--max-tokens` as a hard combined budget. A small
reserve is held for repository provenance headers and dependency metadata. The
remaining budget is divided between selected repositories according to their
existing ACCO ranking evidence, with a minimum floor so a lower-scoring selected
repository still receives usable context.

If combined output would exceed the hard limit, the lowest-priority repository
is removed before any repository pack is truncated arbitrarily.

## Arguments and options

### `workspace init`

- `PATH` — workspace directory, default current directory.
- `--repo NAME=PATH` — explicit repository registration; repeatable.
- `--discover` — inspect only the workspace root and its direct children for
  repository/package markers.
- `--json` — emit the manifest as JSON.

When no `--repo` values are supplied, direct-child discovery runs
automatically.

### `workspace add`

- `NAME` — unique workspace repository name.
- `REPO_PATH` — repository directory.
- `--path WORKSPACE` — workspace root.
- `--json` — emit the updated manifest.

### `workspace remove`

- `NAME` — registered repository name.
- `--path WORKSPACE` — workspace root.
- `--json` — emit the updated manifest.

The final repository cannot be removed; initialize a new workspace instead.

### `workspace status`

Shows resolved repository paths, package identities, declared dependencies and
cross-repository edges.

### `workspace pack`

- `--query, -q TASK` — required task description.
- `--max-tokens N` — hard combined context budget, default 10000.
- `--max-repositories N` — maximum selected repositories, default 4.
- `--max-files-per-repository N` — per-repository file cap, default 8.
- `--context-lines N` — repository pack context lines, default 6.
- `--semantic, --embeddings` — enable each repository's existing semantic
  discovery layer.
- `--json` — emit text plus workspace evidence metadata.
- `-o, --out FILE` — write output to a file.

## Exit codes

- `0` — operation completed.
- `2` — invalid/missing manifest, repository, package configuration, token
  budget, or repository retrieval failure.

## Output contract

JSON workspace packs include:

- `text`
- `estimated_tokens`
- `selected_repositories`
- `repository_budgets`
- `repository_scores`
- `selected_files` keyed by repository
- `scanned_files` keyed by repository
- `dependency_edges`

Repository scores are workspace-selection evidence, not a cross-project quality
rating.

## Authoritative runtime help

Run `acco workspace --help` or `acco workspace <subcommand> --help` for the
arguments supported by the installed version.
