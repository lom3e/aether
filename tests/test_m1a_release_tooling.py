"""M1a: release-readiness reporting and updater manifest generation."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


readiness = _load("check_release_readiness")
manifest = _load("make_update_manifest")


def test_signature_classification():
    assert readiness.classify_signature("Aether.app: code object is not signed at all") == "unsigned"
    assert readiness.classify_signature("Signature=adhoc\nTeamIdentifier=not set") == "adhoc"
    assert readiness.classify_signature("Authority=Developer ID Application: Someone (ABCDE12345)") == "developer-id"
    assert readiness.classify_signature("something else") == "other"


def test_notarization_env_needs_a_complete_credential_set():
    assert not readiness.notary_env_ready({})
    assert not readiness.notary_env_ready({"APPLE_ID": "a", "APPLE_PASSWORD": "b"})
    assert readiness.notary_env_ready({"APPLE_ID": "a", "APPLE_PASSWORD": "b", "APPLE_TEAM_ID": "c"})
    assert readiness.notary_env_ready({"APPLE_API_KEY": "k", "APPLE_API_ISSUER": "i", "APPLE_API_KEY_PATH": "p"})


def test_updater_config_detection():
    cfg = {"plugins": {"updater": {"pubkey": "K", "endpoints": ["https://x/latest.json"]}}, "bundle": {"createUpdaterArtifacts": True}}
    assert all(readiness.updater_configured(cfg, 'tauri-plugin-updater = "2"').values())
    assert not any(readiness.updater_configured({}, "").values())


def test_report_never_contains_secret_values(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_PASSWORD", "super-secret-value")
    monkeypatch.setenv("TAURI_SIGNING_PRIVATE_KEY", "super-secret-key")
    rep = readiness.collect(tmp_path / "missing.app")
    assert "super-secret" not in str(rep)
    assert rep["bundle_signature"] == "missing"


def test_manifest_requires_signature_https_and_semver():
    ok = dict(version="1.6.1", platform="darwin-aarch64", artifact_url="https://h/a.tar.gz", signature="SIG")
    m = manifest.build_manifest(**ok, pub_date="2026-01-01T00:00:00Z")
    assert m["platforms"]["darwin-aarch64"] == {"signature": "SIG", "url": "https://h/a.tar.gz"}
    for bad in (dict(signature="  "), dict(artifact_url="http://h/a"), dict(version="1.6"), dict(platform="linux-x")):
        with pytest.raises(ValueError):
            manifest.build_manifest(**{**ok, **bad})


def test_manifest_accumulates_platforms_per_version_only():
    a = manifest.build_manifest("1.6.1", "darwin-aarch64", "https://h/a", "S1")
    b = manifest.build_manifest("1.6.1", "windows-x86_64", "https://h/w", "S2", existing=a)
    assert set(b["platforms"]) == {"darwin-aarch64", "windows-x86_64"}
    c = manifest.build_manifest("1.7.0", "darwin-aarch64", "https://h/a2", "S3", existing=b)
    assert set(c["platforms"]) == {"darwin-aarch64"}
