"""
Ecosystem and Marketplace domain models for Aether.
Defines package manifests, security permission summaries, installation records, and package types.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class PackageType(StrEnum):
    WORKFORCE = "workforce"
    SKILL = "skill"
    TOOL = "tool"
    CONNECTOR = "connector"
    WORKFLOW_TEMPLATE = "workflow_template"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(slots=True)
class PackagePermission:
    """Security permission requested by an ecosystem package."""
    name: str
    description: str
    level: str = "read"  # read, write, execute, admin

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "level": self.level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackagePermission:
        return cls(
            name=data.get("name", "generic"),
            description=data.get("description", ""),
            level=data.get("level", "read"),
        )


@dataclass(slots=True)
class SecuritySummary:
    """Comprehensive security analysis and risk assessment for a package."""
    risk_level: RiskLevel = RiskLevel.LOW
    permissions: list[PackagePermission] = field(default_factory=list)
    network_domains: list[str] = field(default_factory=list)
    filesystem_paths: list[str] = field(default_factory=list)
    external_tools: list[str] = field(default_factory=list)
    audit_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else str(self.risk_level),
            "permissions": [p.to_dict() for p in self.permissions],
            "network_domains": list(self.network_domains),
            "filesystem_paths": list(self.filesystem_paths),
            "external_tools": list(self.external_tools),
            "audit_notes": list(self.audit_notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecuritySummary:
        raw_risk = data.get("risk_level", "low")
        try:
            risk = RiskLevel(raw_risk)
        except ValueError:
            risk = RiskLevel.LOW

        raw_perms = data.get("permissions") or []
        perms = [
            PackagePermission.from_dict(p) if isinstance(p, dict) else p
            for p in raw_perms
        ]

        return cls(
            risk_level=risk,
            permissions=perms,
            network_domains=list(data.get("network_domains") or []),
            filesystem_paths=list(data.get("filesystem_paths") or []),
            external_tools=list(data.get("external_tools") or []),
            audit_notes=list(data.get("audit_notes") or []),
        )


@dataclass(slots=True)
class PackageManifest:
    """Specification of an ecosystem package available for installation."""
    id: str
    name: str
    version: str = "1.0.0"
    type: PackageType = PackageType.SKILL
    author: str = "Aether Community"
    description: str = ""
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    security_summary: SecuritySummary = field(default_factory=SecuritySummary)
    dependencies: list[str] = field(default_factory=list)
    contents: dict[str, Any] = field(default_factory=dict)
    verified: bool = True
    downloads_count: int = 0
    rating: float = 5.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "type": self.type.value if isinstance(self.type, PackageType) else str(self.type),
            "author": self.author,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "security_summary": self.security_summary.to_dict(),
            "dependencies": list(self.dependencies),
            "contents": dict(self.contents),
            "verified": self.verified,
            "downloads_count": self.downloads_count,
            "rating": self.rating,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackageManifest:
        raw_type = data.get("type", "skill")
        try:
            pkg_type = PackageType(raw_type)
        except ValueError:
            pkg_type = PackageType.SKILL

        sec_data = data.get("security_summary") or {}
        sec_summary = SecuritySummary.from_dict(sec_data) if isinstance(sec_data, dict) else sec_data

        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=data.get("version", "1.0.0"),
            type=pkg_type,
            author=data.get("author", "Aether Community"),
            description=data.get("description", ""),
            category=data.get("category", "general"),
            tags=list(data.get("tags") or []),
            security_summary=sec_summary,
            dependencies=list(data.get("dependencies") or []),
            contents=dict(data.get("contents") or {}),
            verified=bool(data.get("verified", True)),
            downloads_count=int(data.get("downloads_count", 0)),
            rating=float(data.get("rating", 5.0)),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class InstalledPackage:
    """Record of a package installed in a specific workspace."""
    package_id: str
    workspace_id: str
    version: str
    installed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    enabled: bool = True
    install_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "workspace_id": self.workspace_id,
            "version": self.version,
            "installed_at": self.installed_at,
            "enabled": self.enabled,
            "install_path": self.install_path,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstalledPackage:
        return cls(
            package_id=data["package_id"],
            workspace_id=data.get("workspace_id", "default"),
            version=data.get("version", "1.0.0"),
            installed_at=data.get("installed_at") or datetime.now(timezone.utc).isoformat(),
            enabled=bool(data.get("enabled", True)),
            install_path=data.get("install_path"),
            metadata=dict(data.get("metadata") or {}),
        )
