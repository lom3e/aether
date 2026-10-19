# Website deploy and release checklist

Status (2026-10-19): the site code is ready on `development`; nothing is deployed and no new release is published.

## Website (`website/`, Next.js 16)

* Vercel: import the repository, **Root Directory = `website`**, framework Next.js, Node 22. Environment: `NEXT_PUBLIC_SITE_URL=https://aethermate.com`.
* Domain: add `aethermate.com` (and `www`) in Vercel, then point DNS as Vercel indicates. `aether-workforce.org` was the old canonical in the code; redirect it only if you own it.
* Checks before pointing the domain: preview URL loads `/it` and `/en`, `/` redirects by browser language, `/sitemap.xml` and `/robots.txt` respond, the share image renders (`/it/opengraph-image`), the download button resolves to the latest release asset.
* CI: `.github/workflows/website.yml` runs lint, typecheck, tests and build on every change under `website/`.
* Analytics: none installed. If one is added it must be privacy-friendly and gated by the existing cookie banner.

## Release (what the download button serves)

The button points to `releases/latest/download/Aether.dmg`, so the site is only as current as the last published release (today v1.6.0, August: it has none of Companion 2.0, screen understanding, the signed-update plumbing or the Windows installer).

1. Decide the version and move `CHANGELOG.md` "Unreleased" under it; update the version in `pyproject.toml`, `src-tauri/Cargo.toml` and `src-tauri/tauri.conf.json` together.
2. Build on the release machine: `.venv/bin/python scripts/build_desktop_app.py` (produces `build/Aether.app` and `Aether.dmg`), then `git checkout -- src-tauri/icons`.
3. Run `scripts/check_release_readiness.py` and the smoke test `scripts/smoke_desktop_app.py`; run the Windows workflow on the same commit.
4. Signing: the macOS build is ad-hoc signed, **not notarized** (needs Developer ID credentials). The site tells people to use "Open Anyway"; keep that text until notarization lands.
5. Publish (needs your explicit go): `gh release create vX.Y.Z build/Aether.dmg --notes-file <notes>` with the asset named exactly `Aether.dmg`. Do not attach a Windows installer until it is verified on real hardware.
6. Auto-update is not live (`endpoints` is empty): do not mention it as available.
