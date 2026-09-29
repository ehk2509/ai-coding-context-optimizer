# output-holdout

Report measured provider output-token evidence from the opt-in output-shaping
holdout.

Enable assignment on the provider proxy with a control fraction:

```bash
acco provider-proxy . \
  --upstream https://api.anthropic.com \
  --provider anthropic \
  --output-holdout-rate 0.10
```

Then inspect the local result:

```bash
acco output-holdout .
acco output-holdout . --bootstrap-samples 2000 --json
```

Assignment is deterministic per opaque conversation identity. Only requests with
an existing output limit that treatment can tighten are eligible. The report
uses provider-reported output-token counts and a bootstrap interval. It does not
establish response-quality or cost-per-success parity.
