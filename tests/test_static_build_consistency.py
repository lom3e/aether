"""
Tests for static build consistency and drift guard (P3.1).
Ensures single canonical synchronization and cryptographic verification of static assets.
"""
import json
from pathlib import Path
import sys
import tempfile
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.sync_static import (
    compute_file_sha256,
    sync_static_assets,
    verify_static_manifest,
    MANIFEST_FILENAME,
)


def test_sync_static_assets_lifecycle():
    with tempfile.TemporaryDirectory() as tmp_src, tempfile.TemporaryDirectory() as tmp_tgt:
        src = Path(tmp_src)
        tgt = Path(tmp_tgt)

        # 1. Verification fails if index.html is missing
        with pytest.raises(ValueError, match="missing or empty index.html"):
            sync_static_assets(source_dir=src, target_dir=tgt)

        # 2. Create mock dist files
        (src / "index.html").write_text("<html><body>Aether UI</body></html>", encoding="utf-8")
        assets_dir = src / "assets"
        assets_dir.mkdir()
        (assets_dir / "app.js").write_text("console.log('Aether');", encoding="utf-8")
        (assets_dir / "style.css").write_text("body { background: #000; }", encoding="utf-8")

        # 3. Synchronize
        manifest = sync_static_assets(source_dir=src, target_dir=tgt)

        assert manifest["file_count"] == 3
        assert "index.html" in manifest["files"]
        assert "assets/app.js" in manifest["files"]
        assert "assets/style.css" in manifest["files"]
        assert (tgt / MANIFEST_FILENAME).exists()

        # 4. Verify manifest matches
        ok, msg = verify_static_manifest(target_dir=tgt)
        assert ok is True
        assert "verified successfully" in msg

        # 5. Tampering detection: modify a file
        (tgt / "assets" / "app.js").write_text("console.log('tampered');", encoding="utf-8")
        ok, msg = verify_static_manifest(target_dir=tgt)
        assert ok is False
        assert "Checksum mismatch" in msg

        # 6. Tampering detection: remove a file
        (tgt / "assets" / "style.css").unlink()
        ok, msg = verify_static_manifest(target_dir=tgt)
        assert ok is False
        assert "Missing file" in msg


def test_live_server_static_conforms_to_manifest():
    """If server/static exists and ui/dist exists, verify that server/static manifest is intact."""
    repo_root = Path(__file__).resolve().parent.parent
    server_static = repo_root / "src" / "aether" / "server" / "static"
    if (server_static / "index.html").exists():
        manifest_path = server_static / MANIFEST_FILENAME
        assert manifest_path.exists(), "server/static must contain .build_manifest.json"
        ok, msg = verify_static_manifest(target_dir=server_static)
        assert ok is True, f"server/static drift detected: {msg}"
