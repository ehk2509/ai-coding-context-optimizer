# Native release signing and package-manager publication

ACCO's release pipeline supports platform-native signing without storing
credentials in the repository. Unsigned development/release builds remain
checksum-verified and GitHub-provenance-attested; stable publisher identity is
activated when the signing secrets below are configured.

## Windows Authenticode

Configure repository Actions secrets:

- `WINDOWS_SIGNING_PFX_BASE64` — base64-encoded code-signing PFX/P12.
- `WINDOWS_SIGNING_PFX_PASSWORD` — password for that certificate.

The standalone workflow imports the certificate into the ephemeral runner,
signs both x86_64 and ARM64 executables with SHA-256 and a timestamp server,
then verifies the Authenticode status before checksum/upload.

## macOS Developer ID and notarization

Configure:

- `APPLE_SIGNING_CERTIFICATE_P12_BASE64`
- `APPLE_SIGNING_CERTIFICATE_PASSWORD`
- `APPLE_SIGNING_IDENTITY` — Developer ID Application identity.
- `APPLE_ID`
- `APPLE_TEAM_ID`
- `APPLE_APP_SPECIFIC_PASSWORD`

The workflow imports the certificate into an ephemeral keychain, asks
PyInstaller to sign collected code with the Developer ID identity, verifies the
final executable, submits a ZIP wrapper to Apple's notary service, and verifies
Gatekeeper assessment before release.

## GitHub build provenance

Every standalone asset is eligible for GitHub build-provenance attestation in
addition to its SHA-256 sidecar. Provenance attestation is independent of
Authenticode/Apple signing and does not replace operating-system trust.

## Homebrew tap publication

The release always contains an architecture-complete `acco.rb`. The
`Publish native packages` workflow can create/update
`ehk2509/homebrew-acco` when the repository secret
`HOMEBREW_TAP_TOKEN` is configured with permission to create/push that
repository. After first publication users can use:

```bash
brew tap ehk2509/acco
brew install acco
```

The workflow intentionally no-ops when the token is absent.

## WinGet publication

Each release contains a `winget-manifests.zip` with multi-file schema 1.12
manifests for x64 and ARM64 portable executables. Microsoft requires manifests
to be submitted to the public `microsoft/winget-pkgs` repository and validated
through its pull-request process.

Configure `WINGET_TOKEN` with the GitHub permissions required by
`wingetcreate submit`, then run (or allow) the native-package publisher. The
publisher no-ops when the token is absent. After Microsoft accepts the manifest,
installation becomes:

```powershell
winget install --id ehk2509.ACCO
```

External package-manager acceptance is not represented as complete until those
upstream repositories contain the package.
