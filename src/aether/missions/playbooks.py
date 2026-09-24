"""
Aether Mission Playbooks Engine.
Defines reusable mission templates, blueprints, and multi-agent workflow archetypes
that can be instantiated into executable missions with concrete milestones and quality gates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from aether.missions.models import Mission
    from aether.missions.store import MissionStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PlaybookMilestone:
    id: str
    title: str
    description: str
    order_idx: int
    dependencies: list[str] = field(default_factory=list)
    assigned_agent: str | None = None
    expected_deliverables: list[dict[str, Any]] = field(default_factory=list)
    verification_gate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "order_idx": self.order_idx,
            "dependencies": list(self.dependencies),
            "assigned_agent": self.assigned_agent,
            "expected_deliverables": list(self.expected_deliverables),
            "verification_gate": dict(self.verification_gate),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlaybookMilestone:
        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            title=data.get("title", "Untitled Milestone"),
            description=data.get("description", ""),
            order_idx=int(data.get("order_idx", 0)),
            dependencies=list(data.get("dependencies") or []),
            assigned_agent=data.get("assigned_agent"),
            expected_deliverables=list(data.get("expected_deliverables") or []),
            verification_gate=dict(data.get("verification_gate") or {}),
        )


@dataclass(slots=True)
class MissionPlaybook:
    id: str
    title: str
    description: str
    category: str  # "security", "engineering", "documentation", "intelligence", "operations"
    icon: str = "Target"
    team_name: str | None = None
    default_objective: str = ""
    parameter_schema: list[dict[str, Any]] = field(default_factory=list)
    milestones: list[PlaybookMilestone] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = "Aether Core"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "team_name": self.team_name,
            "default_objective": self.default_objective,
            "parameter_schema": list(self.parameter_schema),
            "milestones": [m.to_dict() for m in self.milestones],
            "tags": list(self.tags),
            "version": self.version,
            "author": self.author,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissionPlaybook:
        raw_milestones = data.get("milestones") or []
        milestones = [
            PlaybookMilestone.from_dict(m) if isinstance(m, dict) else m
            for m in raw_milestones
        ]
        return cls(
            id=data.get("id") or f"pb-{uuid.uuid4().hex[:8]}",
            title=data.get("title", "Untitled Playbook"),
            description=data.get("description", ""),
            category=data.get("category", "engineering"),
            icon=data.get("icon", "Target"),
            team_name=data.get("team_name"),
            default_objective=data.get("default_objective", ""),
            parameter_schema=list(data.get("parameter_schema") or []),
            milestones=milestones,
            tags=list(data.get("tags") or []),
            version=data.get("version", "1.0.0"),
            author=data.get("author", "Aether Core"),
            metadata=dict(data.get("metadata") or {}),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


# ===========================================================================
# Built-in Playbook Archetypes
# ===========================================================================

BUILTIN_PLAYBOOKS: list[MissionPlaybook] = [
    MissionPlaybook(
        id="code-security-audit",
        title="Codebase Security & Dependency Audit",
        description="Autonomous multi-agent inspection of source code for exposed secrets, credential leaks, AST vulnerabilities, dependency CVEs, and generation of an executive mitigation dossier.",
        category="security",
        icon="ShieldAlert",
        team_name="Engineering Core",
        default_objective="Perform a full security and secret audit across {target}: scan git logs and source tree for tokens, check dependencies for CVEs, and produce a verified security audit report.",
        parameter_schema=[
            {"key": "target", "label": "Target Path / Module", "default": "src/", "required": True},
            {"key": "severity_threshold", "label": "Minimum Severity", "default": "HIGH", "required": False},
        ],
        tags=["security", "audit", "secrets", "cve", "compliance"],
        milestones=[
            PlaybookMilestone(
                id="sec-m1",
                title="Secrets & Static AST Analysis",
                description="Scan source tree for hardcoded API keys, private credentials, and high-risk AST patterns.",
                order_idx=0,
                assigned_agent="security-auditor",
                expected_deliverables=[{"name": "static_scan_findings.json", "type": "data"}],
                verification_gate={"min_confidence": 0.85, "require_deliverable": True},
            ),
            PlaybookMilestone(
                id="sec-m2",
                title="Dependency Vulnerability & License Check",
                description="Verify packages and external libraries against security advisories and permissive license terms.",
                order_idx=1,
                dependencies=["sec-m1"],
                assigned_agent="dependency-checker",
                expected_deliverables=[{"name": "dependency_advisory.md", "type": "document"}],
                verification_gate={"min_confidence": 0.80, "require_deliverable": True},
            ),
            PlaybookMilestone(
                id="sec-m3",
                title="Executive Security Dossier & Mitigation Plan",
                description="Synthesize findings from static scans and dependencies into an actionable executive report with patch guidance.",
                order_idx=2,
                dependencies=["sec-m1", "sec-m2"],
                assigned_agent="lead-engineer",
                expected_deliverables=[{"name": "security_audit_report.md", "type": "document"}],
                verification_gate={"min_confidence": 0.90, "require_deliverable": True},
            ),
        ],
    ),
    MissionPlaybook(
        id="automated-release",
        title="Automated Release Notes & Changelog Pipeline",
        description="Inspects git commit history, closed pull requests, and verified issues to generate semantic version recommendations, changelog entries, and release readiness verification.",
        category="engineering",
        icon="GitBranch",
        team_name="Engineering Core",
        default_objective="Analyze recent commits and pull requests for {target}, produce semantic changelog notes, and compile a release readiness dossier.",
        parameter_schema=[
            {"key": "target", "label": "Repository / Branch", "default": "main", "required": True},
            {"key": "version_type", "label": "Version Bump Type", "default": "minor", "required": False},
        ],
        tags=["release", "git", "changelog", "cicd"],
        milestones=[
            PlaybookMilestone(
                id="rel-m1",
                title="Commit History & PR Analysis",
                description="Extract recent commits, PR tags, and issue references since the last release tag.",
                order_idx=0,
                assigned_agent="lead-engineer",
                expected_deliverables=[{"name": "raw_release_commits.json", "type": "data"}],
            ),
            PlaybookMilestone(
                id="rel-m2",
                title="Semantic Changelog Categorization",
                description="Categorize changes into Features, Fixes, Performance, and Breaking Changes with upgrade guidance.",
                order_idx=1,
                dependencies=["rel-m1"],
                assigned_agent="technical-writer",
                expected_deliverables=[{"name": "CHANGELOG_DRAFT.md", "type": "document"}],
            ),
            PlaybookMilestone(
                id="rel-m3",
                title="Release Pre-flight & Verification",
                description="Verify build artifacts, test passes, and produce final signed release summary.",
                order_idx=2,
                dependencies=["rel-m2"],
                assigned_agent="quality-assurance",
                expected_deliverables=[{"name": "release_verification_dossier.md", "type": "document"}],
            ),
        ],
    ),
    MissionPlaybook(
        id="knowledge-ingestion-pipeline",
        title="Documentation Ingestion & Knowledge Refresh",
        description="Ingests technical manuals, web APIs, architecture documents, and code specs into the SQLite FTS5 BM25 knowledge engine with vector chunking.",
        category="documentation",
        icon="Database",
        team_name="Research & Docs",
        default_objective="Ingest technical documentation from {target} into workspace knowledge base, index with FTS5 BM25, and verify retrieval recall.",
        parameter_schema=[
            {"key": "target", "label": "Documentation Source (Path or URL)", "default": "docs/", "required": True},
            {"key": "scope", "label": "Knowledge Scope", "default": "workspace", "required": False},
        ],
        tags=["knowledge", "ingestion", "fts5", "documentation"],
        milestones=[
            PlaybookMilestone(
                id="kb-m1",
                title="Document Extraction & Format Parsing",
                description="Harvest files, clean HTML/PDF/CSV streams, and parse into structured markdown blocks.",
                order_idx=0,
                assigned_agent="researcher",
                expected_deliverables=[{"name": "ingestion_manifest.json", "type": "data"}],
            ),
            PlaybookMilestone(
                id="kb-m2",
                title="FTS5 BM25 Indexing & Chunk Scoping",
                description="Split text into semantic chunks and store with full-text search triggers in SQLite knowledge database.",
                order_idx=1,
                dependencies=["kb-m1"],
                assigned_agent="data-engineer",
                expected_deliverables=[{"name": "indexed_chunks_summary.md", "type": "document"}],
            ),
            PlaybookMilestone(
                id="kb-m3",
                title="Knowledge Retrieval Quality Benchmarking",
                description="Run sample queries and verify that BM25 relevance scores and snippets match expected search precision.",
                order_idx=2,
                dependencies=["kb-m2"],
                assigned_agent="qa-engineer",
                expected_deliverables=[{"name": "retrieval_benchmark.json", "type": "data"}],
            ),
        ],
    ),
    MissionPlaybook(
        id="competitive-intelligence",
        title="Competitive Intelligence & Market Dossier",
        description="Autonomous multi-agent research into market trends, competitor feature matrices, product roadmaps, and executive strategy briefs.",
        category="intelligence",
        icon="Sparkles",
        team_name="Research & Strategy",
        default_objective="Conduct comprehensive market and competitor research on {target} to produce a comparative feature matrix and strategic recommendations.",
        parameter_schema=[
            {"key": "target", "label": "Topic or Competitor Domain", "default": "AI Agent Platforms", "required": True},
        ],
        tags=["market", "research", "competitors", "intelligence"],
        milestones=[
            PlaybookMilestone(
                id="ci-m1",
                title="Web & News Information Gathering",
                description="Query search engines and public documentation to collect current product and announcement data.",
                order_idx=0,
                assigned_agent="market-researcher",
                expected_deliverables=[{"name": "raw_market_sources.json", "type": "data"}],
            ),
            PlaybookMilestone(
                id="ci-m2",
                title="Feature Matrix & Differentiation Analysis",
                description="Build comparison matrix of capabilities, pricing, and architecture across targets.",
                order_idx=1,
                dependencies=["ci-m1"],
                assigned_agent="product-analyst",
                expected_deliverables=[{"name": "feature_comparison_matrix.md", "type": "document"}],
            ),
            PlaybookMilestone(
                id="ci-m3",
                title="Strategic Dossier & Recommendations",
                description="Synthesize key opportunities, threats, and executive takeaways into a final briefing.",
                order_idx=2,
                dependencies=["ci-m2"],
                assigned_agent="lead-strategist",
                expected_deliverables=[{"name": "market_intelligence_dossier.md", "type": "document"}],
            ),
        ],
    ),
]


class PlaybookRegistry:
    """
    In-memory and store-backed registry for Mission Playbooks.
    Provides discovery, validation, and real instantiation into executable Missions.
    """

    def __init__(self, store: MissionStore | None = None) -> None:
        self.store = store
        self._builtins: dict[str, MissionPlaybook] = {p.id: p for p in BUILTIN_PLAYBOOKS}

    def register_builtin(self, playbook: MissionPlaybook) -> None:
        self._builtins[playbook.id] = playbook

    def get_playbook(self, playbook_id: str) -> MissionPlaybook | None:
        if playbook_id in self._builtins:
            return self._builtins[playbook_id]
        if self.store and hasattr(self.store, "get_playbook"):
            return self.store.get_playbook(playbook_id)
        return None

    def list_playbooks(self, category: str | None = None) -> list[MissionPlaybook]:
        results: list[MissionPlaybook] = list(self._builtins.values())
        if self.store and hasattr(self.store, "list_playbooks"):
            custom_playbooks = self.store.list_playbooks()
            for cp in custom_playbooks:
                if not any(r.id == cp.id for r in results):
                    results.append(cp)
        if category:
            results = [p for p in results if p.category.lower() == category.lower()]
        return results

    def instantiate(
        self,
        playbook_id: str,
        store: MissionStore,
        workspace_id: str = "default",
        custom_objective: str | None = None,
        team_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Mission:
        """
        Instantiates a Playbook into a real, durable Mission with concrete Milestones.
        Ensures foreign-key integrity, dependency ordering, and zero fake state.
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook '{playbook_id}' not found in registry")

        params = params or {}
        # Render default objective with provided parameters
        objective = custom_objective
        if not objective:
            try:
                objective = playbook.default_objective.format(**params)
            except (KeyError, IndexError, ValueError):
                # Fallback if some params are missing: replace known ones
                rendered = playbook.default_objective
                for k, v in params.items():
                    rendered = rendered.replace(f"{{{k}}}", str(v))
                # Remove unformatted placeholders
                import re
                rendered = re.sub(r"\{[a-zA-Z0-9_]+\}", "the target", rendered)
                objective = rendered

        effective_team = team_name or playbook.team_name or "Default Workforce"

        # Prepare milestones for creation
        milestone_definitions: list[dict[str, Any]] = []
        milestone_id_map: dict[str, str] = {}

        # First generate stable real IDs for all milestones
        for idx, pm in enumerate(playbook.milestones):
            real_mid = f"ms-{uuid.uuid4().hex[:10]}"
            milestone_id_map[pm.id] = real_mid

        # Map dependencies using generated IDs
        for pm in playbook.milestones:
            real_mid = milestone_id_map[pm.id]
            resolved_deps = [milestone_id_map.get(dep, dep) for dep in pm.dependencies]
            milestone_definitions.append({
                "id": real_mid,
                "title": pm.title,
                "description": pm.description,
                "order_idx": pm.order_idx,
                "dependencies": resolved_deps,
                "assigned_agent": pm.assigned_agent,
                "metadata": {
                    "playbook_id": playbook.id,
                    "expected_deliverables": pm.expected_deliverables,
                    "verification_gate": pm.verification_gate,
                },
            })

        mission = store.create_mission(
            title=f"{playbook.title}",
            objective=objective,
            workspace_id=workspace_id,
            team_name=effective_team,
            milestones=milestone_definitions,
            metadata={
                "playbook_id": playbook.id,
                "playbook_version": playbook.version,
                "playbook_category": playbook.category,
                "instantiated_at": datetime.now(timezone.utc).isoformat(),
                "instantiation_params": params,
            },
        )
        return mission


# Global singleton instance
_GLOBAL_PLAYBOOK_REGISTRY: PlaybookRegistry | None = None


def get_playbook_registry(store: MissionStore | None = None) -> PlaybookRegistry:
    global _GLOBAL_PLAYBOOK_REGISTRY
    if _GLOBAL_PLAYBOOK_REGISTRY is None or (store and _GLOBAL_PLAYBOOK_REGISTRY.store is None):
        _GLOBAL_PLAYBOOK_REGISTRY = PlaybookRegistry(store=store)
    return _GLOBAL_PLAYBOOK_REGISTRY
