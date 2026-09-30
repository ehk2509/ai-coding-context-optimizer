# `acco output-holdout`

Report provider-observed output-token evidence from the opt-in output-shaping holdout.

## Synopsis

Enable holdout assignment at the provider boundary:

```bash
acco provider-proxy . \
  --upstream https://api.anthropic.com \
  --provider anthropic \
  --output-holdout-rate 0.10
```

Then inspect accumulated evidence:

```bash
acco output-holdout [path] [--bootstrap-samples N] [--json]
```

## Arguments and options

- `path` — project root; defaults to the current directory.
- `--bootstrap-samples N` — deterministic bootstrap sample count; defaults to 1000.
- `--json` — emit the complete machine-readable holdout report.

Assignment is deterministic per opaque conversation identity. Only requests with an existing provider output limit that treatment can actually tighten are eligible.

## Exit codes

- `0` — report generated successfully, including when evidence is insufficient.
- `2` — invalid bootstrap configuration or unavailable report state.

## Output contract

JSON output contains the experiment id, matched conversation weight, measured output-token reduction when enough matched strata exist, a 95% bootstrap interval, and per-stratum control/treatment statistics.

This is provider-observed output-token evidence only. It does not establish response-quality parity or cost-per-success improvement.

## Authoritative runtime help

```bash
acco output-holdout --help
```
