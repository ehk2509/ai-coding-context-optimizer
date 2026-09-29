# `acco tool-fields`

Inspect local structured tool-field importance learned from selective recovery.

## Synopsis

```bash
acco tool-fields [path] [--limit N] [--json]
```

## Arguments and options

- `path` — project root; defaults to the current directory.
- `--limit N` — maximum learned field rows to return; defaults to 50.
- `--json` — emit the complete machine-readable report.

The learner stores bounded tool identities, structural JSON paths, exposure counts, retrieval counts, and timestamps. It does not store corresponding field values.

## Exit codes

- `0` — report generated successfully.
- `2` — invalid arguments or unavailable local learner state.

## Output contract

JSON output contains `schema`, the number of observed tools, bounded learned `fields`, and a privacy statement. Each field row includes tool identity, structural field path, exposures, retrievals, confidence, and last-seen timestamp.

Field importance is a local packing hint only; exact recovery remains authoritative.

## Authoritative runtime help

```bash
acco tool-fields --help
```
