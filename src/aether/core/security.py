"""
Security Foundation — PathSandbox & Filesystem Access Policy for Aether.

Enforces strict filesystem boundary confinement:
- Root directory anchoring
- Canonical path resolution via realpath
- Path traversal prevention (e.g. ../, nested ../, absolute paths)
- Symlink escape prevention
- Sensitive file & directory blacklist (.env*, .git, credentials, keys, node_modules, etc.)
- Relative path sanitization and non-leaking path formatting
"""
from __future__ import annotations

import fnmatch
import os
from enum import Enum
from pathlib import Path
from typing import Sequence

from aether.errors import (
    SecurityBoundaryViolation,
    SensitivePathAccessDenied,
    FileNotFoundToolError,
    DirectoryNotFoundToolError,
)


class OperationType(str, Enum):
    """Filesystem operation types for policy validation and auditing."""
    READ = "read"
    WRITE = "write"
    PATCH = "patch"
    DELETE = "delete"
    LIST = "list"


# Default blacklist patterns applied across all path components and basenames
DEFAULT_SENSITIVE_PATTERNS: tuple[str, ...] = (
    # Environment & configuration files
    ".env",
    ".env.*",
    ".envrc",
    # Version control & internal repositories
    ".git",
    ".git/**",
    ".svn",
    ".svn/**",
    ".hg",
    ".hg/**",
    # Dependencies, caches, and build artifacts
    "node_modules",
    "node_modules/**",
    ".venv",
    ".venv/**",
    "__pycache__",
    "__pycache__/**",
    ".pytest_cache",
    ".pytest_cache/**",
    ".tox",
    ".tox/**",
    # Secrets, private keys, and certificates
    "*credentials*",
    "*id_rsa*",
    "*id_ecdsa*",
    "*id_ed25519*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.pkcs12",
    # Operating system metadata
    ".DS_Store",
    "Thumbs.db",
    # Aether internal databases if located in the files folder
    "*.db",
    "*.db-wal",
    "*.db-shm",
)


class PathSandbox:
    """
    Filesystem security boundary enforcing root anchoring and path validation.
    
    All tools and operations receive relative or user-provided paths and must
    pass through this sandbox before performing any disk I/O.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        sensitive_patterns: Sequence[str] | None = None,
        auto_create: bool = True,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        if auto_create and not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=True)
        self.sensitive_patterns = tuple(sensitive_patterns or DEFAULT_SENSITIVE_PATTERNS)

    def is_sensitive(self, path: str | Path) -> bool:
        """
        Check whether a path or any of its segments match sensitive patterns.
        """
        path_str = str(path).replace("\\", "/").strip()
        rel_str = path_str.lstrip("/")
        if not rel_str:
            return False

        parts = Path(rel_str).parts

        for pattern in self.sensitive_patterns:
            # Check full relative path match
            if fnmatch.fnmatch(rel_str.lower(), pattern.lower()):
                return True
            # Check filename / basename match
            if fnmatch.fnmatch(Path(rel_str).name.lower(), pattern.lower()):
                return True
            # Check any individual path component
            for part in parts:
                if fnmatch.fnmatch(part.lower(), pattern.lower()):
                    return True
                # Match directory glob patterns like ".git/**"
                if pattern.endswith("/**") and fnmatch.fnmatch(part.lower(), pattern[:-3].lower()):
                    return True
        return False

    def resolve(self, path: str | Path, *, check_symlink: bool = True) -> Path:
        """
        Resolve a user-provided path relative to sandbox root with traversal protection.
        
        Raises SecurityBoundaryViolation if the path escapes the sandbox root.
        """
        if not path or str(path).strip() in {"", "."}:
            return self.root

        raw_str = str(path).strip()

        # Reject null byte injection
        if "\0" in raw_str:
            raise SecurityBoundaryViolation("Path contains null byte character.")

        # Strip leading separators to force relative anchoring within sandbox root
        cleaned_rel = raw_str.lstrip("/\\")

        candidate = self.root / cleaned_rel

        # Resolve real canonical path
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError) as exc:
            raise SecurityBoundaryViolation(f"Unable to resolve path: {raw_str}") from exc

        # Check containment within self.root
        try:
            if not resolved.is_relative_to(self.root):
                raise SecurityBoundaryViolation(
                    f"Path '{raw_str}' resolves outside sandbox root."
                )
            if os.path.commonpath([str(self.root), str(resolved)]) != str(self.root):
                raise SecurityBoundaryViolation(
                    f"Path '{raw_str}' violates sandbox boundary."
                )
        except ValueError:
            raise SecurityBoundaryViolation(
                f"Path '{raw_str}' violates sandbox boundary."
            )

        # Check symlink escape if target exists and is a symlink
        if check_symlink and candidate.is_symlink():
            try:
                real_target = Path(os.path.realpath(candidate))
                if not real_target.is_relative_to(self.root) or os.path.commonpath([str(self.root), str(real_target)]) != str(self.root):
                    raise SecurityBoundaryViolation(
                        f"Symlink '{raw_str}' points outside sandbox boundary."
                    )
            except (ValueError, OSError) as exc:
                raise SecurityBoundaryViolation(
                    f"Symlink '{raw_str}' points outside sandbox boundary."
                ) from exc

        return resolved

    def validate_path(
        self,
        path: str | Path,
        operation: OperationType | str = OperationType.READ,
        *,
        must_exist: bool | None = None,
    ) -> Path:
        """
        Validate path resolution, boundary confinement, and sensitive pattern protection.
        
        Parameters
        ----------
        path:
            Relative path or path expression within the sandbox.
        operation:
            The intended operation (read, write, delete, patch, list).
        must_exist:
            If True, raises FileNotFoundToolError if path does not exist.
            If False, raises FilesystemToolError if path already exists.
            If None (default), existence is not asserted.
            
        Returns
        -------
        Path
            The resolved and validated canonical Path.
        """
        op_str = operation.value if isinstance(operation, OperationType) else str(operation).lower()

        # 1. Resolve and check boundary confinement
        resolved = self.resolve(path)

        # 2. Get sanitized relative representation for sensitive pattern checking
        rel_str = self.get_relative_path(resolved)

        # If target is the sandbox root itself
        if resolved == self.root:
            if op_str in {OperationType.DELETE.value, OperationType.WRITE.value, OperationType.PATCH.value}:
                raise SecurityBoundaryViolation("Cannot perform destructive operation directly on sandbox root.")
            return resolved

        # 3. Check sensitive patterns on relative path and original raw input
        if self.is_sensitive(rel_str) or self.is_sensitive(path):
            raise SensitivePathAccessDenied(
                f"Access denied: '{rel_str}' matches protected sensitive pattern."
            )

        # 4. Existence assertions if requested
        if must_exist is True:
            if not resolved.exists():
                if op_str == OperationType.LIST.value:
                    raise DirectoryNotFoundToolError(f"Directory not found: '{rel_str}'")
                raise FileNotFoundToolError(f"File not found: '{rel_str}'")

        return resolved

    def get_relative_path(self, path: str | Path) -> str:
        """
        Convert a resolved or arbitrary path into a safe, normalized relative POSIX path.
        """
        try:
            resolved = Path(path).resolve()
            if resolved == self.root:
                return "."
            if resolved.is_relative_to(self.root):
                return resolved.relative_to(self.root).as_posix()
        except Exception:
            pass

        # Fallback normalization
        raw = str(path).replace("\\", "/").strip().lstrip("/")
        return raw or "."

    def is_safe(self, path: str | Path) -> bool:
        """
        Non-raising check whether a path can be safely accessed.
        """
        try:
            self.validate_path(path)
            return True
        except (SecurityBoundaryViolation, SensitivePathAccessDenied):
            return False


def validate_public_url(url: str, allow_internal: bool = False) -> None:
    """
    SSRF Protection: Validates that an outbound HTTP/HTTPS request target does not resolve
    to a private, loopback, link-local, multicast, or cloud-metadata network address.

    Raises SecurityBoundaryViolation if the target IP address is prohibited.
    """
    if allow_internal or os.environ.get("AETHER_ALLOW_INTERNAL_HTTP") == "1":
        return

    import ipaddress
    import socket
    import urllib.parse

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SecurityBoundaryViolation(
            f"Invalid URL scheme '{parsed.scheme}'. Only http and https are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SecurityBoundaryViolation(f"URL '{url}' is missing a valid hostname.")

    hostname_clean = hostname.strip().lower()

    # Explicit check for localhost and known link-local patterns
    if hostname_clean in ("localhost", "0.0.0.0") or hostname_clean.endswith(".localhost"):
        raise SecurityBoundaryViolation(
            f"SSRF Protection: Access to local host '{hostname}' is blocked."
        )

    # Resolve hostname to IP addresses
    try:
        addr_info = socket.getaddrinfo(hostname_clean, None)
    except socket.gaierror as exc:
        raise SecurityBoundaryViolation(
            f"SSRF Protection: Failed to resolve hostname '{hostname}': {exc}"
        ) from exc

    for item in addr_info:
        sockaddr = item[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise SecurityBoundaryViolation(
                f"SSRF Protection: Outbound request to private/internal network address '{hostname}' ({ip_str}) is blocked."
            )
