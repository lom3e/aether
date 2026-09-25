"""
EcosystemStore — SQLite persistence and installation engine for Aether Marketplace packages.
Handles package catalog, security permission analysis, and physical workspace installation.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Generator
import uuid

from aether.core.sqlite import get_sqlite_connection, sqlite_connection
from aether.ecosystem.models import (
    InstalledPackage,
    PackageManifest,
    PackagePermission,
    PackageType,
    RiskLevel,
    SecuritySummary,
)

logger = logging.getLogger(__name__)


class EcosystemStore:
    """Manages the ecosystem package repository and installed package records."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:" or "mode=memory" in self.db_path
        if self.db_path == ":memory:":
            self.db_path = f"file:memdb_ecosystem_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._keepalive_conn: sqlite3.Connection | None = (
            get_sqlite_connection(self.db_path) if self._is_memory else None
        )
        self._init_db()
        self._seed_default_catalog_if_empty()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        with sqlite_connection(self.db_path) as conn:
            yield conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS packages (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    type TEXT NOT NULL,
                    author TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'general',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    security_summary_json TEXT NOT NULL DEFAULT '{}',
                    dependencies_json TEXT NOT NULL DEFAULT '[]',
                    contents_json TEXT NOT NULL DEFAULT '{}',
                    verified INTEGER NOT NULL DEFAULT 1,
                    downloads_count INTEGER NOT NULL DEFAULT 0,
                    rating REAL NOT NULL DEFAULT 5.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS installed_packages (
                    package_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    installed_at TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    install_path TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (package_id, workspace_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pkg_type ON packages(type);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pkg_category ON packages(category);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_ws ON installed_packages(workspace_id);")

    def _seed_default_catalog_if_empty(self) -> None:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM packages")
            if cur.fetchone()[0] > 0:
                return

        seeds: list[PackageManifest] = [
            # 1. Workforce: SecOps Defense
            PackageManifest(
                id="workforce-secops-defense",
                name="SecOps & Vulnerability Defense",
                version="1.0.0",
                type=PackageType.WORKFORCE,
                author="Aether Security Lab",
                description="Autonomous security workforce for CVE vulnerability auditing, secret scanning, and automated compliance.",
                category="security",
                tags=["security", "cve", "compliance", "auditing"],
                security_summary=SecuritySummary(
                    risk_level=RiskLevel.MEDIUM,
                    permissions=[
                        PackagePermission("filesystem:read", "Scans repository and configuration files for vulnerabilities", "read"),
                        PackagePermission("network:outbound", "Queries National Vulnerability Database (NVD) feeds", "read"),
                    ],
                    network_domains=["nvd.nist.gov", "cve.mitre.org"],
                    filesystem_paths=["src/", "config/", ".env.example"],
                    audit_notes=["Read-only filesystem access; no destructive operations permitted."],
                ),
                contents={
                    "team_name": "SecOpsDefense",
                    "agents": [
                        {
                            "name": "SecLead",
                            "role": "Chief Security Officer",
                            "instructions": "Coordinate security posture and prioritize threat mitigation.",
                            "model": "gemini-1.5-pro",
                        },
                        {
                            "name": "CveScanner",
                            "role": "Vulnerability Auditor",
                            "instructions": "Scan package dependencies and identify CVEs.",
                            "model": "gemini-1.5-flash",
                        },
                        {
                            "name": "ComplianceGuard",
                            "role": "Compliance Officer",
                            "instructions": "Verify SOC2, HIPAA, and GDPR posture.",
                            "model": "gemini-1.5-pro",
                        },
                    ],
                },
                downloads_count=1240,
                rating=4.95,
            ),
            # 2. Workforce: Full-Stack Web
            PackageManifest(
                id="workforce-fullstack-dev",
                name="Full-Stack Web Engineering",
                version="1.2.0",
                type=PackageType.WORKFORCE,
                author="Aether Core",
                description="Full-stack engineering squad capable of shipping end-to-end React, TypeScript, and FastAPI features.",
                category="engineering",
                tags=["fullstack", "react", "fastapi", "typescript"],
                security_summary=SecuritySummary(
                    risk_level=RiskLevel.LOW,
                    permissions=[
                        PackagePermission("filesystem:write", "Creates source files and frontend components", "write"),
                    ],
                    filesystem_paths=["src/", "ui/src/"],
                    audit_notes=["Local repository modifications only."],
                ),
                contents={
                    "team_name": "FullStackSquad",
                    "agents": [
                        {
                            "name": "TechLead",
                            "role": "Principal Software Architect",
                            "instructions": "Plan architectural boundaries and ensure system cohesion.",
                        },
                        {
                            "name": "FrontendDev",
                            "role": "Senior React Engineer",
                            "instructions": "Implement responsive, accessible UI components.",
                        },
                        {
                            "name": "BackendDev",
                            "role": "Senior Python Backend Engineer",
                            "instructions": "Design REST APIs and data models with FastAPI.",
                        },
                    ],
                },
                downloads_count=3420,
                rating=4.98,
            ),
            # 3. Skill: Kubernetes & Container Orchestration
            PackageManifest(
                id="skill-docker-k8s",
                name="Kubernetes & Container Orchestrator",
                version="1.1.0",
                type=PackageType.SKILL,
                author="Cloud Native Guild",
                description="Autonomous skill pack for generating multi-stage Dockerfiles, Helm charts, and K8s manifests.",
                category="devops",
                tags=["docker", "kubernetes", "helm", "devops"],
                security_summary=SecuritySummary(
                    risk_level=RiskLevel.LOW,
                    permissions=[
                        PackagePermission("filesystem:write", "Generates Dockerfile and Kubernetes deployment manifests", "write"),
                    ],
                    filesystem_paths=["deploy/", "k8s/", "Dockerfile"],
                    audit_notes=["Produces configuration manifests without invoking cluster mutations directly."],
                ),
                contents={
                    "skill_name": "docker-k8s",
                    "files": {
                        "SKILL.md": "# Kubernetes & Docker Skill\nGenerates optimized production container configurations.",
                        "template_dockerfile.txt": "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nCMD [\"python\", \"main.py\"]\n",
                    },
                },
                downloads_count=2150,
                rating=4.88,
            ),
            # 4. Skill: API Stress Tester
            PackageManifest(
                id="skill-api-stress-tester",
                name="API Load & Resilience Benchmark",
                version="1.0.4",
                type=PackageType.SKILL,
                author="Reliability Labs",
                description="Calculates p50, p95, and p99 latency distributions, concurrency thresholds, and rate limits.",
                category="testing",
                tags=["benchmark", "performance", "api", "load-testing"],
                security_summary=SecuritySummary(
                    risk_level=RiskLevel.MEDIUM,
                    permissions=[
                        PackagePermission("network:outbound", "Sends benchmark traffic to user-designated test target endpoints", "execute"),
                    ],
                    network_domains=["localhost", "127.0.0.1"],
                    audit_notes=["Traffic generator constrained to specified target domains."],
                ),
                contents={
                    "skill_name": "api-stress-tester",
                    "files": {
                        "SKILL.md": "# API Stress Tester\nBenchmarks REST endpoints and outputs latency histograms.",
                    },
                },
                downloads_count=890,
                rating=4.79,
            ),
            # 5. Tool: Relational Database Introspector
            PackageManifest(
                id="tool-sql-introspect",
                name="Relational Database Introspector",
                version="1.0.0",
                type=PackageType.TOOL,
                author="Data Intelligence Group",
                description="Deep introspector for PostgreSQL, MySQL, and SQLite schemas with foreign key graph extraction.",
                category="database",
                tags=["database", "sql", "postgres", "sqlite", "schema"],
                security_summary=SecuritySummary(
                    risk_level=RiskLevel.LOW,
                    permissions=[
                        PackagePermission("database:read", "Queries database information_schema and sqlite_master tables", "read"),
                    ],
                    audit_notes=["Strictly read-only database metadata inspection."],
                ),
                contents={
                    "tool_id": "db.introspect_schema",
                    "config": {
                        "supported_dialects": ["postgres", "mysql", "sqlite"],
                        "read_only": True,
                    },
                },
                downloads_count=1780,
                rating=4.91,
            ),
            # 6. Connector: Slack Ops Alerting
            PackageManifest(
                id="connector-slack-ops",
                name="Slack Ops Alerting Fabric",
                version="1.3.0",
                type=PackageType.CONNECTOR,
                author="Aether Integrations",
                description="Bidirectional operational bridge for Slack channels, mission dispatch notifications, and incident alerts.",
                category="connectors",
                tags=["slack", "notifications", "chatops", "alerting"],
                security_summary=SecuritySummary(
                    risk_level=RiskLevel.MEDIUM,
                    permissions=[
                        PackagePermission("network:outbound", "Sends message payloads to Slack Incoming Webhooks API", "write"),
                    ],
                    network_domains=["hooks.slack.com", "slack.com"],
                    audit_notes=["Requires user-provided Slack Webhook URL."],
                ),
                contents={
                    "connector_id": "slack_ops",
                    "protocol": "webhook",
                    "endpoint_template": "https://hooks.slack.com/services/{webhook_token}",
                },
                downloads_count=2980,
                rating=4.92,
            ),
            # 7. Workflow Template: Continuous Security Audit
            PackageManifest(
                id="workflow-continuous-security",
                name="Continuous Security Audit Pipeline",
                version="1.0.0",
                type=PackageType.WORKFLOW_TEMPLATE,
                author="Aether SecOps",
                description="Ready-to-run visual workflow: Weekly Trigger -> Security Scanner -> Staff Approval Checkpoint -> PDF Deliverable.",
                category="security",
                tags=["workflow", "security", "pipeline", "dag"],
                security_summary=SecuritySummary(
                    risk_level=RiskLevel.LOW,
                    permissions=[
                        PackagePermission("workflow:execute", "Executes multi-step security DAG", "execute"),
                        PackagePermission("approval:require", "Enforces human clearance gate before artifact generation", "read"),
                    ],
                    audit_notes=["Includes mandatory human-in-the-loop clearance step."],
                ),
                contents={
                    "workflow": {
                        "id": "wf_sec_audit_tpl",
                        "name": "Continuous Security Audit Pipeline",
                        "description": "Weekly automated security scan with clearance approval gate and executive report.",
                        "graph": {
                            "nodes": [
                                {
                                    "id": "trig_sec_cron",
                                    "type": "trigger",
                                    "title": "Weekly Audit Trigger",
                                    "config": {"type": "schedule", "cron": "0 2 * * 1"},
                                    "position": {"x": 50, "y": 150},
                                },
                                {
                                    "id": "agent_sec_scan",
                                    "type": "agent",
                                    "title": "Security Scanner",
                                    "config": {"agent_name": "SecBot", "prompt": "Audit codebase for CVEs and leaked secrets"},
                                    "position": {"x": 300, "y": 150},
                                },
                                {
                                    "id": "appr_lead_signoff",
                                    "type": "approval",
                                    "title": "Lead Security Clearance",
                                    "config": {"tier": "Supervised"},
                                    "position": {"x": 550, "y": 150},
                                },
                                {
                                    "id": "deliv_sec_report",
                                    "type": "deliverable",
                                    "title": "Executive Security Audit Report",
                                    "config": {"output_format": "markdown", "target": "reports/security_audit.md"},
                                    "position": {"x": 800, "y": 150},
                                },
                            ],
                            "edges": [
                                {"id": "e1", "source": "trig_sec_cron", "target": "agent_sec_scan"},
                                {"id": "e2", "source": "agent_sec_scan", "target": "appr_lead_signoff"},
                                {"id": "e3", "source": "appr_lead_signoff", "target": "deliv_sec_report"},
                            ],
                        },
                    },
                },
                downloads_count=1650,
                rating=4.94,
            ),
        ]

        for pkg in seeds:
            self.save_package(pkg)

    # -----------------------------------------------------------------------
    # Package Catalog Operations
    # -----------------------------------------------------------------------

    def save_package(self, package: PackageManifest) -> PackageManifest:
        """Saves or updates a package in the catalog."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO packages (
                    id, name, version, type, author, description, category,
                    tags_json, security_summary_json, dependencies_json, contents_json,
                    verified, downloads_count, rating, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    package.id,
                    package.name,
                    package.version,
                    package.type.value if isinstance(package.type, PackageType) else str(package.type),
                    package.author,
                    package.description,
                    package.category,
                    json.dumps(package.tags),
                    json.dumps(package.security_summary.to_dict()),
                    json.dumps(package.dependencies),
                    json.dumps(package.contents),
                    1 if package.verified else 0,
                    package.downloads_count,
                    package.rating,
                    package.created_at,
                    package.updated_at,
                ),
            )
        return package

    def get_package(self, package_id: str) -> PackageManifest | None:
        """Retrieves a package specification by ID."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT id, name, version, type, author, description, category,
                       tags_json, security_summary_json, dependencies_json, contents_json,
                       verified, downloads_count, rating, created_at, updated_at
                FROM packages WHERE id = ?
                """,
                (package_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return PackageManifest(
                id=row[0],
                name=row[1],
                version=row[2],
                type=PackageType(row[3]) if row[3] in PackageType._value2member_map_ else PackageType.SKILL,
                author=row[4],
                description=row[5],
                category=row[6],
                tags=json.loads(row[7]) if row[7] else [],
                security_summary=SecuritySummary.from_dict(json.loads(row[8]) if row[8] else {}),
                dependencies=json.loads(row[9]) if row[9] else [],
                contents=json.loads(row[10]) if row[10] else {},
                verified=bool(row[11]),
                downloads_count=row[12],
                rating=row[13],
                created_at=row[14],
                updated_at=row[15],
            )

    def list_packages(
        self,
        pkg_type: str | None = None,
        category: str | None = None,
        search: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lists packages with optional filters and installed status indicator."""
        installed_ids: set[str] = set()
        if workspace_id:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "SELECT package_id FROM installed_packages WHERE workspace_id = ?",
                    (workspace_id,),
                )
                installed_ids = {r[0] for r in cur.fetchall()}

        query = "SELECT * FROM packages WHERE 1=1"
        params: list[Any] = []

        if pkg_type:
            query += " AND type = ?"
            params.append(pkg_type.lower())
        if category:
            query += " AND category = ?"
            params.append(category.lower())
        if search:
            query += " AND (name LIKE ? OR description LIKE ? OR tags_json LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term, term])

        query += " ORDER BY downloads_count DESC, rating DESC"

        result = []
        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            for row in cur.fetchall():
                pkg = PackageManifest(
                    id=row[0],
                    name=row[1],
                    version=row[2],
                    type=PackageType(row[3]) if row[3] in PackageType._value2member_map_ else PackageType.SKILL,
                    author=row[4],
                    description=row[5],
                    category=row[6],
                    tags=json.loads(row[7]) if row[7] else [],
                    security_summary=SecuritySummary.from_dict(json.loads(row[8]) if row[8] else {}),
                    dependencies=json.loads(row[9]) if row[9] else [],
                    contents=json.loads(row[10]) if row[10] else {},
                    verified=bool(row[11]),
                    downloads_count=row[12],
                    rating=row[13],
                    created_at=row[14],
                    updated_at=row[15],
                )
                pkg_dict = pkg.to_dict()
                pkg_dict["is_installed"] = pkg.id in installed_ids
                result.append(pkg_dict)

        return result

    def get_security_summary(self, package_id: str) -> SecuritySummary | None:
        """Returns the security and permission summary for a package."""
        pkg = self.get_package(package_id)
        return pkg.security_summary if pkg else None

    # -----------------------------------------------------------------------
    # Installation & Uninstallation Engine
    # -----------------------------------------------------------------------

    def is_installed(self, package_id: str, workspace_id: str) -> bool:
        """Returns True if the package is recorded as installed in the given workspace."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT 1 FROM installed_packages WHERE package_id = ? AND workspace_id = ?",
                (package_id, workspace_id),
            )
            return cur.fetchone() is not None

    def install_package(self, package_id: str, workspace: Any) -> InstalledPackage:
        """
        Executes physical installation of a package into the workspace:
        - Workforce: creates or merges agents into team topology.
        - Skill: writes skill folder into workspace .aether/skills/.
        - Workflow Template: persists visual workflow DAG into workspace.workflows.
        - Tool / Connector: persists configuration artifact.
        """
        pkg = self.get_package(package_id)
        if not pkg:
            raise ValueError(f"Package '{package_id}' not found in ecosystem catalog.")

        ws_id = getattr(workspace, "name", "default")
        install_path: str | None = None
        now = datetime.now(timezone.utc).isoformat()

        # 1. Workforce Installation
        if pkg.type == PackageType.WORKFORCE:
            team_name = pkg.contents.get("team_name", pkg.name)
            # Create team configuration if workspace has team facilities
            team_dir = workspace.root / ".aether" / "teams"
            team_dir.mkdir(parents=True, exist_ok=True)
            team_file = team_dir / f"{pkg.id}.json"
            team_file.write_text(json.dumps(pkg.contents, indent=2), encoding="utf-8")
            install_path = str(team_file)

        # 2. Skill Installation
        elif pkg.type == PackageType.SKILL:
            skill_name = pkg.contents.get("skill_name", pkg.id)
            skills_dir = workspace.root / ".aether" / "skills" / skill_name
            skills_dir.mkdir(parents=True, exist_ok=True)
            files = pkg.contents.get("files", {})
            for rel_file, content in files.items():
                dest_file = skills_dir / rel_file
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_text(content, encoding="utf-8")
            install_path = str(skills_dir)

        # 3. Workflow Template Installation
        elif pkg.type == PackageType.WORKFLOW_TEMPLATE:
            wf_data = pkg.contents.get("workflow", {})
            if hasattr(workspace, "workflows"):
                from aether.workflows.models import Workflow
                wf_id = f"wf_{pkg.id.replace('-', '_')}"
                wf_data["id"] = wf_id
                wf_data["workspace_id"] = ws_id
                wf = Workflow.from_dict(wf_data)
                workspace.workflows.save_workflow(wf)
                install_path = f"workflow://{wf.id}"

        # 4. Tool / Connector Installation
        else:
            conf_dir = workspace.root / ".aether" / "ecosystem"
            conf_dir.mkdir(parents=True, exist_ok=True)
            conf_file = conf_dir / f"{pkg.id}.json"
            conf_file.write_text(json.dumps(pkg.contents, indent=2), encoding="utf-8")
            install_path = str(conf_file)

        # Record installed package in database
        installed = InstalledPackage(
            package_id=pkg.id,
            workspace_id=ws_id,
            version=pkg.version,
            installed_at=now,
            enabled=True,
            install_path=install_path,
            metadata={"installed_by": "aether_marketplace", "name": pkg.name, "type": pkg.type.value},
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO installed_packages (
                    package_id, workspace_id, version, installed_at, enabled, install_path, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    installed.package_id,
                    installed.workspace_id,
                    installed.version,
                    installed.installed_at,
                    1 if installed.enabled else 0,
                    installed.install_path,
                    json.dumps(installed.metadata),
                ),
            )
            # Increment downloads count
            conn.execute("UPDATE packages SET downloads_count = downloads_count + 1 WHERE id = ?", (pkg.id,))

        logger.info(f"Installed ecosystem package '{pkg.id}' in workspace '{ws_id}'.")
        return installed

    def uninstall_package(self, package_id: str, workspace: Any) -> bool:
        """Removes an installed package and its physical artifacts from the workspace."""
        ws_id = getattr(workspace, "name", "default")
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT install_path FROM installed_packages WHERE package_id = ? AND workspace_id = ?",
                (package_id, ws_id),
            )
            row = cur.fetchone()
            if not row:
                return False

            install_path = row[0]
            conn.execute(
                "DELETE FROM installed_packages WHERE package_id = ? AND workspace_id = ?",
                (package_id, ws_id),
            )

        # Cleanup physical file/directory if it exists
        if install_path:
            if install_path.startswith("workflow://"):
                wf_id = install_path.replace("workflow://", "")
                if hasattr(workspace, "workflows"):
                    workspace.workflows.delete_workflow(wf_id, workspace_id=ws_id)
            else:
                p = Path(install_path)
                try:
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    elif p.is_file():
                        p.unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning(f"Failed to delete installed artifact at {install_path}: {exc}")

        logger.info(f"Uninstalled ecosystem package '{package_id}' from workspace '{ws_id}'.")
        return True

    def list_installed(self, workspace_id: str) -> list[InstalledPackage]:
        """Lists all packages installed in the designated workspace."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT package_id, workspace_id, version, installed_at, enabled, install_path, metadata_json "
                "FROM installed_packages WHERE workspace_id = ? ORDER BY installed_at DESC",
                (workspace_id,),
            )
            results = []
            for row in cur.fetchall():
                results.append(
                    InstalledPackage(
                        package_id=row[0],
                        workspace_id=row[1],
                        version=row[2],
                        installed_at=row[3],
                        enabled=bool(row[4]),
                        install_path=row[5],
                        metadata=json.loads(row[6]) if row[6] else {},
                    )
                )
            return results
