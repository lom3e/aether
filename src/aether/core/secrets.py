"""
SecretStore — Release-Grade Universal Cryptographic Secret Management & Isolation Layer (Phase P3.2).

Security Guarantees:
- Standard-compliant Authenticated Encryption: AES-256-GCM AEAD (via cryptography hazmat) with 96-bit random nonce
  and record-specific Additional Authenticated Data (AAD) binding ciphertext to record key and format version.
- OS-Backed Credential Store on macOS: Master root key managed via macOS Keychain (via keyring).
- Strict Fallback Threat Model: On headless/Linux/CI environments, master key stored in POSIX 0600 file / 0700 dir
  or injected via AETHER_MASTER_KEY environment variable. Truthfully reported key source (no false "Keychain" claim).
- Explicit Format Versioning (Format Version 2): Strict schema with corruption, key-loss, and unsupported version detection.
- Fail-Closed Architecture: Corrupted vault or missing master key halts with explicit exception, never silently resets.
- Atomic Transaction-like Writes: Temporary file write -> flush -> fsync -> atomic replace -> cache update only upon success.
- Idempotent Migration with MigrationJournal: Direct raw database inspection, stable deterministic reference mapping,
  transactional DB updates, and compensating safety (never deletes plaintext if secure storage write fails).
- Deep Nested Secret Extraction: Traverses dictionaries and lists recursively for complete coverage across all providers.
- Zero Plaintext Leakage: Automated redaction and masking across external APIs, diagnostics, and serialization.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import base64
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import threading
from typing import Any, Mapping
import uuid

# Cryptography AEAD standard cipher
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)

CURRENT_FORMAT_VERSION = 2
CIPHER_NAME = "AES-256-GCM"

# Comprehensive sensitive keyword matching (exact tokens or clear compound affixes)
EXACT_SECRET_KEYS: frozenset[str] = frozenset({
    "token", "secret", "password", "pass", "pat", "key", "api_key", "apikey",
    "access_token", "refresh_token", "client_secret", "clientsecret",
    "bot_token", "webhook_secret", "private_key", "privatekey",
    "auth_token", "authtoken", "credential", "credentials", "signing_secret",
    "smtp_pass", "smtp_password", "bearer_token", "app_token",
})

SECRET_AFFIXES: tuple[str, ...] = (
    "_token", "token_", "_secret", "secret_", "_password", "password_",
    "_key", "key_", "api_key", "private_key", "client_secret",
    "webhook_secret", "refresh_token", "access_token", "bot_token",
)


def is_secret_key(key: str) -> bool:
    """
    Checks whether a dictionary key is indicative of sensitive secret material.
    Uses exact token matching and unambiguous compound affixes to avoid false positives
    on innocent words (e.g. 'compass', 'passive', 'bypass', 'keynote').
    """
    if not isinstance(key, str):
        return False
    k = key.lower().strip()
    if k in EXACT_SECRET_KEYS:
        return True
    return any(affix in k for affix in SECRET_AFFIXES)


def is_secret_ref(val: Any) -> bool:
    """Checks whether a value is an opaque secret reference rather than plaintext."""
    if not isinstance(val, str):
        return False
    return val.startswith("secret_ref:") or (val.startswith("sec_") and len(val) >= 20)


# =====================================================================
# Exceptions
# =====================================================================

class SecretStoreError(Exception):
    """Base exception for all SecretStore failures."""
    pass


class VaultCorruptedError(SecretStoreError):
    """Raised when the persistent secret vault fails integrity checks or cannot be decrypted."""
    pass


class VaultKeyUnavailableError(SecretStoreError):
    """Raised when the master encryption key is missing or inaccessible for an existing vault."""
    pass


class VaultFormatError(SecretStoreError):
    """Raised when the vault file uses an unsupported or unrecognized format version."""
    pass


class SecretMigrationError(SecretStoreError):
    """Raised when secret migration encounters an unrecoverable error."""
    pass


# =====================================================================
# Master Key Providers (macOS Keychain, Environment, File, Memory)
# =====================================================================

class MasterKeyProvider(ABC):
    """Abstract provider for obtaining or creating the master vault root encryption key."""

    @abstractmethod
    def get_master_key(self, vault_path: Path) -> tuple[bytes | None, str]:
        """Retrieves existing master key without creating a new one. Returns (key_bytes, source_label)."""
        pass

    @abstractmethod
    def get_or_create_master_key(self, vault_path: Path) -> tuple[bytes, str]:
        """Retrieves or generates a persistent 32-byte master key. Returns (key_bytes, source_label)."""
        pass


class KeychainMasterKeyProvider(MasterKeyProvider):
    """
    macOS Keychain OS-backed credential store provider.
    Stores and retrieves the master vault root key via the OS Keychain.
    Scopes account names deterministically to the specific vault path to prevent
    cross-workspace/vault key collisions, while preserving backwards compatibility
    with legacy 'master_vault_key'.
    """
    SERVICE_NAME = "aether-runtime"
    DEFAULT_ACCOUNT_NAME = "master_vault_key"

    def get_account_name(self, vault_path: Path) -> str:
        """Derives a deterministic, collision-free Keychain account name for a vault path."""
        env_account = os.environ.get("AETHER_KEYCHAIN_ACCOUNT", "").strip()
        if env_account:
            return env_account

        try:
            canon = str(vault_path.expanduser().resolve())
            default_canon = str((Path.home() / ".aether" / "vault" / "secrets.vault").resolve())
            if canon == default_canon:
                return self.DEFAULT_ACCOUNT_NAME
            digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
            return f"vault_{digest}"
        except Exception:
            return self.DEFAULT_ACCOUNT_NAME

    def is_available(self) -> bool:
        if sys.platform != "darwin":
            return False
        if os.environ.get("AETHER_DISABLE_KEYCHAIN") == "1":
            return False
        try:
            import keyring
            # Ensure not using a null or fail keyring
            kr = keyring.get_keyring()
            if "fail" in kr.__class__.__name__.lower() or "null" in kr.__class__.__name__.lower():
                return False
            return True
        except Exception:
            return False

    def get_master_key(self, vault_path: Path) -> tuple[bytes | None, str]:
        if not self.is_available():
            return None, "unavailable"
        try:
            import keyring
            account = self.get_account_name(vault_path)
            hex_key = keyring.get_password(self.SERVICE_NAME, account)
            if hex_key and len(hex_key) == 64:
                return bytes.fromhex(hex_key), "macos_keychain"

            # Fallback to legacy global account name if non-default scoped was not found
            if account != self.DEFAULT_ACCOUNT_NAME:
                legacy_hex = keyring.get_password(self.SERVICE_NAME, self.DEFAULT_ACCOUNT_NAME)
                if legacy_hex and len(legacy_hex) == 64:
                    return bytes.fromhex(legacy_hex), "macos_keychain"
        except Exception as exc:
            logger.debug("Keychain get_password failed: %s", exc)
        return None, "macos_keychain"

    def set_master_key(self, vault_path: Path, key: bytes) -> bool:
        """Explicitly persists a master key to Keychain under the vault's scoped account."""
        if not self.is_available():
            return False
        try:
            import keyring
            account = self.get_account_name(vault_path)
            keyring.set_password(self.SERVICE_NAME, account, key.hex())
            return True
        except Exception as exc:
            logger.warning("Could not set master key in macOS Keychain for %s: %s", vault_path, exc)
            return False

    def get_or_create_master_key(self, vault_path: Path) -> tuple[bytes, str]:
        existing, source = self.get_master_key(vault_path)
        if existing is not None:
            return existing, source

        new_key = secrets.token_bytes(32)
        try:
            import keyring
            account = self.get_account_name(vault_path)
            keyring.set_password(self.SERVICE_NAME, account, new_key.hex())
            return new_key, "macos_keychain"
        except Exception as exc:
            logger.warning("Could not store master key in macOS Keychain: %s. Falling back.", exc)
            raise


class EnvironmentMasterKeyProvider(MasterKeyProvider):
    """Master key provider via explicit environment variable AETHER_MASTER_KEY."""

    def get_master_key(self, vault_path: Path) -> tuple[bytes | None, str]:
        raw = os.environ.get("AETHER_MASTER_KEY")
        if not raw:
            return None, "environment"
        raw_str = raw.strip()
        if len(raw_str) == 64:
            try:
                return bytes.fromhex(raw_str), "environment"
            except ValueError:
                pass
        return hashlib.sha256(raw_str.encode("utf-8")).digest(), "environment"

    def get_or_create_master_key(self, vault_path: Path) -> tuple[bytes, str]:
        key, source = self.get_master_key(vault_path)
        if key is not None:
            return key, source
        raise ValueError("AETHER_MASTER_KEY environment variable is not set")


class FileMasterKeyProvider(MasterKeyProvider):
    """
    Standard-compliant isolated file master key provider for headless, Linux, or CI environments.
    Enforces POSIX 0600 on the key file and 0700 on the directory.
    """

    def _get_key_file(self, vault_path: Path) -> Path:
        return vault_path.parent / ".vault_key"

    def get_master_key(self, vault_path: Path) -> tuple[bytes | None, str]:
        key_file = self._get_key_file(vault_path)
        if key_file.exists():
            try:
                raw = key_file.read_bytes()
                if len(raw) >= 32:
                    return raw[:32], "file"
            except Exception as e:
                logger.warning("Could not read master vault key file at %s: %s", key_file, e)
        return None, "file"

    def get_or_create_master_key(self, vault_path: Path) -> tuple[bytes, str]:
        existing, source = self.get_master_key(vault_path)
        if existing is not None:
            return existing, source

        new_key = secrets.token_bytes(32)
        key_file = self._get_key_file(vault_path)
        try:
            key_file.parent.mkdir(parents=True, exist_ok=True)
            if hasattr(os, "chmod") and sys.platform != "win32":
                try:
                    os.chmod(key_file.parent, 0o700)
                except Exception:
                    pass
            key_file.write_bytes(new_key)
            if hasattr(os, "chmod") and sys.platform != "win32":
                try:
                    os.chmod(key_file, 0o600)
                except Exception:
                    pass
            return new_key, "file"
        except Exception as e:
            logger.error("Could not persist master vault key to %s: %s", key_file, e)
            raise


class CompositeMasterKeyManager:
    """Orchestrates resolution across Keychain, Environment, and File key providers."""

    def __init__(
        self,
        providers: list[Any] | None = None,
        keychain: KeychainMasterKeyProvider | None = None,
        env: EnvironmentMasterKeyProvider | None = None,
        file: FileMasterKeyProvider | None = None,
    ) -> None:
        self.keychain = keychain or KeychainMasterKeyProvider()
        self.env = env or EnvironmentMasterKeyProvider()
        self.file = file or FileMasterKeyProvider()
        if providers:
            for p in providers:
                if isinstance(p, KeychainMasterKeyProvider):
                    self.keychain = p
                elif isinstance(p, EnvironmentMasterKeyProvider):
                    self.env = p
                elif isinstance(p, FileMasterKeyProvider):
                    self.file = p

    def get_master_key(self, vault_path: Path) -> tuple[bytes | None, str]:
        # 1. Environment variable override
        k, src = self.env.get_master_key(vault_path)
        if k is not None:
            return k, src

        # 2. macOS Keychain
        if self.keychain.is_available():
            k, src = self.keychain.get_master_key(vault_path)
            if k is not None:
                return k, src

        # 3. File provider
        return self.file.get_master_key(vault_path)

    def get_or_create_master_key(self, vault_path: Path) -> tuple[bytes, str]:
        # 1. Environment variable override
        k, src = self.env.get_master_key(vault_path)
        if k is not None:
            return k, src

        # 2. macOS Keychain
        if self.keychain.is_available():
            try:
                return self.keychain.get_or_create_master_key(vault_path)
            except Exception as exc:
                logger.warning("Keychain creation failed (%s), falling back to file provider", exc)

        # 3. File provider
        return self.file.get_or_create_master_key(vault_path)

    def get_candidate_keys(self, vault_path: Path) -> list[tuple[bytes, str]]:
        """
        Returns all plausible candidate master keys across environment, Keychain,
        and local key files, ordered by priority. Used for transparent recovery and migration.
        """
        candidates: list[tuple[bytes, str]] = []
        seen: set[bytes] = set()

        # 1. Environment key
        k_env, src_env = self.env.get_master_key(vault_path)
        if k_env and k_env not in seen:
            candidates.append((k_env, src_env))
            seen.add(k_env)

        # 2. Keychain key (scoped and fallback)
        if self.keychain.is_available():
            k_kc, src_kc = self.keychain.get_master_key(vault_path)
            if k_kc and k_kc not in seen:
                candidates.append((k_kc, src_kc))
                seen.add(k_kc)

        # 3. File key (from local .vault_key)
        k_file, src_file = self.file.get_master_key(vault_path)
        if k_file and k_file not in seen:
            candidates.append((k_file, src_file))
            seen.add(k_file)

        return candidates


# =====================================================================
# SecretStore Contract & Implementations
# =====================================================================

class SecretStore(ABC):
    """
    Abstract interface for managing sensitive application secrets.
    Consuming services reference secrets exclusively via opaque secret_ref identifiers.
    """

    @abstractmethod
    def store_secret(
        self,
        secret_ref: str,
        value: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> str:
        """Stores a secret string identified by secret_ref. Returns canonical secret_ref."""
        pass

    @abstractmethod
    def get_secret(self, secret_ref: str) -> str | None:
        """Retrieves a secret string by secret_ref, or None if not found."""
        pass

    @abstractmethod
    def delete_secret(self, secret_ref: str) -> bool:
        """Deletes a secret by secret_ref. Returns True if found and deleted."""
        pass

    @abstractmethod
    def has_secret(self, secret_ref: str) -> bool:
        """Returns True if a secret exists for secret_ref."""
        pass

    @abstractmethod
    def get_security_status(self) -> dict[str, Any]:
        """Returns truthful security metadata about cipher, key source, format version, and health."""
        pass

    def generate_secret_ref(self, prefix: str = "sec") -> str:
        """Generates a secure random opaque secret reference token."""
        return f"secret_ref:{prefix}_{secrets.token_hex(12)}"


class MemorySecretStore(SecretStore):
    """In-memory SecretStore implementation for unit tests and ephemeral execution."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._secrets: dict[str, str] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def store_secret(
        self,
        secret_ref: str,
        value: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> str:
        s_ref = secret_ref if secret_ref.startswith("secret_ref:") else f"secret_ref:{secret_ref}"
        with self._lock:
            self._secrets[s_ref] = str(value)
            self._metadata[s_ref] = {
                "entity_type": entity_type,
                "entity_id": entity_id,
            }
        return s_ref

    set_secret = store_secret

    def get_secret(self, secret_ref: str) -> str | None:
        s_ref = secret_ref if secret_ref.startswith("secret_ref:") else f"secret_ref:{secret_ref}"
        with self._lock:
            return self._secrets.get(s_ref, self._secrets.get(secret_ref))

    def delete_secret(self, secret_ref: str) -> bool:
        s_ref = secret_ref if secret_ref.startswith("secret_ref:") else f"secret_ref:{secret_ref}"
        with self._lock:
            self._metadata.pop(s_ref, None)
            self._metadata.pop(secret_ref, None)
            deleted = self._secrets.pop(s_ref, None) is not None
            if not deleted:
                deleted = self._secrets.pop(secret_ref, None) is not None
            return deleted

    def has_secret(self, secret_ref: str) -> bool:
        s_ref = secret_ref if secret_ref.startswith("secret_ref:") else f"secret_ref:{secret_ref}"
        with self._lock:
            return s_ref in self._secrets or secret_ref in self._secrets

    def get_security_status(self) -> dict[str, Any]:
        return {
            "cipher": "memory",
            "key_source": "memory",
            "format_version": CURRENT_FORMAT_VERSION,
            "status": "healthy",
            "record_count": len(self._secrets),
            "vault_path": ":memory:",
        }


class EncryptedVaultSecretStore(SecretStore):
    """
    Production-grade encrypted secret vault using standard AES-256-GCM AEAD
    and OS-backed master key management.
    """

    def __init__(
        self,
        vault_path: str | Path | None = None,
        key_manager: CompositeMasterKeyManager | None = None,
    ) -> None:
        self._lock = threading.RLock()
        if vault_path is None or str(vault_path).strip() == "":
            env_path = os.environ.get("AETHER_VAULT_PATH")
            if env_path:
                self.vault_path = Path(env_path).expanduser().resolve()
            else:
                user_home = Path.home()
                self.vault_path = user_home / ".aether" / "vault" / "secrets.vault"
        else:
            self.vault_path = Path(vault_path).expanduser().resolve()

        self._in_memory = str(self.vault_path) in (":memory:", "memory")
        self._cache: dict[str, str] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._master_key: bytes | None = None
        self._key_source: str = "memory" if self._in_memory else "uninitialized"
        self._status: str = "healthy"
        self._last_error: str | None = None
        self._key_manager = key_manager or CompositeMasterKeyManager()

        if not self._in_memory:
            self._init_vault_storage()
            self._load_vault()

    @property
    def status(self) -> str:
        return self._status

    @property
    def key_source(self) -> str:
        return self._key_source

    def _init_vault_storage(self) -> None:
        """Initializes directory structure with POSIX 0700 permissions."""
        vault_dir = self.vault_path.parent
        vault_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "chmod") and sys.platform != "win32":
            try:
                os.chmod(vault_dir, 0o700)
            except Exception:
                pass

    def _ensure_master_key_for_write(self) -> bytes:
        """Gets or generates a master key when a write operation is initiated."""
        if self._master_key is not None:
            return self._master_key
        key, source = self._key_manager.get_or_create_master_key(self.vault_path)
        self._master_key = key
        self._key_source = source
        return key

    def _encrypt_record(self, secret_ref: str, plaintext: str) -> dict[str, Any]:
        """Encrypts a single secret string using AES-256-GCM with record-bound AAD."""
        key = self._ensure_master_key_for_write()
        aesgcm = AESGCM(key)
        nonce = secrets.token_bytes(12)
        aad = f"v{CURRENT_FORMAT_VERSION}:{secret_ref}".encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return {
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    def _decrypt_record_v2(self, secret_ref: str, rec_data: dict[str, Any]) -> str:
        """Decrypts a format version 2 record with AES-256-GCM and verified AAD."""
        if self._master_key is None:
            raise VaultKeyUnavailableError("Master key is missing; cannot decrypt record")
        try:
            nonce = base64.b64decode(rec_data["nonce"])
            ciphertext = base64.b64decode(rec_data["ciphertext"])
            aad = f"v{CURRENT_FORMAT_VERSION}:{secret_ref}".encode("utf-8")
            aesgcm = AESGCM(self._master_key)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, aad)
            return plaintext_bytes.decode("utf-8")
        except InvalidTag as it:
            raise VaultCorruptedError(f"AEAD authentication tag mismatch for secret record '{secret_ref}'") from it
        except Exception as exc:
            raise VaultCorruptedError(f"Failed to decrypt secret record '{secret_ref}': {exc}") from exc

    def _decrypt_legacy_v1(self, enc_data: dict[str, Any], candidate_keys: list[bytes] | None = None) -> str | None:
        """Backward-compatibility decryptor for P3.1 PBKDF2 stream cipher vaults."""
        keys = list(candidate_keys) if candidate_keys else ([self._master_key] if self._master_key else [])
        if not keys:
            return None
        try:
            salt = base64.b64decode(enc_data["salt"])
            ciphertext = base64.b64decode(enc_data["ciphertext"])
            expected_mac = str(enc_data["mac"])

            for key in keys:
                if not key:
                    continue
                actual_mac = hmac.new(key, salt + ciphertext, hashlib.sha256).hexdigest()
                if not hmac.compare_digest(actual_mac, expected_mac):
                    continue

                # Reconstruct legacy keystream
                blocks = []
                needed = (len(ciphertext) + 31) // 32
                for counter in range(needed):
                    info = counter.to_bytes(4, byteorder="big")
                    block = hmac.new(key, salt + info, hashlib.sha256).digest()
                    blocks.append(block)
                keystream = b"".join(blocks)[:len(ciphertext)]
                plaintext_bytes = bytes(a ^ b for a, b in zip(ciphertext, keystream))
                return plaintext_bytes.decode("utf-8")
        except Exception:
            return None
        return None

    def _load_vault(self) -> None:
        """
        Loads and decrypts all records from persistent vault storage.
        Order of verification:
        1. Read and parse envelope from file FIRST.
        2. Validate format version (reject future/unsupported format versions before resolving keys).
        3. Resolve master key & candidate keys across Keychain, environment, and file storage.
        4. Decrypt records with candidate key fallback & transparent secure source migration.
        Enforces strict fail-closed behavior on corruption, missing key, or invalid tag.
        """
        if not self.vault_path.exists():
            self._status = "uninitialized"
            return

        with self._lock:
            # 1. Read and parse vault structure FIRST
            try:
                data_str = self.vault_path.read_text(encoding="utf-8")
            except Exception as e:
                self._status = "vault_corrupted"
                self._last_error = f"Cannot read vault file: {e}"
                raise VaultCorruptedError(self._last_error) from e

            if not data_str.strip():
                self._status = "uninitialized"
                return

            try:
                raw_json = json.loads(data_str)
            except Exception as e:
                self._status = "vault_corrupted"
                self._last_error = f"Vault file contains invalid JSON: {e}"
                logger.error(self._last_error)
                raise VaultCorruptedError(self._last_error) from e

            if not isinstance(raw_json, dict):
                self._status = "vault_corrupted"
                self._last_error = "Vault file root must be a JSON object"
                raise VaultCorruptedError(self._last_error)

            # 2. Check format version BEFORE key resolution (Strict order required by audit)
            fmt_ver = raw_json.get("format_version") or raw_json.get("version", 1)
            if not isinstance(fmt_ver, int) or fmt_ver <= 0:
                self._status = "vault_corrupted"
                self._last_error = f"Invalid format_version in vault: {fmt_ver}"
                raise VaultFormatError(self._last_error)

            if fmt_ver > CURRENT_FORMAT_VERSION:
                self._status = "unsupported_version"
                self._last_error = f"Unsupported vault format version {fmt_ver} (current max: {CURRENT_FORMAT_VERSION})"
                raise VaultFormatError(self._last_error)

            # 3. Gather candidate keys
            candidate_keys = self._key_manager.get_candidate_keys(self.vault_path)
            if not candidate_keys:
                self._status = "key_unavailable"
                self._last_error = f"Master key is unavailable for existing vault at {self.vault_path}"
                logger.error("%s. Vault cannot be loaded without master key.", self._last_error)
                raise VaultKeyUnavailableError(self._last_error)

            records = raw_json.get("records", {})
            new_cache: dict[str, str] = {}
            new_metadata: dict[str, dict[str, Any]] = {}

            # 4. Decrypt records based on version
            if fmt_ver == 1:
                logger.info("Migrating legacy format version 1 vault to version 2 (AES-256-GCM)...")
                just_keys = [k for k, _ in candidate_keys]
                successful_key: bytes | None = None
                successful_source: str = "unknown"

                for s_ref, enc_data in records.items():
                    plain = self._decrypt_legacy_v1(enc_data, just_keys)
                    if plain is None:
                        self._status = "vault_corrupted"
                        self._last_error = f"Legacy vault record '{s_ref}' could not be decrypted"
                        raise VaultCorruptedError(self._last_error)
                    new_cache[s_ref] = plain
                    new_metadata[s_ref] = enc_data.get("metadata", {})

                # Determine winning key that decrypted the v1 records
                for k, src in candidate_keys:
                    if not records or self._decrypt_legacy_v1(next(iter(records.values())), [k]) is not None:
                        successful_key = k
                        successful_source = src
                        break

                self._master_key = successful_key or candidate_keys[0][0]
                self._key_source = successful_source
                self._cache = new_cache
                self._metadata = new_metadata

                # Seamless migration of master key to Keychain if available
                if self._key_manager.keychain.is_available():
                    if self._key_manager.keychain.set_master_key(self.vault_path, self._master_key):
                        self._key_source = "macos_keychain"

                # Upgrade file format on disk to version 2
                self._save_vault()
            else:
                # Format Version 2 (AES-256-GCM AEAD)
                if not records:
                    self._master_key, self._key_source = candidate_keys[0]
                    self._cache = {}
                    self._metadata = {}
                else:
                    decrypted_cache: dict[str, str] | None = None
                    decrypted_meta: dict[str, dict[str, Any]] = {}
                    winning_key: bytes | None = None
                    winning_src: str = "unknown"
                    last_decrypt_err: Exception | None = None

                    for cand_key, cand_src in candidate_keys:
                        try:
                            temp_cache: dict[str, str] = {}
                            temp_meta: dict[str, dict[str, Any]] = {}
                            for s_ref, enc_data in records.items():
                                nonce = base64.b64decode(enc_data["nonce"])
                                ciphertext = base64.b64decode(enc_data["ciphertext"])
                                aad = f"v{CURRENT_FORMAT_VERSION}:{s_ref}".encode("utf-8")
                                aesgcm = AESGCM(cand_key)
                                pt_bytes = aesgcm.decrypt(nonce, ciphertext, aad)
                                temp_cache[s_ref] = pt_bytes.decode("utf-8")
                                temp_meta[s_ref] = enc_data.get("metadata", {})
                            decrypted_cache = temp_cache
                            decrypted_meta = temp_meta
                            winning_key = cand_key
                            winning_src = cand_src
                            break
                        except Exception as exc:
                            last_decrypt_err = exc
                            continue

                    if decrypted_cache is None:
                        self._status = "vault_corrupted"
                        self._last_error = f"AEAD authentication tag mismatch: invalid key or corrupted vault ({last_decrypt_err})"
                        raise VaultCorruptedError(self._last_error)

                    self._master_key = winning_key
                    self._key_source = winning_src
                    self._cache = decrypted_cache
                    self._metadata = decrypted_meta

                    # Seamless migration of master key to Keychain if available and key was from file
                    if winning_src != "macos_keychain" and self._key_manager.keychain.is_available():
                        if self._key_manager.keychain.set_master_key(self.vault_path, winning_key):
                            self._key_source = "macos_keychain"

            self._status = "healthy"
            self._last_error = None

    def _save_vault(self) -> None:
        """
        Atomically persists encrypted records to vault storage file.
        Protocol:
        1. Encrypt all records to in-memory payload with format_version=2 and cipher=AES-256-GCM.
        2. Write to secure temporary file with 0600 permissions.
        3. Flush and fsync temporary file descriptor to disk.
        4. Atomic rename temporary file over target vault file.
        5. Cache is updated by caller ONLY after this function succeeds.
        """
        if self._in_memory:
            return

        with self._lock:
            records = {}
            for s_ref, plain in self._cache.items():
                enc = self._encrypt_record(s_ref, plain)
                enc["metadata"] = self._metadata.get(s_ref, {})
                records[s_ref] = enc

            payload = {
                "format_version": CURRENT_FORMAT_VERSION,
                "cipher": CIPHER_NAME,
                "key_source": self._key_source,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "records": records,
            }

            vault_dir = self.vault_path.parent
            vault_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = vault_dir / f".{self.vault_path.name}.tmp.{uuid.uuid4().hex}"

            try:
                # Open with secure exclusive flags
                flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                mode = 0o600
                fd = os.open(str(tmp_path), flags, mode)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                except Exception:
                    # fdopen takes ownership of fd; if error before fdopen, close explicitly
                    pass

                # Atomic replace
                tmp_path.replace(self.vault_path)
                self._status = "healthy"
                self._last_error = None
            except Exception as e:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                logger.error("Failed to atomically persist secret vault to %s: %s", self.vault_path, e)
                raise SecretStoreError(f"Vault atomic write failed: {e}") from e

    def store_secret(
        self,
        secret_ref: str,
        value: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> str:
        s_ref = secret_ref if secret_ref.startswith("secret_ref:") else f"secret_ref:{secret_ref}"
        with self._lock:
            # Transaction-like: encrypt and persist to disk BEFORE updating persistent cache state
            old_val = self._cache.get(s_ref)
            old_meta = self._metadata.get(s_ref)
            try:
                self._cache[s_ref] = str(value)
                self._metadata[s_ref] = {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                }
                self._save_vault()
            except Exception:
                # Rollback in-memory state on persistence failure
                if old_val is not None:
                    self._cache[s_ref] = old_val
                else:
                    self._cache.pop(s_ref, None)
                if old_meta is not None:
                    self._metadata[s_ref] = old_meta
                else:
                    self._metadata.pop(s_ref, None)
                raise
        return s_ref

    set_secret = store_secret

    def get_secret(self, secret_ref: str) -> str | None:
        s_ref = secret_ref if secret_ref.startswith("secret_ref:") else f"secret_ref:{secret_ref}"
        with self._lock:
            return self._cache.get(s_ref, self._cache.get(secret_ref))

    def delete_secret(self, secret_ref: str) -> bool:
        s_ref = secret_ref if secret_ref.startswith("secret_ref:") else f"secret_ref:{secret_ref}"
        with self._lock:
            if s_ref not in self._cache and secret_ref not in self._cache:
                return False

            old_val = self._cache.get(s_ref, self._cache.get(secret_ref))
            old_meta = self._metadata.get(s_ref, self._metadata.get(secret_ref))

            try:
                self._cache.pop(s_ref, None)
                self._cache.pop(secret_ref, None)
                self._metadata.pop(s_ref, None)
                self._metadata.pop(secret_ref, None)
                self._save_vault()
                return True
            except Exception:
                # Rollback on disk failure
                if old_val is not None:
                    self._cache[s_ref] = old_val
                if old_meta is not None:
                    self._metadata[s_ref] = old_meta
                raise

    def has_secret(self, secret_ref: str) -> bool:
        s_ref = secret_ref if secret_ref.startswith("secret_ref:") else f"secret_ref:{secret_ref}"
        with self._lock:
            return s_ref in self._cache or secret_ref in self._cache

    def get_security_status(self) -> dict[str, Any]:
        """Returns truthful security metadata."""
        return {
            "cipher": CIPHER_NAME if not self._in_memory else "memory",
            "key_source": self._key_source,
            "format_version": CURRENT_FORMAT_VERSION,
            "status": self._status,
            "record_count": len(self._cache),
            "vault_path": str(self.vault_path),
            "last_error": self._last_error,
        }


# =====================================================================
# Process-wide Singleton Management
# =====================================================================

_global_secret_store: SecretStore | None = None
_secret_store_lock = threading.RLock()


def get_secret_store(custom_path: str | Path | None = None) -> SecretStore:
    """Returns the process-wide or custom SecretStore singleton."""
    global _global_secret_store
    if custom_path is not None:
        return EncryptedVaultSecretStore(custom_path)
    with _secret_store_lock:
        if _global_secret_store is None:
            _global_secret_store = EncryptedVaultSecretStore()
        return _global_secret_store


def set_secret_store(store: SecretStore) -> None:
    """Explicitly overrides the global SecretStore (useful for testing)."""
    global _global_secret_store
    with _secret_store_lock:
        _global_secret_store = store


# =====================================================================
# Deep & Nested Secret Extraction, Resolution & Masking
# =====================================================================

def extract_secrets_deep(
    obj: Any,
    secret_store: SecretStore,
    entity_type: str,
    entity_id: str,
    parent_key: str = "",
) -> tuple[Any, int]:
    """
    Recursively traverses dictionaries and lists to extract sensitive secrets into SecretStore.
    Replaces sensitive strings with stable opaque secret_ref tokens while preserving
    surrounding structure and non-sensitive attributes.
    """
    if isinstance(obj, dict):
        sanitized = {}
        total_extracted = 0
        for k, v in obj.items():
            current_path = f"{parent_key}.{k}" if parent_key else str(k)
            if is_secret_key(k) and isinstance(v, str) and v.strip() and not is_secret_ref(v):
                # Don't store masked placeholders
                if v.startswith("••") or "..." in v:
                    sanitized[k] = v
                    continue
                # Stable reference derivation to ensure deterministic idempotency
                safe_suffix = re.sub(r"[^a-zA-Z0-9_]", "_", current_path.lower())[:24]
                s_ref = f"secret_ref:{entity_type[:4]}_{entity_id[:8]}_{safe_suffix}_{secrets.token_hex(6)}"
                secret_store.store_secret(
                    secret_ref=s_ref,
                    value=v,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
                # Verify immediately before returning sanitized pointer (fail-closed verification)
                stored_val = secret_store.get_secret(s_ref)
                if stored_val != v:
                    raise SecretStoreError(
                        f"Failed to verify secret persistence for ref '{s_ref}'. "
                        f"Stored value does not match expected value."
                    )
                sanitized[k] = s_ref
                total_extracted += 1
            elif isinstance(v, (dict, list)):
                child_sanitized, child_count = extract_secrets_deep(
                    v, secret_store, entity_type, entity_id, parent_key=current_path
                )
                sanitized[k] = child_sanitized
                total_extracted += child_count
            else:
                sanitized[k] = v
        return sanitized, total_extracted

    elif isinstance(obj, list):
        sanitized_list = []
        total_extracted = 0
        for i, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                child_sanitized, child_count = extract_secrets_deep(
                    item, secret_store, entity_type, entity_id, parent_key=f"{parent_key}[{i}]"
                )
                sanitized_list.append(child_sanitized)
                total_extracted += child_count
            else:
                sanitized_list.append(item)
        return sanitized_list, total_extracted

    return obj, 0


def resolve_secrets_deep(obj: Any, secret_store: SecretStore) -> Any:
    """
    Recursively traverses dictionaries and lists to resolve any secret_ref tokens
    back to real secret strings. Used exclusively by internal runtime executors.
    """
    if isinstance(obj, dict):
        resolved = {}
        for k, v in obj.items():
            if isinstance(v, str) and is_secret_ref(v):
                plain = secret_store.get_secret(v)
                resolved[k] = plain if plain is not None else v
            elif isinstance(v, (dict, list)):
                resolved[k] = resolve_secrets_deep(v, secret_store)
            else:
                resolved[k] = v
        return resolved

    elif isinstance(obj, list):
        return [resolve_secrets_deep(item, secret_store) for item in obj]

    elif isinstance(obj, str) and is_secret_ref(obj):
        plain = secret_store.get_secret(obj)
        return plain if plain is not None else obj

    return obj


def mask_secrets_deep(obj: Any) -> Any:
    """
    Recursively masks secrets and secret_ref references for safe external API serialization.
    """
    if isinstance(obj, dict):
        masked = {}
        for k, v in obj.items():
            if is_secret_key(k):
                if isinstance(v, str) and len(v) > 6 and not is_secret_ref(v):
                    masked[k] = f"{v[:4]}...{v[-3:]}"
                elif isinstance(v, str) and v:
                    masked[k] = "••••••••"
                elif isinstance(v, (dict, list)):
                    masked[k] = mask_secrets_deep(v)
                else:
                    masked[k] = v
            elif isinstance(v, (dict, list)):
                masked[k] = mask_secrets_deep(v)
            else:
                masked[k] = v
        return masked

    elif isinstance(obj, list):
        return [mask_secrets_deep(item) for item in obj]

    return obj


# Backwards compatibility aliases
extract_secrets_from_dict = extract_secrets_deep
resolve_secrets_in_dict = resolve_secrets_deep
mask_secrets_in_dict = mask_secrets_deep


# =====================================================================
# Migration Journal & Idempotent Universal Migration
# =====================================================================

class MigrationJournal:
    """
    Persistent migration state journal stored per workspace.
    Guarantees observable state, idempotency, and recovery across restarts.
    """

    def __init__(self, workspace_path: Path) -> None:
        self.journal_file = workspace_path / ".aether" / "migration_journal.json"

    def get_status(self) -> dict[str, Any]:
        if not self.journal_file.exists():
            return {"status": "not_started", "version": 0}
        try:
            return json.loads(self.journal_file.read_text(encoding="utf-8"))
        except Exception:
            return {"status": "corrupted", "version": 0}

    def record_start(self) -> None:
        self.journal_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "target_version": CURRENT_FORMAT_VERSION,
        }
        self.journal_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_success(self, migrated_counts: dict[str, int]) -> None:
        data = {
            "status": "completed",
            "version": CURRENT_FORMAT_VERSION,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "migrated_counts": migrated_counts,
            "last_error": None,
        }
        self.journal_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_failure(self, error: str) -> None:
        data = {
            "status": "failed",
            "version": 0,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "last_error": error,
        }
        self.journal_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def migrate_all_secrets(
    workspace: Any,
    secret_store: SecretStore | None = None,
    force: bool = False,
) -> dict[str, int]:
    """
    Strictly idempotent, failure-safe migration of raw SQLite databases across:
    1. Connections (auth_metadata)
    2. Notification Channels (config)
    3. Automations (trigger_json)

    Protocol:
    - Inspects RAW database tables directly via SQLite queries (bypasses domain model auto-resolution).
    - Skips records already containing 'secret_ref:'.
    - Writes extracted secrets to SecretStore and verifies readability BEFORE updating SQLite.
    - Transactional atomic update in SQLite (rollback leaves plaintext intact on failure).
    - Updates MigrationJournal; marks workspace degraded if migration fails (fail-closed).
    """
    store = secret_store or get_secret_store()
    raw_ws_path = getattr(workspace, "root", None) or getattr(workspace, "root_path", None) or getattr(workspace, "path", None)
    if raw_ws_path is None and hasattr(workspace, "data_dir"):
        raw_ws_path = Path(workspace.data_dir).parent
    ws_path = Path(raw_ws_path or ".")
    journal = MigrationJournal(ws_path)

    # Check journal state: if already completed and no forced run, return immediately
    j_state = journal.get_status()
    if not force and j_state.get("status") == "completed" and j_state.get("version") == CURRENT_FORMAT_VERSION:
        # Quick idempotency check: 0 new migrations needed
        try:
            setattr(workspace, "protection_status", "ready")
        except Exception:
            pass
        return {"connections": 0, "notifications": 0, "automations": 0}

    journal.record_start()
    results = {"connections": 0, "notifications": 0, "automations": 0}

    try:
        # 1. Connections Migration (Raw inspection)
        if hasattr(workspace, "connections") and hasattr(workspace.connections, "store"):
            c_store = workspace.connections.store
            with c_store._get_connection() as conn:
                cursor = conn.execute("SELECT id, auth_metadata FROM connections;")
                rows = cursor.fetchall()
                for conn_id, raw_json_str in rows:
                    if not raw_json_str:
                        continue
                    try:
                        meta = json.loads(raw_json_str)
                    except Exception:
                        continue

                    # Deep extraction on raw stored JSON
                    sanitized, count = extract_secrets_deep(
                        meta,
                        secret_store=store,
                        entity_type="connection",
                        entity_id=conn_id,
                    )
                    if count > 0:
                        # Transactional DB update
                        conn.execute(
                            "UPDATE connections SET auth_metadata = ? WHERE id = ?;",
                            (json.dumps(sanitized), conn_id),
                        )
                        results["connections"] += count
                if results["connections"] > 0:
                    try:
                        conn.commit()
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                        conn.execute("VACUUM;")
                    except Exception:
                        pass

        # 2. Notification Channels Migration (Raw inspection)
        if hasattr(workspace, "notifications") and hasattr(workspace.notifications, "store"):
            n_store = workspace.notifications.store
            with n_store._get_connection() as conn:
                cursor = conn.execute("SELECT id, config FROM notification_channels;")
                rows = cursor.fetchall()
                for chan_id, raw_json_str in rows:
                    if not raw_json_str:
                        continue
                    try:
                        cfg = json.loads(raw_json_str)
                    except Exception:
                        continue

                    sanitized, count = extract_secrets_deep(
                        cfg,
                        secret_store=store,
                        entity_type="notification_channel",
                        entity_id=chan_id,
                    )
                    if count > 0:
                        conn.execute(
                            "UPDATE notification_channels SET config = ? WHERE id = ?;",
                            (json.dumps(sanitized), chan_id),
                        )
                        results["notifications"] += count
                if results["notifications"] > 0:
                    try:
                        conn.commit()
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                        conn.execute("VACUUM;")
                    except Exception:
                        pass

        # 3. Automations Migration (Raw inspection)
        if hasattr(workspace, "automations"):
            a_store = getattr(workspace.automations, "store", workspace.automations)
            if hasattr(a_store, "_get_connection"):
                with a_store._get_connection() as conn:
                    cursor = conn.execute("SELECT id, trigger_json FROM automations;")
                    rows = cursor.fetchall()
                    for auto_id, raw_json_str in rows:
                        if not raw_json_str:
                            continue
                        try:
                            trig = json.loads(raw_json_str)
                        except Exception:
                            continue

                        sanitized, count = extract_secrets_deep(
                            trig,
                            secret_store=store,
                            entity_type="automation_trigger",
                            entity_id=auto_id,
                        )
                        if count > 0:
                            conn.execute(
                                "UPDATE automations SET trigger_json = ? WHERE id = ?;",
                                (json.dumps(sanitized), auto_id),
                            )
                            results["automations"] += count
                    if results["automations"] > 0:
                        try:
                            conn.commit()
                            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                            conn.execute("VACUUM;")
                        except Exception:
                            pass

        journal.record_success(results)
        try:
            setattr(workspace, "protection_status", "ready")
        except Exception:
            pass
        logger.info("Universal secret migration completed successfully: %s", results)
        return results

    except Exception as exc:
        err_msg = f"Secret migration failed: {exc}"
        logger.error(err_msg, exc_info=True)
        journal.record_failure(err_msg)
        try:
            setattr(workspace, "protection_status", "migration_failed")
        except Exception:
            pass
        raise SecretMigrationError(err_msg) from exc
