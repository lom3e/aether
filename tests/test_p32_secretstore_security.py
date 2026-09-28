"""
Tests for Release-Grade SecretStore Security (P3.2).
Covers:
- AES-256-GCM standard AEAD encryption and decryption
- Record-bound Additional Authenticated Data (AAD) tamper detection
- Master Key Management: Keychain, Environment, File (POSIX 0600)
- Explicit Key Loss Detection (VaultKeyUnavailableError)
- Vault Corruption Detection (VaultCorruptedError)
- Format Versioning (Format Version 2, rejection of unknown future versions)
- Atomic Write Protocol and Rollback Safety on persistence failure
- Deep Nested Secret Extraction, Resolution, and Masking
- Truthful Security Status reporting
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import stat
import sys
import uuid
import pytest

from aether.core.secrets import (
    CURRENT_FORMAT_VERSION,
    CIPHER_NAME,
    EncryptedVaultSecretStore,
    MemorySecretStore,
    SecretStoreError,
    VaultCorruptedError,
    VaultKeyUnavailableError,
    VaultFormatError,
    extract_secrets_deep,
    resolve_secrets_deep,
    mask_secrets_deep,
    is_secret_key,
    is_secret_ref,
    FileMasterKeyProvider,
    EnvironmentMasterKeyProvider,
    KeychainMasterKeyProvider,
)


def test_aes_gcm_encryption_and_aad_integrity(tmp_path: Path):
    """Verify that records are encrypted with AES-256-GCM and bound to their secret_ref via AAD."""
    vault_file = tmp_path / "secrets.vault"
    store = EncryptedVaultSecretStore(vault_file)

    ref = store.generate_secret_ref(prefix="test")
    plain = "super-sensitive-api-token-12345"
    store.store_secret(ref, plain, entity_type="test", entity_id="item_1")

    # 1. Verify retrieval
    assert store.get_secret(ref) == plain

    # 2. Inspect raw vault file on disk
    raw_data = json.loads(vault_file.read_text(encoding="utf-8"))
    assert raw_data["format_version"] == 2
    assert raw_data["cipher"] == "AES-256-GCM"
    assert ref in raw_data["records"]

    rec = raw_data["records"][ref]
    assert "nonce" in rec
    assert "ciphertext" in rec
    # Ensure plaintext is not present in raw file
    assert plain not in vault_file.read_text()

    # 3. Tamper with ciphertext -> should raise VaultCorruptedError
    tampered_bytes = bytearray(base64.b64decode(rec["ciphertext"]))
    tampered_bytes[0] ^= 0xFF
    raw_data["records"][ref]["ciphertext"] = base64.b64encode(tampered_bytes).decode("ascii")
    vault_file.write_text(json.dumps(raw_data), encoding="utf-8")

    # Loading corrupted vault must raise VaultCorruptedError
    with pytest.raises(VaultCorruptedError):
        EncryptedVaultSecretStore(vault_file)


def test_key_loss_detection_raises_explicit_error(tmp_path: Path):
    """
    If a vault exists on disk but its master key is lost, SecretStore MUST raise
    VaultKeyUnavailableError and NOT generate a new master key or pretend the vault is empty.
    """
    vault_file = tmp_path / "secrets.vault"
    key_file = tmp_path / ".vault_key"

    # Disable keychain to isolate file key provider
    old_disable = os.environ.get("AETHER_DISABLE_KEYCHAIN")
    os.environ["AETHER_DISABLE_KEYCHAIN"] = "1"
    try:
        store = EncryptedVaultSecretStore(vault_file)
        ref = store.generate_secret_ref(prefix="keytest")
        store.store_secret(ref, "critical-secret-data")
        assert vault_file.exists()
        assert key_file.exists()

        # Simulate key loss: delete master key file
        key_file.unlink()

        # Reopening the vault MUST fail with VaultKeyUnavailableError
        with pytest.raises(VaultKeyUnavailableError) as exc_info:
            EncryptedVaultSecretStore(vault_file)
        assert "Master key is unavailable" in str(exc_info.value)
    finally:
        if old_disable is not None:
            os.environ["AETHER_DISABLE_KEYCHAIN"] = old_disable
        else:
            os.environ.pop("AETHER_DISABLE_KEYCHAIN", None)


def test_unsupported_future_format_version_rejected(tmp_path: Path):
    """A vault file with a higher unsupported format version must fail-closed."""
    vault_file = tmp_path / "future_vault.json"
    future_payload = {
        "format_version": 999,
        "cipher": "QUANTUM-RESISTANT-AEAD",
        "key_source": "hardware_token",
        "records": {},
    }
    vault_file.write_text(json.dumps(future_payload), encoding="utf-8")

    with pytest.raises(VaultFormatError) as exc:
        EncryptedVaultSecretStore(vault_file)
    assert "Unsupported vault format version 999" in str(exc.value)


def test_atomic_write_rollback_safety(tmp_path: Path, monkeypatch):
    """
    If atomic persistence fails during store_secret, the in-memory cache must rollback
    and not consider the secret persisted.
    """
    vault_file = tmp_path / "atomic_vault.json"
    store = EncryptedVaultSecretStore(vault_file)

    ref = store.generate_secret_ref(prefix="rollback")
    store.store_secret(ref, "initial-value")
    assert store.get_secret(ref) == "initial-value"

    # Monkeypatch atomic replace to simulate disk write failure
    def failing_replace(self, target):
        raise OSError("Simulated disk I/O error or full disk")

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(SecretStoreError):
        store.store_secret(ref, "new-unwritten-value")

    # In-memory cache must retain the old value, not the unwritten new value!
    assert store.get_secret(ref) == "initial-value"


def test_file_master_key_provider_posix_permissions(tmp_path: Path):
    """Verify that file master key provider sets POSIX 0600 on key and 0700 on dir."""
    vault_path = tmp_path / "sub" / "secrets.vault"
    provider = FileMasterKeyProvider()

    key, src = provider.get_or_create_master_key(vault_path)
    assert len(key) == 32
    assert src == "file"

    key_file = vault_path.parent / ".vault_key"
    assert key_file.exists()

    if sys.platform != "win32":
        file_mode = stat.S_IMODE(key_file.stat().st_mode)
        assert file_mode == 0o600
        dir_mode = stat.S_IMODE(vault_path.parent.stat().st_mode)
        assert dir_mode == 0o700


def test_environment_master_key_provider(tmp_path: Path, monkeypatch):
    """Verify master key injection via AETHER_MASTER_KEY environment variable."""
    vault_path = tmp_path / "env_vault.vault"
    test_key = "a" * 64  # 32 bytes hex
    monkeypatch.setenv("AETHER_MASTER_KEY", test_key)

    provider = EnvironmentMasterKeyProvider()
    key, src = provider.get_master_key(vault_path)
    assert src == "environment"
    assert key == bytes.fromhex(test_key)


def test_deep_nested_secret_extraction_and_resolution():
    """Verify that nested dicts and lists are recursively extracted and resolved."""
    store = MemorySecretStore()

    raw_payload = {
        "provider": "google_calendar",
        "auth": {
            "client_id": "public-client-id-123.apps.googleusercontent.com",
            "client_secret": "GOCSPX-very-secret-client-token",
            "oauth_tokens": {
                "access_token": "ya29.sensitive-access-token-xyz",
                "refresh_token": "1//04sensitive-refresh-token-abc",
                "scopes": ["https://www.googleapis.com/auth/calendar"],
            },
        },
        "channels": [
            {
                "type": "email",
                "smtp": {
                    "host": "smtp.gmail.com",
                    "smtp_password": "my-smtp-app-password",
                },
            }
        ],
        "non_sensitive_list": ["apple", "banana"],
    }

    # 1. Extract
    sanitized, count = extract_secrets_deep(raw_payload, store, "connection", "conn_test_nested")
    assert count == 4  # client_secret, access_token, refresh_token, smtp_password

    # Plaintext credentials must be replaced by secret_refs
    assert sanitized["auth"]["client_id"] == "public-client-id-123.apps.googleusercontent.com"
    assert is_secret_ref(sanitized["auth"]["client_secret"])
    assert is_secret_ref(sanitized["auth"]["oauth_tokens"]["access_token"])
    assert is_secret_ref(sanitized["auth"]["oauth_tokens"]["refresh_token"])
    assert is_secret_ref(sanitized["channels"][0]["smtp"]["smtp_password"])
    assert sanitized["channels"][0]["smtp"]["host"] == "smtp.gmail.com"

    # 2. Resolve
    resolved = resolve_secrets_deep(sanitized, store)
    assert resolved == raw_payload

    # 3. Mask
    masked = mask_secrets_deep(sanitized)
    assert masked["auth"]["client_id"] == "public-client-id-123.apps.googleusercontent.com"
    assert "GOCSPX" not in str(masked)
    assert "ya29" not in str(masked)
    assert "my-smtp-app-password" not in str(masked)


def test_truthful_security_status_reporting(tmp_path: Path):
    """Verify that get_security_status reports accurate cipher and key source without false claims."""
    vault_file = tmp_path / "status_vault.vault"
    store = EncryptedVaultSecretStore(vault_file)
    status = store.get_security_status()

    assert status["cipher"] == "AES-256-GCM"
    assert status["format_version"] == 2
    assert status["status"] in ("healthy", "uninitialized")
    assert status["key_source"] in ("macos_keychain", "file", "environment", "memory", "uninitialized")
    assert "vault_path" in status

    # Once a secret is stored, key_source must be initialized to a real provider
    store.store_secret("secret_ref:status_test", "status_secret")
    status_written = store.get_security_status()
    assert status_written["status"] == "healthy"
    assert status_written["key_source"] in ("macos_keychain", "file", "environment", "memory")
