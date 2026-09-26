# acco proxy

Install and manage persistent background ACCO provider proxies for a project.

Unlike acco wrap, which owns one foreground agent launch, acco proxy install
creates stable loopback listeners that start automatically with the current user
session and attaches supported hosts to those listeners.

## Quick start

    cd /path/to/project
    acco proxy install .
    acco proxy install . --host claude --host codex
    acco proxy status .
    acco proxy stop .
    acco proxy start .
    acco proxy uninstall .

Current automatic persistent attachment is intentionally limited to **Claude
Code** and **Codex**. Other hosts continue to use acco wrap until ACCO has a
stable documented way to persist their provider routing without editing private
state or persisting credentials.

## Architecture

A project can have more than one persistent listener because provider wire
protocols differ:

    Claude Code -> ANTHROPIC_BASE_URL -> ACCO Anthropic listener -> Anthropic upstream
    Codex      -> model_providers.acco -> ACCO OpenAI listener -> OpenAI upstream

Profiles are keyed by project + provider. Re-running installation reuses an
existing profile's stable port unless a new provider-specific port is supplied.

## Native autostart

| Platform | Supervisor |
|---|---|
| Linux | systemd --user service under ~/.config/systemd/user |
| macOS | user LaunchAgent under ~/Library/LaunchAgents |
| Windows | current-user Task Scheduler logon task |

The service definition stores the ACCO executable path, a content-free profile
identifier, and the ACCO state-directory path needed to find that profile after
login. It stores no API keys, provider authorization tokens, prompts, tool output,
or source content. The provider client continues
to supply its normal authentication headers on requests through the loopback proxy.

## Verified readiness before host mutation

Installation does not attach a host merely because an operating-system service
creation command returned success. The background proxy exposes a loopback-only
/__acco/health identity containing the ACCO instance id, provider, and a
content-free project-root fingerprint. ACCO verifies that exact identity before
changing Claude or Codex routing.

## Claude Code attachment

For Claude, ACCO owns only ANTHROPIC_BASE_URL and
ACCO_PERSISTENT_PROXY_PROFILE inside the project .claude/settings.json env map.
Existing hooks, permissions, and unrelated environment keys are preserved.

If ANTHROPIC_BASE_URL already exists and is not owned by the same ACCO profile,
installation fails closed. ACCO does not silently replace an existing gateway.

## Codex attachment

For Codex, ACCO inserts one marked provider block in the project's .codex/config.toml.
This keeps persistent routing scoped to the repository instead of changing every
Codex session for the user. Unrelated root keys and tables are preserved. If the
project config already has user-managed root model_provider or openai_base_url
routing, ACCO refuses to replace it.

When ~/.codex/auth.json reports ChatGPT authentication, the managed custom
provider includes requires_openai_auth = true; API-key users do not receive
that flag.

## Custom upstreams and stable ports

Provider-specific overrides are explicit:

    acco proxy install . --host claude \
      --upstream anthropic=https://gateway.example \
      --port anthropic=18765

For two providers:

    acco proxy install . --host claude --host codex \
      --port anthropic=18765 --port openai=18766

Persistent upstream URLs may not contain embedded credentials. Plain HTTP is
accepted only for localhost.

## Transaction and rollback behavior

A multi-provider installation is treated as one operation. If a later service
or host attachment fails, ACCO rolls back profiles created earlier in that same
operation. Reconfiguration of an existing profile keeps its previous manifest
available for restoration.

## Commands

### acco proxy install [PATH]

- --host claude|codex|all: repeatable host target. Without it ACCO auto-detects Claude/Codex.
- --upstream PROVIDER=URL: repeatable upstream override.
- --port PROVIDER=PORT: repeatable stable listener override.
- --json: machine-readable installation result.

### acco proxy status [PATH]

Shows installed profiles, stable loopback URLs, host ownership, supervisor type,
service-artifact presence, and verified runtime identity.

### acco proxy start [PATH]

Starts every installed persistent profile for the project using its native supervisor.

### acco proxy stop [PATH]

Stops listeners without removing autostart registration or host routing.

### acco proxy uninstall [PATH]

Detaches only routing still owned by each profile, removes its user-session
autostart registration, and deletes the credential-free profile manifest.

## Relationship to acco wrap

Use persistent proxy mode when you want supported hosts to route through ACCO
automatically in future sessions. Use acco wrap for temporary sessions, hosts
without a safe persistent adapter, or ambiguous/user-managed provider configuration.

The two paths use the same production provider transformation engine.
