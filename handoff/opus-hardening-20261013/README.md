# Opus hardening patch (2026-10-13)

Base revision: `df46b7d8756357be795caff0ebfb70725f13075a` (branch `development`).

Contents:
- `opus-hardening.patch`: changes to `src/aether/server/routes.py` (canonical approval off the event loop),
  `src/aether/missions/reviewer.py` (only completed + verified coding runs count as evidence),
  `tests/conftest.py` (ordinary tests: no provider API keys, no non-loopback/Ollama connections).
- `test_opus_hardening.py`: regression tests (copy to `tests/`).

Apply (from the repo root, on a checkout of the base revision or a compatible tree):
```
git apply --check handoff/opus-hardening-20261013/opus-hardening.patch
git apply handoff/opus-hardening-20261013/opus-hardening.patch
cp handoff/opus-hardening-20261013/test_opus_hardening.py tests/
```
Verified on the Mac: 78 targeted tests passed (with fake keys exported). The full suite was not run:
the new network guard in conftest.py may make tests that silently used the network fail.
