# Aether Desktop — Signing, Notarization & Auto-Update (M1a design)

**Status (2026-10-15):** design and preparation only. Nothing here is signed, notarized or auto-updating yet. Check the live state with `python scripts/check_release_readiness.py`.

## 1. Current state (verified)

| Item | State |
| :--- | :--- |
| Bundle signature | **Ad-hoc** (`codesign -dv`: `Signature=adhoc`, no TeamIdentifier). Valid for `codesign --verify --deep --strict`, **rejected by Gatekeeper** on other Macs |
| Developer ID identity in the keychain | None on the build machine |
| Notarization | **Not done.** `xcrun notarytool` is installed, but no Apple credentials exist in the environment; no stapled ticket |
| Updater plugin | **Not present.** `tauri-plugin-updater` is not in `src-tauri/Cargo.toml`, not in `Cargo.lock`, and not in the local cargo registry cache; adding it requires downloading new crates (not done: no new dependencies were installed) |
| Update signing key | None generated; no `plugins.updater` block in `tauri.conf.json` |
| Tauri version | 2.11.x (`tauri = "2"`), so the official mechanism is `tauri-plugin-updater` v2 |

## 2. Signing and notarization (macOS)

Prerequisites (human/credential steps):
1. Apple Developer Program membership and a **Developer ID Application** certificate installed in the build keychain.
2. Notarization credentials, either an app-specific password (`APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`) or an App Store Connect API key (`APPLE_API_KEY`, `APPLE_API_ISSUER`, `APPLE_API_KEY_PATH`). Keep them in CI secrets or the keychain; never in the repository or logs.

Pipeline changes to make once credentials exist (not done now):
* Sign the PyInstaller sidecar and every nested Mach-O (`_internal/**/*.dylib|*.so`) with the hardened runtime (`codesign --options runtime --timestamp`) **before** signing the `.app`; add entitlements only if the frozen runtime needs them (e.g. JIT/unsigned memory), keeping them minimal.
* Sign the `.app` with the Developer ID identity (Tauri reads `APPLE_SIGNING_IDENTITY`), submit with `xcrun notarytool submit --wait`, then `xcrun stapler staple` the `.app` and the DMG.
* Acceptance: `spctl --assess --type execute build/Aether.app` accepts, `xcrun stapler validate` succeeds, and `check_release_readiness.py --strict` passes the notarization checks.

## 3. Auto-update design (Tauri 2 updater)

* **Mechanism:** `tauri-plugin-updater` (official), with `bundle.createUpdaterArtifacts: true` producing `Aether.app.tar.gz` and its `.sig`; the app checks a static JSON manifest.
* **Keys:** generate an updater keypair once (`tauri signer generate`). The **public key** goes into `plugins.updater.pubkey` (committed). The **private key** (`TAURI_SIGNING_PRIVATE_KEY`, optional `..._PASSWORD`) lives only in CI secrets or an offline vault, with a backup and a documented rotation procedure. It is independent of the Apple certificate. Losing it means already-installed apps can never be updated again, so a manual-install notice must exist.
* **Manifest:** static `latest.json` served over HTTPS from the stable channel location, built with `scripts/make_update_manifest.py` (refuses empty signatures and non-HTTPS URLs). Format: `version`, `notes`, `pub_date`, `platforms.{darwin-aarch64,darwin-x86_64,windows-x86_64}.{url,signature}`.
* **Channel:** `stable` only for now. A beta channel is an open decision (roadmap §E.5).
* **Hosting:** artifact and manifest host not chosen (GitHub Releases or the website are candidates); it needs HTTPS and immutable per-version artifact URLs.
* **Client behavior (to implement with the plugin):**
  1. Check on start and on demand (Settings → "Check for updates"); never block startup on a failed check; offline is silent.
  2. Download, verify the signature with the embedded public key (the plugin rejects mismatches), show release notes, install only after user confirmation unless the user enables automatic install.
  3. Before replacing the app: gracefully stop the sidecar through the existing shutdown path (`graceful_shutdown`, SIGTERM handler and the sidecar parent watchdog added in M1a), so no orphan runtime survives an update.
  4. Never touch the data directory (`~/Library/Application Support/Aether`); schema migrations are the runtime's responsibility on next start.
* **Errors and recovery:** failed download/verification/installation leaves the running version untouched and reports a plain-language message with a "download manually" link to the DMG. Never auto-retry in a tight loop (back off, e.g. next launch/24 h). A bad release is handled by publishing a higher patch version; the manifest never points backwards. The manual DMG path always remains available.
* **Windows:** same plugin with NSIS artifacts (`windows-x86_64`), signed with the same updater key; Authenticode signing is separate and required to avoid SmartScreen warnings. Verified when a Windows runner exists (M1b).

## 4. What was prepared in M1a, and what is blocked

| Done (no credentials needed) | Blocked on |
| :--- | :--- |
| `scripts/check_release_readiness.py` (truthful, read-only status; never prints secret values) | Developer ID certificate + notarization credentials |
| `scripts/make_update_manifest.py` with tests | Downloading `tauri-plugin-updater` (new dependency) and the `tauri signer` CLI |
| This design, key-custody and recovery policy | Updater keypair generation (needs the CLI and a safe place for the private key) |
| Sidecar lifecycle fixes the updater depends on (clean stop on SIGTERM/SIGHUP/SIGINT, watchdog after SIGKILL) | Artifact/manifest hosting decision |
