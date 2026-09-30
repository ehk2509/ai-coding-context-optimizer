# `acco benchmark`

Evaluate recorded paired tasks with supplied model rates.

## Synopsis

```bash
acco benchmark <manifest> [--rates FILE] [--require-publishable] [--print-task-definition-hash]
```

## Arguments and options

- `manifest` — paired benchmark artifact.
- `--rates` pricing JSON; required unless printing the task-definition hash.
- `--require-publishable` enforces frozen broad-protocol requirements.
- `--print-task-definition-hash` prints the freeze hash without evaluating costs.

## Exit codes

`0` success; `1` malformed evidence/pricing or failed publication requirements.

## Output contract

JSON when evaluating; a single hash when printing the task-definition hash. See [Machine-readable contracts](../JSON_OUTPUTS.md#legacy-benchmark-always-json).

When experiment runs contain ACCO 1.24 runtime evidence, the JSON result also
includes `evidence.runtime_activation`: enabled-run coverage, raw event/tool
counts, and the number of runs in which each measured runtime surface was
actually active. Activation is reported separately from cost-per-success and
does not create a causal feature claim.

## Authoritative runtime help

Run `acco benchmark --help` for argparse's exact usage text for the installed version.
