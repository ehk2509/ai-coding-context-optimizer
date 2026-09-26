# `acco wrap`

Launch a coding CLI through ACCO's loopback provider optimization boundary without
persistently rewriting the tool's configuration.

## Synopsis

```bash
acco wrap [wrapper-options] COMMAND [wrapper-options] [-- COMMAND_ARGS...]
```

Examples:

```bash
# Unambiguous built-in presets
acco wrap claude
acco wrap codex -- --help
acco wrap gemini

# Multi-provider / arbitrary CLIs: infer from the child model
acco wrap aider -- --model gpt-4.1
acco wrap aider -- --model claude-sonnet-4-5

# Or infer from exactly one configured provider credential/base URL
OPENAI_API_KEY=... acco wrap opencode

# Reuse an already-running ACCO-compatible proxy
acco wrap opencode --proxy-url http://127.0.0.1:8787/v1

# Inspect the decision without launching anything
acco wrap custom-agent --provider anthropic --dry-run --json
```

## Zero-config provider selection

For `claude`, `codex`, and `gemini`, ACCO knows the wire provider from the
executable name. For any other command, provider selection is conservative and
uses this precedence:

1. known executable preset;
2. a recognizable child `--model` / `-m` value after the `--` separator;
3. exactly one configured provider base-URL environment variable;
4. exactly one configured provider credential family.

If multiple provider families are configured and the command/model does not
disambiguate them, ACCO fails closed and asks for `--provider`. It never
silently chooses one API key from an ambiguous shell environment.

This generic path works for CLIs that honor the standard provider base-URL
environment variable ACCO injects. Tools that require proprietary config-file,
plugin, or OAuth/BYOK rewrites still need a host-specific integration rather
than pretending generic environment interception is sufficient.

## Arguments and options

- `COMMAND` — executable to launch. A full path, including Windows
  `.exe`/`.cmd`/`.bat` paths, is accepted.
- `COMMAND_ARGS` — arguments after `--`, forwarded unchanged to the child.
- `--path` — working/project root; defaults to `.`.
- `--bind` / `--port` — ephemeral proxy listener; port `0` chooses a free
  loopback port.
- `--provider anthropic|openai|gemini` — explicit provider override when
  inference is unavailable or ambiguous.
- `--upstream` — explicit provider upstream override.
- `--base-url-env` — override the environment key redirected in the child.
- `--executable` — override executable lookup while retaining the logical
  command name used for inference.
- `--proxy-url` — skip ephemeral proxy startup and point the child at an
  already-running ACCO-compatible proxy.
- `--model-routing off|observe|calibrated` — provider routing mode; defaults to
  `off`.
- `--dry-run` — print the launch plan without starting the proxy or command.
- `--json` — with `--dry-run`, emit the plan as JSON.

Wrapper flags may appear before or after `COMMAND`, but child flags belong
after the `--` separator. This prevents ACCO flags and child flags from being
silently confused.

## Existing gateways

If the selected provider's base URL is already configured, ACCO preserves that
destination as the real upstream and inserts itself in front of it for the
child process. For example, an existing OpenAI-compatible
`https://gateway.example/v1` remains the upstream instead of being replaced by
`api.openai.com`.

Only the selected provider's base-URL variable is redirected. Credentials and
unrelated environment variables remain inherited by the child and are not
written to project files.

## Process semantics

The ephemeral proxy is terminated when the child exits. ACCO preserves the
child exit code and stdout/stderr. Wrapped children receive `ACCO_WRAPPED=1`
so recursive `acco wrap` chains fail closed rather than accidentally creating
proxy loops.

## Exit codes

- In live mode, returns the child command's exit code.
- `0` — successful dry-run.
- `2` — invalid/ambiguous provider selection, missing executable, unsafe
  configuration, or proxy startup failure.

## Output contract

Dry-run JSON contains the command, executable, provider,
`provider_source` (`preset`, `model`, `base-url-env`,
`credential-env`, or `explicit`), upstream, base-URL environment key, local
base URL, forwarded argv, routing mode, and optional existing proxy URL.

Live mode does not rewrite child stdout/stderr; it owns only provider routing,
the proxy lifecycle, and the child environment override.

## Authoritative runtime help

Run `acco wrap --help` for wrapper flags. Child-specific flags after `--`
are defined by the selected CLI.
