# Aether Desktop — Signing, Notarization & Auto-Update

**Status (2026-10-19):** the signed-update mechanism is **implemented, verified end to end against a local test server with a throwaway key**, and from v1.7.1 **configured to read `latest.json` from the latest GitHub release** (`https://github.com/lom3e/aether/releases/latest/download/latest.json`; every release must attach `latest.json`, the `.app.tar.gz` and its `.sig`). Builds up to 1.7.0 have no endpoint. Developer ID signing and notarization are still blocked on Apple credentials (updates work without them: the updater downloads and verifies the package itself). Check the live state with `python scripts/check_release_readiness.py`.

## 1. What exists and what was verified

| Item | State |
| :--- | :--- |
| Mechanism | Official `tauri-plugin-updater` 2.12 (Tauri 2.11.5), minisign signatures, `requireSignedVersion` enabled (downgrade protection) |
| App code | `src-tauri/src/updater.rs`: commands `check_for_update` / `install_update`; only these are exposed to the UI (no capability grants the plugin's own JS commands) |
| UI | Settings → General → *Updates* card (desktop app only), IT/EN. Check, show version/notes, install on explicit click |
| Update public key | Committed in `tauri.conf.json` → `plugins.updater.pubkey` |
| Update private key | Generated, **outside the repository**: `~/.aether-signing/aether-updater.key` (+ `.password`), directory mode 700, files 600. Never printed, never in `build/`, never in the package |
| Endpoint | **None configured** (`endpoints: []`). The app reports "automatic updates are not set up for this build" and keeps the manual path |
| Release tooling | `scripts/build_update_artifacts.py` (archive + sign with `--app-version` + `latest.json`; uploads nothing), `scripts/make_update_manifest.py`, `scripts/check_release_readiness.py` |
| End-to-end verification | `scripts/e2e_update_flow.py`: builds an old (1.6.0) and new (1.6.1) test binary trusting only a temporary key and a `http://127.0.0.1` endpoint (compile-time `TAURI_CONFIG`, feature `updater-e2e`, separate target dir), then **14/14 checks passed** |
| Production key | Signs a real package with the version bound into the signature (verified locally; not published) |

E2E checks: positive: old → new installs, app relaunches, new sidecar healthy, installed binary equals the new build, no further update, no process left. Negative (old app keeps running, sidecar healthy, binary untouched, no process left): tampered archive → refused (`signature`); package signed with another key → refused (`signature`); manifest announcing a version different from the signed one → refused (`signature`); unreachable endpoint → `network`.

## 2. Failure policy

* Check/download/verification problems never stop the running app. The sidecar is stopped only **after** the package is downloaded and its signature verified.
* If the install step fails after that, the app relaunches itself from the restored bundle so the user is never left with a window and no runtime.
* Errors are classified for the UI (`not_configured`, `network`, `signature`, `install`, `busy`); the UI shows plain-language text and never installs anything automatically.
* The manual path always remains: download the latest DMG/installer and replace the app. The data directory is never touched by an update.
* A bad release is withdrawn by publishing a higher version; the manifest never points backwards.

## 3. How to publish a release (when the hosting exists)

1. `python scripts/build_distribution.py` → `build/Aether.app`, `build/Aether.dmg`.
2. (After notarization is possible, sign + notarize + staple **before** step 3, so the archive contains the notarized app.)
3. `python scripts/build_update_artifacts.py --base-url https://<host>/stable` → `build/updates/Aether_<ver>_<arch>.app.tar.gz`, `.sig`, `latest.json`.
4. Upload the archive first, then `latest.json`, to the HTTPS location; set that URL in `tauri.conf.json` → `plugins.updater.endpoints` (e.g. `https://<host>/stable/latest.json`) and rebuild once so the app knows where to look.
5. Test an update from the previous version on a clean account before announcing it.

Key custody: back up `~/.aether-signing/` to an offline vault; move the key to CI secrets (`TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`) if releases are built in CI. Losing the key means installed apps can no longer be updated automatically and users must reinstall manually; rotating it requires shipping a build that trusts the new key *before* retiring the old one.

## 4. Signing and notarization (macOS) — blocked on credentials

State: the bundle is **ad-hoc signed** (valid, but Gatekeeper rejects it on other Macs). No Developer ID certificate and no Apple notarization credentials exist in this environment; nothing was notarized.

Needed from the owner: an Apple Developer Program Developer ID Application certificate in the build keychain, and either `APPLE_ID` + app-specific password + `APPLE_TEAM_ID`, or an App Store Connect API key. Then, in the pipeline: sign the sidecar and every nested Mach-O with the hardened runtime (`codesign --options runtime --timestamp`) before signing the `.app`, add only the entitlements the frozen runtime needs, submit with `xcrun notarytool submit --wait`, `xcrun stapler staple` the app and DMG, and accept only if `spctl --assess --type execute` and `stapler validate` pass (`check_release_readiness.py --strict`).

## 5. Windows

Same plugin and updater key with NSIS artifacts (`windows-x86_64`); Authenticode signing is separate. Not verified (no Windows runner; M1b, non-blocking).
