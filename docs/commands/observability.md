# observability

Inspect content-free provider and framework runtime metrics.

```bash
acco observability .
acco observability . --days 14 --json
acco observability . --prometheus
```

The provider proxy also serves local views at `/__acco/stats` and
`/__acco/metrics`.

Metrics include provider/framework call counts, status classes, transform counts,
estimated context tokens removed, recovery-handle counts, and latency
percentiles. Raw request bodies, provider responses, prompts, and tool-result
content are not copied into observability events. Prometheus labels intentionally
omit model ids and request-shape strings.
