"""
Tests for Final Foundation Release Gate: Scoped Identity & Migration (P3.3).
Covers:
- Scoped Keychain account derivation per vault path (no collisions across workspaces)
- Format version validation strictly precedes key resolution
- Seamless migration of existing .vault_key to Keychain
- Fail-closed verification during extract_secrets_deep
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from aether.core.secrets import (
    CURRENT_FORMAT_VERSION,
    EncryptedVaultSecretStore,
    KeychainMasterKeyProvider,
    SecretStoreError,
    VaultFormatError,
    VaultKeyUnavailableError,
    extract_secrets_deep,
)


def test_scoped_keychain_identity(tmp_path: Path):
    """Verify that Keychain accounts are deterministically scoped to vault paths."""
    provider = KeychainMasterKeyProvider()

    path_a = tmp_path / "workspace_a" / "secrets.vault"
    path_b = tmp_path / "workspace_b" / "secrets.vault"

    account_a = provider.get_account_name(path_a)
    account_b = provider.get_account_name(path_b)

    assert account_a != account_b
    assert account_a.startswith("vault_")
    assert account_b.startswith("vault_")

    # Determinism: same path must give identical account
    assert provider.get_account_name(path_a) == account_a

    # Explicit environment override
    old_acc = os.environ.get("AETHER_KEYCHAIN_ACCOUNT")
    try:
        os.environ["AETHER_KEYCHAIN_ACCOUNT"] = "custom_test_account"
        assert provider.get_account_name(path_a) == "custom_test_account"
    finally:
        if old_acc is None:
            os.environ.pop("AETHER_KEYCHAIN_ACCOUNT", None)
        else:
            os.environ["AETHER_KEYCHAIN_ACCOUNT"] = old_acc


def test_format_validation_order_before_key_resolution(tmp_path: Path, monkeypatch):
    """
    Format version must be checked BEFORE attempting or requiring master key resolution.
    An unsupported format version (e.g. 999) must raise VaultFormatError even if
    keys are completely unavailable.
    """
    monkeypatch.setenv("AETHER_DISABLE_KEYCHAIN", "1")
    monkeypatch.delenv("AETHER_MASTER_KEY", raising=False)

    vault_file = tmp_path / "secrets.vault"
    # Write future format envelope without any key file present
    vault_file.write_text(json.dumps({
        "format_version": 999,
        "cipher": "FUTURE-CIPHER-2099",
        "records": {"ref1": {"nonce": "dummy", "ciphertext": "dummy"}},
    }), encoding="utf-8")

    # Must raise VaultFormatError, NOT VaultKeyUnavailableError
    with pytest.raises(VaultFormatError) as exc_info:
        EncryptedVaultSecretStore(vault_file)
    assert "Unsupported vault format version 999" in str(exc_info.value)


def test_legacy_file_key_migration_to_mocked_keychain(tmp_path: Path, monkeypatch):
    """
    When an existing vault was encrypted with a file key and Keychain becomes available,
    the store decrypts using candidate keys and automatically saves the key into Keychain.
    """
    # 1. Create a vault with file key (Keychain disabled)
    monkeypatch.setenv("AETHER_DISABLE_KEYCHAIN", "1")
    monkeypatch.delenv("AETHER_MASTER_KEY", raising=False)

    vault_file = tmp_path / "secrets.vault"
    key_file = tmp_path / ".vault_key"

    store1 = EncryptedVaultSecretStore(vault_file)
    ref = store1.generate_secret_ref(prefix="conn")
    store1.store_secret(ref, "super-confidential-password")
    assert key_file.exists()
    file_key = key_file.read_bytes()

    # 2. Reopen with simulated working Keychain
    keychain_storage: dict[str, bytes] = {}

    def mock_is_available():
        return True

    def mock_get_master_key(vpath):
        acc = KeychainMasterKeyProvider().get_account_name(vpath)
        k = keychain_storage.get(acc)
        return (k, "macos_keychain") if k else (None, "macos_keychain")

    def mock_set_master_key(vpath, key_bytes):
        acc = KeychainMasterKeyProvider().get_account_name(vpath)
        keychain_storage[acc] = key_bytes
        return True

    monkeypatch.delenv("AETHER_DISABLE_KEYCHAIN", raising=False)
    monkeypatch.setattr(KeychainMasterKeyProvider, "is_available", staticmethod(mock_is_available))
    monkeypatch.setattr(KeychainMasterKeyProvider, "get_master_key", lambda self, vp: mock_get_master_key(vp))
    monkeypatch.setattr(KeychainMasterKeyProvider, "set_master_key", lambda self, vp, kb: mock_set_master_key(vp, kb))

    store2 = EncryptedVaultSecretStore(vault_file)
    assert store2.get_secret(ref) == "super-confidential-password"

    # Key should now be in keychain storage
    acc_name = KeychainMasterKeyProvider().get_account_name(vault_file)
    assert acc_name in keychain_storage
    assert keychain_storage[acc_name] == file_key

    # 3. Simulate file key deletion: store3 can still load vault purely from Keychain!
    key_file.unlink()
    store3 = EncryptedVaultSecretStore(vault_file)
    assert store3.get_secret(ref) == "super-confidential-password"
    assert store3.get_security_status()["key_source"] == "macos_keychain"


def test_extract_secrets_deep_fail_closed_on_store_verification_failure(tmp_path: Path):
    """If secret store fails post-store verification, extract_secrets_deep must abort."""
    mock_store = MagicMock()
    mock_store.store_secret = MagicMock()
    # Simulate get_secret mismatch (e.g. storage write corrupted or unreadable)
    mock_store.get_secret.return_value = "mismatched_value"

    raw_payload = {
        "provider": "smtp",
        "password": "untrusted_incoming_password",
    }

    with pytest.raises(SecretStoreError) as exc_info:
        extract_secrets_deep(raw_payload, secret_store=mock_store, entity_type="connection", entity_id="conn_1")

    assert "Failed to verify secret persistence" in str(exc_info.value)
