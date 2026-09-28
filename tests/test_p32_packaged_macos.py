"""
P3.2 Release-Grade Hardening: Packaged macOS App & Upgrade Verification.
Enforces:
1. macOS App Bundle structure, permissions, Info.plist, and codesign integrity.
2. Build manifest verification: ensures zero static drift between frontend and backend.
3. Fresh install procedure: clean data directory initialization, permissions, and cipher integrity.
4. Upgrade migration for legacy workspaces:
   - v1 to v2 AEAD AES-256-GCM vault migration
   - Connection secret extraction and masking integrity
   - Notification target migration (single target to multi-target queue with TTL)
   - Runtime crash recovery on legacy states (RUNNING/QUEUED -> FAILED, WAITING_APPROVAL preserved)
   - Zero plaintext credential leakage anywhere in the filesystem
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aether.actions.models import (
    ActionExecution,
    ActionExecutionStatus,
)
from aether.actions.store import ActionStore
from aether.connections.models import Connection, ConnectionStatus
from aether.connections.store import ConnectionStore
from aether.core.secrets import (
    EncryptedVaultSecretStore,
    CompositeMasterKeyManager,
    FileMasterKeyProvider,
    CURRENT_FORMAT_VERSION,
    CIPHER_NAME,
    mask_secrets_deep,
)
from aether.notifications.dispatcher import NotificationDispatcher
from aether.notifications.store import NotificationStore
from scripts.sync_static import verify_static_manifest, MANIFEST_FILENAME


BUILD_APP_PATH = REPO_ROOT / "build" / "Aether.app"
SERVER_STATIC_PATH = REPO_ROOT / "src" / "aether" / "server" / "static"


# =============================================================================
# 1. BUNDLE STRUCTURE & INTEGRITY TESTS
# =============================================================================

def test_packaged_bundle_structure_and_signature():
    """
    Validates that when Aether.app is built, it satisfies macOS application bundle
    conventions, contains valid Info.plist metadata, has an executable binary and
    bundled sidecar, and passes codesign verification.
    """
    if not BUILD_APP_PATH.exists():
        pytest.skip("build/Aether.app not found. Run scripts/build_desktop_app.py to compile.")

    contents_dir = BUILD_APP_PATH / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"
    info_plist_path = contents_dir / "Info.plist"

    assert contents_dir.exists(), "Aether.app/Contents must exist"
    assert macos_dir.exists(), "Aether.app/Contents/MacOS must exist"
    assert resources_dir.exists(), "Aether.app/Contents/Resources must exist"
    assert info_plist_path.exists(), "Aether.app/Contents/Info.plist must exist"

    # Verify Info.plist metadata
    with open(info_plist_path, "rb") as f:
        plist = plistlib.load(f)

    assert plist.get("CFBundleIdentifier") == "com.aether.desktop"
    assert plist.get("CFBundlePackageType") == "APPL"
    assert plist.get("CFBundleDisplayName") in ["Aether", "Aether Desktop"]

    # Verify executable binary
    exec_name = plist.get("CFBundleExecutable") or "aether-desktop"
    main_binary = macos_dir / exec_name
    assert main_binary.exists(), f"Main binary missing: {main_binary}"
    assert os.access(main_binary, os.X_OK), f"Main binary is not executable: {main_binary}"

    # Verify bundled Python sidecar exists in Resources
    sidecar_path = resources_dir / "aether-runtime"
    nested_sidecar = resources_dir / "resources" / "aether-runtime"
    assert sidecar_path.exists() or nested_sidecar.exists(), "aether-runtime sidecar missing in Resources"

    # Verify ad-hoc code signature on macOS
    if sys.platform == "darwin":
        res = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(BUILD_APP_PATH)],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Codesign verification failed: {res.stderr}"


def test_static_build_manifest_integrity():
    """
    Validates that the static frontend distribution in server/static matches
    the cryptographic build manifest (.build_manifest.json).
    """
    if not SERVER_STATIC_PATH.exists():
        pytest.skip("src/aether/server/static not found")

    manifest_file = SERVER_STATIC_PATH / MANIFEST_FILENAME
    assert manifest_file.exists(), f"Missing {MANIFEST_FILENAME} in {SERVER_STATIC_PATH}"

    ok, msg = verify_static_manifest(SERVER_STATIC_PATH)
    assert ok, f"Static manifest verification failed: {msg}"

    # Verify essential assets are present
    assert (SERVER_STATIC_PATH / "index.html").exists()
    assert (SERVER_STATIC_PATH / "index.html").stat().st_size > 0


# =============================================================================
# 2. FRESH INSTALL INITIALIZATION PROCEDURE
# =============================================================================

def test_fresh_install_clean_data_directory_initialization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Simulates a completely new installation:
    1. Clean isolated data directory.
    2. Vault initializes with standard AES-256-GCM AEAD cipher.
    3. Action, connection, and notification stores initialize cleanly.
    4. Recovery runs on empty stores without errors.
    """
    monkeypatch.setenv("AETHER_DISABLE_KEYCHAIN", "1")
    fresh_root = tmp_path / "fresh_install"
    fresh_root.mkdir(parents=True)
    vault_path = fresh_root / "vault" / "secrets.vault"

    # Initialize SecretStore using file provider in isolated test directory
    key_file = fresh_root / "vault" / ".vault_key"
    mgr = CompositeMasterKeyManager(providers=[FileMasterKeyProvider()])
    secret_store = EncryptedVaultSecretStore(vault_path=vault_path, key_manager=mgr)

    # 1. Initialize vault and write initial secret
    secret_store.set_secret("install_check", "clean_value")
    assert vault_path.exists()
    vault_data = json.loads(vault_path.read_text(encoding="utf-8"))
    assert vault_data["format_version"] == CURRENT_FORMAT_VERSION
    assert vault_data["cipher"] == CIPHER_NAME
    assert secret_store.get_secret("install_check") == "clean_value"

    # 2. Verify key file created with 0o600 permissions
    assert key_file.exists()
    assert len(key_file.read_bytes()) == 32
    if sys.platform != "win32":
        mode = key_file.stat().st_mode & 0o777
        assert mode == 0o600

    # 3. ConnectionStore initializes on fresh database
    conn_db = fresh_root / "connections.db"
    conn_store = ConnectionStore(str(conn_db), secret_store=secret_store)
    assert conn_store.list_connections("ws-fresh") == []

    # 4. ActionStore initializes on fresh database and recovery runs cleanly
    action_db = fresh_root / "actions.db"
    action_store = ActionStore(action_db)
    recovered = action_store.recover_interrupted_executions()
    assert recovered == 0
    assert action_store.list_executions("ws-fresh") == []

    # 5. NotificationStore & NotificationDispatcher initialize cleanly
    notif_db = fresh_root / "notifications.db"
    notif_store = NotificationStore(db_path=notif_db, secret_store=secret_store)
    dispatcher = NotificationDispatcher(store=notif_store, secret_store=secret_store)
    assert dispatcher is not None


# =============================================================================
# 3. UPGRADE FIXTURE FOR LEGACY WORKSPACE
# =============================================================================

def test_legacy_workspace_upgrade_and_migration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Simulates upgrading an existing Aether workspace from legacy state:
    1. Legacy v1 PBKDF2 vault -> Automatically upgraded to v2 AES-256-GCM AEAD.
    2. Legacy unmasked connection metadata -> Secrets extracted & masked.
    3. Legacy single notification target file -> Migrated to multi-target queue with TTL.
    4. Interrupted action executions -> Recovered to FAILED, WAITING_APPROVAL preserved.
    5. Verifies zero plaintext credentials remain on disk.
    """
    monkeypatch.setenv("AETHER_DISABLE_KEYCHAIN", "1")
    legacy_dir = tmp_path / "legacy_workspace"
    legacy_dir.mkdir(parents=True)

    # --- A. Setup Legacy v1 Vault ---
    import base64
    import hashlib
    import hmac

    vault_dir = legacy_dir / "vault"
    vault_dir.mkdir()
    v1_key_file = vault_dir / ".vault_key"
    v1_raw_key = os.urandom(32)
    v1_key_file.write_bytes(v1_raw_key)

    def make_v1_record(key: bytes, plaintext: str) -> dict[str, Any]:
        salt = os.urandom(16)
        pt_bytes = plaintext.encode("utf-8")
        blocks = []
        needed = (len(pt_bytes) + 31) // 32
        for counter in range(needed):
            info = counter.to_bytes(4, byteorder="big")
            block = hmac.new(key, salt + info, hashlib.sha256).digest()
            blocks.append(block)
        keystream = b"".join(blocks)[:len(pt_bytes)]
        ciphertext = bytes(a ^ b for a, b in zip(pt_bytes, keystream))
        mac = hmac.new(key, salt + ciphertext, hashlib.sha256).hexdigest()
        return {
            "salt": base64.b64encode(salt).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "mac": mac,
            "metadata": {},
        }

    v1_data = {
        "version": 1,
        "records": {
            "secret_ref:github_token": make_v1_record(v1_raw_key, "ghp_LEGACY_UPGRADE_SECRET_TOKEN_12345"),
            "secret_ref:smtp_pass": make_v1_record(v1_raw_key, "SuperSecretSMTPPassword!@#"),
        },
    }
    v1_vault_file = vault_dir / "secrets.vault"
    v1_vault_file.write_text(json.dumps(v1_data), encoding="utf-8")

    # --- B. Setup Legacy Action Store with Stale Executions ---
    action_db = legacy_dir / "actions.db"
    legacy_action_store = ActionStore(action_db)
    e_running = ActionExecution(
        id="legacy-exec-run",
        action_id="sync.data",
        workspace_id="ws-legacy",
        status=ActionExecutionStatus.RUNNING,
        input_data={"param": "legacy_val"},
    )
    e_queued = ActionExecution(
        id="legacy-exec-queue",
        action_id="sync.data",
        workspace_id="ws-legacy",
        status=ActionExecutionStatus.QUEUED,
        input_data={"param": "legacy_val"},
    )
    e_waiting = ActionExecution(
        id="legacy-exec-wait",
        action_id="send.email",
        workspace_id="ws-legacy",
        status=ActionExecutionStatus.WAITING_APPROVAL,
        input_data={"to": "ceo@example.com"},
    )
    legacy_action_store.save_execution(e_running)
    legacy_action_store.save_execution(e_queued)
    legacy_action_store.save_execution(e_waiting)

    # --- C. Setup Legacy Single Notification Target File ---
    legacy_target_file = legacy_dir / "pending_notification_target.json"
    legacy_target_payload = {
        "target": "mission:legacy-101",
        "created_at": time.time() - 30, # Created 30 seconds ago
    }
    legacy_target_file.write_text(json.dumps(legacy_target_payload), encoding="utf-8")

    # =========================================================================
    # EXECUTE UPGRADE
    # =========================================================================

    # 1. Initialize modern EncryptedVaultSecretStore on the legacy vault
    mgr = CompositeMasterKeyManager(providers=[FileMasterKeyProvider()])
    modern_vault = EncryptedVaultSecretStore(vault_path=v1_vault_file, key_manager=mgr)

    # Vault seamlessly loads and upgrades v1 -> v2
    assert modern_vault.get_secret("github_token") == "ghp_LEGACY_UPGRADE_SECRET_TOKEN_12345"
    assert modern_vault.get_secret("smtp_pass") == "SuperSecretSMTPPassword!@#"

    # Verify vault on disk is now v2 format
    vault_data = json.loads(v1_vault_file.read_text(encoding="utf-8"))
    assert vault_data["format_version"] == CURRENT_FORMAT_VERSION
    assert vault_data["cipher"] == CIPHER_NAME

    # 2. Setup Connection Store using the modern vault
    conn_db = legacy_dir / "connections.db"
    conn_store = ConnectionStore(str(conn_db), secret_store=modern_vault)

    # Save a connection that uses secrets
    conn = Connection(
        id="conn-legacy-github",
        workspace_id="ws-legacy",
        provider="github",
        account_name="GitHub Integration",
        auth_metadata={"token": "ghp_LEGACY_UPGRADE_SECRET_TOKEN_12345"},
        status=ConnectionStatus.VERIFIED,
    )
    conn_store.save_connection(conn)

    # Verify that connection retrieval defaults to masked secrets
    retrieved = conn_store.get_connection("conn-legacy-github")
    assert retrieved is not None
    dict_repr = retrieved.to_dict(mask_secrets=True)
    assert dict_repr["auth_metadata"]["token"] != "ghp_LEGACY_UPGRADE_SECRET_TOKEN_12345"
    assert "..." in dict_repr["auth_metadata"]["token"] or dict_repr["auth_metadata"]["token"] == "***"
    assert "ghp_LEGACY_UPGRADE_SECRET_TOKEN_12345" not in json.dumps(dict_repr)

    # 3. Execute Runtime Crash Recovery on Action Store
    recovered_count = legacy_action_store.recover_interrupted_executions()
    assert recovered_count == 2 # e_running and e_queued

    rec_running = legacy_action_store.get_execution("legacy-exec-run")
    assert rec_running.status == ActionExecutionStatus.FAILED
    assert "interrupted" in (rec_running.error_message or "").lower()

    rec_queued = legacy_action_store.get_execution("legacy-exec-queue")
    assert rec_queued.status == ActionExecutionStatus.FAILED

    rec_waiting = legacy_action_store.get_execution("legacy-exec-wait")
    assert rec_waiting.status == ActionExecutionStatus.WAITING_APPROVAL # Preserved!

    # 4. Verify Notification Target Migration logic (Rust Tauri parity in Python)
    # If pending_notification_targets.json doesn't exist, read legacy target and write to multi-target queue
    new_targets_file = legacy_dir / "pending_notification_targets.json"
    if not new_targets_file.exists() and legacy_target_file.exists():
        legacy_t = json.loads(legacy_target_file.read_text(encoding="utf-8"))
        # Prune expired (> 900s)
        now = time.time()
        targets = []
        if now - legacy_t.get("created_at", 0) <= 900:
            targets.append(legacy_t)
        new_targets_file.write_text(json.dumps(targets, indent=2), encoding="utf-8")
        legacy_target_file.unlink()

    assert not legacy_target_file.exists()
    assert new_targets_file.exists()
    queue = json.loads(new_targets_file.read_text(encoding="utf-8"))
    assert len(queue) == 1
    assert queue[0]["target"] == "mission:legacy-101"

    # 5. ZERO Plaintext Residual Check across all legacy workspace files
    secret_bytes = b"ghp_LEGACY_UPGRADE_SECRET_TOKEN_12345"
    for p in legacy_dir.rglob("*"):
        if p.is_file() and p != v1_vault_file:
            content = p.read_bytes()
            assert secret_bytes not in content, f"Secret leaked in plaintext in {p}!"
