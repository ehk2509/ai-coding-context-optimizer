# `acco observability`

Inspect content-free provider and framework runtime metrics.

## Synopsis

```bash
acco observability [path] [--days N] [--json]
acco observability [path] [--days N] --prometheus
```

The provider proxy also serves local views at `/__acco/stats` and `/__acco/metrics`.

## Arguments and options

- `path` — project root; defaults to the current directory.
- `--days N` — reporting window in days; defaults to 7.
- `--json` — emit the structured observability report.
- `--prometheus` — emit Prometheus text exposition instead of the normal report.

## Exit codes

- `0` — report generated successfully.
- `2` — invalid reporting window or unavailable local telemetry state.

## Output contract

JSON output contains `providers`, `frameworks`, cache-TTL observation counters, output-holdout counters, the reporting window, and an evidence note. Provider/framework aggregates include call counts, status/failure counts, transform counts, token deltas, recovery counts, and latency percentiles where available.

Raw prompts, request bodies, provider responses, and tool-result content are not copied into observability events. Prometheus labels intentionally omit model ids and request-shape strings.

## Authoritative runtime help

```bash
acco observability --help
```
