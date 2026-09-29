# `acco cache-ttl`

Inspect provider-observed prompt-cache lifetime evidence without guessing a universal provider TTL.

## Synopsis

```bash
acco cache-ttl [path] [--json]
```

## Arguments and options

- `path` — project root; defaults to the current directory.
- `--json` — emit the complete machine-readable TTL report.

ACCO learns only from explicit provider cache counters. Missing cache counters are not treated as misses. A qualified estimate requires repeated observed hits plus an exact-prefix post-hit miss.

## Exit codes

- `0` — report generated successfully.
- `2` — invalid/unavailable local report state.

## Output contract

JSON output contains `schema` and `estimates`. Each estimate identifies the provider/model and reports observations, hits, misses, the observed hit lower bound, expiry upper bound, qualified `learned_ttl_seconds`, qualification state, and evidence basis.

A learned TTL is an observed local bound, not a universal provider guarantee.

## Authoritative runtime help

```bash
acco cache-ttl --help
```
