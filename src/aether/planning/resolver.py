"""
ContextResolver — Thin context resolution boundary over existing workspace, project, connection,
memory, and knowledge graph infrastructure (Phase A Macro-pass 1).
Truthfully resolves entities, captures provenance, detects ambiguity, and records retrieval failures
without hallucinating entities or exposing secrets.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
from typing import Any
import uuid

from aether.core.secrets import mask_secrets_deep
from aether.intelligence.models import UnifiedEvidence
from aether.intelligence.service import UnifiedIntelligenceService
from aether.planning.contracts import (
    ContextPack,
    ContextProvenance,
    EvidenceReference,
    IntentRequest,
    ResolutionState,
    ResolvedEntity,
)

logger = logging.getLogger(__name__)


class ContextResolver:
    """
    Resolves natural-language intent into a truthful ContextPack.
    Inspects workspace configuration, active project, connections, files,
    and unified memory/knowledge graph without side-effects or hallucinated entities.
    """

    def __init__(
        self,
        workspace: Any,
        intelligence_service: UnifiedIntelligenceService | None = None,
        connection_service: Any | None = None,
    ) -> None:
        self.workspace = workspace
        self._intelligence_service = intelligence_service
        self._connection_service = connection_service

    @property
    def intelligence_service(self) -> UnifiedIntelligenceService | None:
        if self._intelligence_service is not None:
            return self._intelligence_service
        if hasattr(self.workspace, "intelligence_service") and self.workspace.intelligence_service:
            return self.workspace.intelligence_service
        # Attempt to synthesize from workspace stores if available
        try:
            mem_store = getattr(self.workspace, "memory", None)
            kg_store = getattr(self.workspace, "knowledge_graph", None)
            if mem_store or kg_store:
                self._intelligence_service = UnifiedIntelligenceService(
                    workforce_memory_store=mem_store,
                    knowledge_graph_store=kg_store,
                    default_workspace_id=getattr(self.workspace, "name", "default"),
                )
                return self._intelligence_service
        except Exception as exc:
            logger.debug("Could not initialize UnifiedIntelligenceService from workspace: %s", exc)
        return None

    @property
    def connection_service(self) -> Any | None:
        if self._connection_service is not None:
            return self._connection_service
        return getattr(self.workspace, "connections", None)

    def resolve(self, intent: IntentRequest) -> ContextPack:
        """
        Executes deterministic context resolution for an IntentRequest.
        """
        ws_id = intent.workspace_id.strip()
        expected_ws = getattr(self.workspace, "name", getattr(self.workspace, "id", ws_id))

        resolved_entities: list[ResolvedEntity] = []
        evidence_refs: list[EvidenceReference] = []
        unresolved_refs: list[str] = []
        ambiguities: list[str] = []
        assumptions: list[str] = []
        retrieval_failures: list[str] = []

        # 1. Workspace scope check
        if ws_id != expected_ws and ws_id != "default" and expected_ws != "default":
            retrieval_failures.append(
                f"Workspace authorization mismatch: requested '{ws_id}' does not match active workspace '{expected_ws}'."
            )

        # 2. Project / Repository Resolution
        self._resolve_project_and_repo(
            intent=intent,
            resolved_entities=resolved_entities,
            evidence_refs=evidence_refs,
            unresolved_refs=unresolved_refs,
            ambiguities=ambiguities,
        )

        # 3. Connections Resolution (GitHub, Slack, Email, Calendar, etc.)
        self._resolve_connections(
            intent=intent,
            resolved_entities=resolved_entities,
            evidence_refs=evidence_refs,
            unresolved_refs=unresolved_refs,
            ambiguities=ambiguities,
            retrieval_failures=retrieval_failures,
        )

        # 4. Filesystem / Deliverables Reference Resolution
        self._resolve_files(
            intent=intent,
            resolved_entities=resolved_entities,
            evidence_refs=evidence_refs,
            unresolved_refs=unresolved_refs,
            ambiguities=ambiguities,
        )

        # 5. Client / External Stakeholder Resolution
        self._resolve_client(
            intent=intent,
            resolved_entities=resolved_entities,
            evidence_refs=evidence_refs,
            unresolved_refs=unresolved_refs,
            ambiguities=ambiguities,
            retrieval_failures=retrieval_failures,
        )

        # 6. Unified Intelligence (Workforce Memory + Knowledge Graph)
        self._resolve_intelligence(
            intent=intent,
            evidence_refs=evidence_refs,
            assumptions=assumptions,
            retrieval_failures=retrieval_failures,
        )

        # 7. Ambiguity extraction from prompt syntax
        self._detect_prompt_ambiguity(
            intent=intent,
            ambiguities=ambiguities,
            unresolved_refs=unresolved_refs,
        )

        # 8. Truthful evidence-derived confidence scoring
        confidence = self._compute_truthful_confidence(
            resolved_entities=resolved_entities,
            evidence_refs=evidence_refs,
            unresolved_refs=unresolved_refs,
            ambiguities=ambiguities,
            retrieval_failures=retrieval_failures,
        )

        prov = ContextProvenance(
            source_entity="ContextResolver",
            workspace_id=ws_id,
            locator=f"workspace:{expected_ws}",
            verification_status="verified" if not retrieval_failures else "inferred",
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            evidence_refs=[ev.id for ev in evidence_refs],
            metadata={
                "total_entities_evaluated": len(resolved_entities),
                "retrieval_failures_count": len(retrieval_failures),
                "ambiguities_count": len(ambiguities),
            },
        )

        return ContextPack(
            workspace_scope=ws_id,
            resolved_entities=resolved_entities,
            evidence_references=evidence_refs,
            confidence=confidence,
            unresolved_references=unresolved_refs,
            ambiguity=ambiguities,
            assumptions=assumptions,
            retrieval_failures=retrieval_failures,
            provenance=prov,
        )

    def _resolve_project_and_repo(
        self,
        intent: IntentRequest,
        resolved_entities: list[ResolvedEntity],
        evidence_refs: list[EvidenceReference],
        unresolved_refs: list[str],
        ambiguities: list[str],
    ) -> None:
        """Resolves project and repository references against workspace config."""
        prompt = intent.raw_input
        p_lower = prompt.lower()
        ws = self.workspace

        project_info = getattr(ws, "project_info", None)
        project_path = getattr(ws, "project_path", None)

        # Look for explicit repo or project keywords in prompt
        repo_mention = re.search(
            r"\b(?:repo|repository|progetto|project|codebase)\s+['\"]?([a-zA-Z0-9_\-\./]+)['\"]?",
            prompt,
            re.IGNORECASE,
        )
        branch_mention = re.search(
            r"\b(?:branch|ramo)\s+['\"]?([a-zA-Z0-9_\-\./]+)['\"]?",
            prompt,
            re.IGNORECASE,
        )

        if project_info and project_info.get("exists"):
            proj_name = project_info.get("name") or "active_project"
            proj_id = project_info.get("id") or proj_name
            ws_root = getattr(self.workspace, "root", None)
            rel_locator = proj_name
            if project_path and ws_root:
                try:
                    rel_locator = str(Path(project_path).relative_to(Path(ws_root)))
                except ValueError:
                    rel_locator = Path(project_path).name
            elif project_path:
                rel_locator = Path(project_path).name

            ev_id = f"ev-proj-{uuid.uuid4().hex[:6]}"
            evidence_refs.append(
                EvidenceReference(
                    id=ev_id,
                    source_type="project",
                    source_identifier=proj_id,
                    workspace=intent.workspace_id,
                    locator=rel_locator,
                    verification_status="verified",
                    excerpt=f"Connected project: {proj_name} at {rel_locator}",
                    metadata={"project_type": project_info.get("type", "local"), "relative_path": rel_locator},
                )
            )

            # Check if prompt targets a different project
            if repo_mention:
                target_repo = repo_mention.group(1).strip().strip("'\":,.;")
                if target_repo.lower() not in (proj_name.lower(), proj_id.lower(), "current", "this", "questo", "attivo"):
                    resolved_entities.append(
                        ResolvedEntity(
                            entity_type="repository",
                            canonical_id=None,
                            display_name=target_repo,
                            workspace_scope=intent.workspace_id,
                            resolution_state=ResolutionState.NOT_FOUND,
                            confidence=0.0,
                            evidence_references=[],
                            metadata={"reason": f"Project '{target_repo}' is not connected to workspace."},
                        )
                    )
                    unresolved_refs.append(f"repository:{target_repo}")
                    return

            resolved_entities.append(
                ResolvedEntity(
                    entity_type="project",
                    canonical_id=proj_id,
                    display_name=proj_name,
                    workspace_scope=intent.workspace_id,
                    resolution_state=ResolutionState.MATCHED,
                    confidence=0.95,
                    evidence_references=[ev_id],
                    metadata={"relative_path": rel_locator},
                )
            )

            # Inspect branch if mentioned
            if branch_mention:
                target_branch = branch_mention.group(1).strip()
                # Verify branch exists via git if possible
                branch_found = False
                if project_path and (Path(project_path) / ".git").exists():
                    try:
                        import subprocess
                        res = subprocess.run(
                            ["git", "branch", "--list", target_branch],
                            cwd=str(project_path),
                            capture_output=True,
                            text=True,
                            timeout=2.0,
                            check=False,
                        )
                        if target_branch in res.stdout:
                            branch_found = True
                    except Exception:
                        pass

                if branch_found:
                    ev_br = f"ev-branch-{uuid.uuid4().hex[:6]}"
                    evidence_refs.append(
                        EvidenceReference(
                            id=ev_br,
                            source_type="git",
                            source_identifier=target_branch,
                            workspace=intent.workspace_id,
                            locator=f"{p_str}:refs/heads/{target_branch}",
                            verification_status="verified",
                            excerpt=f"Verified local branch '{target_branch}'",
                        )
                    )
                    resolved_entities.append(
                        ResolvedEntity(
                            entity_type="branch",
                            canonical_id=target_branch,
                            display_name=target_branch,
                            workspace_scope=intent.workspace_id,
                            resolution_state=ResolutionState.MATCHED,
                            confidence=0.9,
                            evidence_references=[ev_br],
                        )
                    )
                else:
                    resolved_entities.append(
                        ResolvedEntity(
                            entity_type="branch",
                            canonical_id=None,
                            display_name=target_branch,
                            workspace_scope=intent.workspace_id,
                            resolution_state=ResolutionState.UNRESOLVED,
                            confidence=0.1,
                            evidence_references=[],
                            metadata={"reason": f"Branch '{target_branch}' not verified in git repository."},
                        )
                    )
                    unresolved_refs.append(f"branch:{target_branch}")

        else:
            # No project connected
            if repo_mention:
                target_repo = repo_mention.group(1).strip()
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="repository",
                        canonical_id=None,
                        display_name=target_repo,
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.NOT_FOUND,
                        confidence=0.0,
                        evidence_references=[],
                        metadata={"reason": "No project or repository connected to this workspace."},
                    )
                )
                unresolved_refs.append(f"repository:{target_repo}")

    def _resolve_connections(
        self,
        intent: IntentRequest,
        resolved_entities: list[ResolvedEntity],
        evidence_refs: list[EvidenceReference],
        unresolved_refs: list[str],
        ambiguities: list[str],
        retrieval_failures: list[str],
    ) -> None:
        """Resolves external integration connections mentioned in intent."""
        prompt = intent.raw_input.lower()
        known_providers = ["github", "slack", "email", "calendar", "telegram", "http", "notion"]

        detected_providers = [p for p in known_providers if p in prompt]
        if not detected_providers:
            return

        conn_service = self.connection_service
        if not conn_service:
            retrieval_failures.append("ConnectionService not available on workspace.")
            for p in detected_providers:
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="connection",
                        canonical_id=None,
                        display_name=p.capitalize(),
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.UNRESOLVED,
                        confidence=0.0,
                        metadata={"reason": "ConnectionService unavailable"},
                    )
                )
                unresolved_refs.append(f"connection:{p}")
            return

        try:
            conns = conn_service.list_connections(intent.workspace_id)
        except Exception as exc:
            retrieval_failures.append(f"Failed to query connections: {exc}")
            for p in detected_providers:
                unresolved_refs.append(f"connection:{p}")
            return

        conn_map: dict[str, list[Any]] = {}
        for c in conns:
            prov = getattr(c, "provider", "").lower()
            conn_map.setdefault(prov, []).append(c)

        for p in detected_providers:
            matches = conn_map.get(p, [])
            if len(matches) == 1:
                m = matches[0]
                status_val = getattr(getattr(m, "status", None), "value", str(getattr(m, "status", "unknown")))
                is_verified = (status_val == "verified")
                ev_id = f"ev-conn-{uuid.uuid4().hex[:6]}"
                evidence_refs.append(
                    EvidenceReference(
                        id=ev_id,
                        source_type="connection",
                        source_identifier=str(getattr(m, "id", p)),
                        workspace=intent.workspace_id,
                        locator=f"connections/{getattr(m, 'id', p)}",
                        verification_status="verified" if is_verified else "unverified",
                        excerpt=f"Provider {p.capitalize()} connection: {status_val}",
                        metadata=mask_secrets_deep({
                            "account_name": getattr(m, "account_name", ""),
                            "status": status_val,
                        }),
                    )
                )
                if not is_verified:
                    ambiguities.append(f"Connection '{p.capitalize()}' is in status '{status_val}' (not verified).")
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="connection",
                        canonical_id=str(getattr(m, "id", p)),
                        display_name=getattr(m, "account_name", p.capitalize()) or p.capitalize(),
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.MATCHED if is_verified else ResolutionState.UNRESOLVED,
                        confidence=0.9 if is_verified else 0.4,
                        evidence_references=[ev_id],
                        metadata={"provider": p, "status": status_val},
                    )
                )
            elif len(matches) > 1:
                ambiguities.append(f"Multiple {p.capitalize()} connections found ({len(matches)}).")
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="connection",
                        canonical_id=None,
                        display_name=p.capitalize(),
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.AMBIGUOUS,
                        confidence=0.4,
                        metadata={"match_count": len(matches)},
                    )
                )
            else:
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="connection",
                        canonical_id=None,
                        display_name=p.capitalize(),
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.NOT_FOUND,
                        confidence=0.0,
                        metadata={"reason": f"No {p.capitalize()} connection configured in workspace."},
                    )
                )
                unresolved_refs.append(f"connection:{p}")

    def _resolve_files(
        self,
        intent: IntentRequest,
        resolved_entities: list[ResolvedEntity],
        evidence_refs: list[EvidenceReference],
        unresolved_refs: list[str],
        ambiguities: list[str],
    ) -> None:
        """Resolves file paths or document names mentioned in intent."""
        prompt = intent.raw_input
        # Find explicit filenames like doc.txt, main.py, data/report.pdf
        file_candidates = re.findall(r"\b([a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]{1,5})\b", prompt)
        if not file_candidates:
            return

        ws_root = getattr(self.workspace, "root", Path("."))
        proj_root = getattr(self.workspace, "project_path", None)
        files_dir = getattr(self.workspace, "files_dir", ws_root / "files")

        for f_name in file_candidates:
            # Check if file exists in project or files_dir
            found_path: Path | None = None
            search_paths = []
            if proj_root:
                search_paths.append(Path(proj_root))
            if files_dir:
                search_paths.append(Path(files_dir))
            search_paths.append(Path(ws_root))

            for s_path in search_paths:
                candidate = s_path / f_name
                if candidate.exists() and candidate.is_file():
                    found_path = candidate.resolve()
                    break

            if found_path:
                rel_file_locator = f_name
                ws_root = getattr(self.workspace, "root", None)
                if ws_root:
                    try:
                        rel_file_locator = str(found_path.relative_to(Path(ws_root)))
                    except ValueError:
                        rel_file_locator = found_path.name
                else:
                    rel_file_locator = found_path.name

                ev_id = f"ev-file-{uuid.uuid4().hex[:6]}"
                evidence_refs.append(
                    EvidenceReference(
                        id=ev_id,
                        source_type="file",
                        source_identifier=rel_file_locator,
                        workspace=intent.workspace_id,
                        locator=rel_file_locator,
                        verification_status="verified",
                        excerpt=f"File verified on disk ({found_path.stat().st_size} bytes)",
                        metadata={"size_bytes": found_path.stat().st_size, "relative_path": rel_file_locator},
                    )
                )
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="file",
                        canonical_id=rel_file_locator,
                        display_name=f_name,
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.MATCHED,
                        confidence=0.95,
                        evidence_references=[ev_id],
                        metadata={"relative_path": rel_file_locator},
                    )
                )
            else:
                # If file does not exist, check whether it is an output/target or missing input
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="file",
                        canonical_id=None,
                        display_name=f_name,
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.UNRESOLVED,
                        confidence=0.2,
                        metadata={"reason": f"File '{f_name}' does not exist on disk."},
                    )
                )
                unresolved_refs.append(f"file:{f_name}")

    def _resolve_client(
        self,
        intent: IntentRequest,
        resolved_entities: list[ResolvedEntity],
        evidence_refs: list[EvidenceReference],
        unresolved_refs: list[str],
        ambiguities: list[str],
        retrieval_failures: list[str],
    ) -> None:
        """Resolves client or organization references mentioned in intent."""
        prompt = intent.raw_input
        # Look for explicit client patterns: "client X", "cliente Acme", "customer Y"
        client_match = re.search(
            r"\b(?:client|cliente|customer|committente)\s+([a-zA-Z0-9_\-]+)",
            prompt,
            re.IGNORECASE,
        )
        if not client_match:
            return

        client_name = client_match.group(1).strip()
        client_store = getattr(self.workspace, "client_store", None)
        if not client_store:
            # No client store available
            resolved_entities.append(
                ResolvedEntity(
                    entity_type="client",
                    canonical_id=None,
                    display_name=client_name,
                    workspace_scope=intent.workspace_id,
                    resolution_state=ResolutionState.AMBIGUOUS,
                    confidence=0.2,
                    metadata={"reason": "No client directory or client store active in workspace."},
                )
            )
            ambiguities.append(f"Client '{client_name}' reference cannot be verified without active client store.")
            return

        try:
            matches = []
            if hasattr(client_store, "search_clients"):
                matches = client_store.search_clients(client_name)
            elif hasattr(client_store, "list_clients"):
                all_c = client_store.list_clients()
                matches = [c for c in all_c if client_name.lower() in getattr(c, "name", "").lower()]

            if len(matches) == 1:
                c = matches[0]
                c_id = getattr(c, "id", client_name)
                c_display = getattr(c, "name", client_name)
                ev_id = f"ev-client-{uuid.uuid4().hex[:6]}"
                evidence_refs.append(
                    EvidenceReference(
                        id=ev_id,
                        source_type="client",
                        source_identifier=str(c_id),
                        workspace=intent.workspace_id,
                        locator=f"clients/{c_id}",
                        verification_status="verified",
                        excerpt=f"Matched client: {c_display}",
                    )
                )
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="client",
                        canonical_id=str(c_id),
                        display_name=c_display,
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.MATCHED,
                        confidence=0.9,
                        evidence_references=[ev_id],
                    )
                )
            elif len(matches) > 1:
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="client",
                        canonical_id=None,
                        display_name=client_name,
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.AMBIGUOUS,
                        confidence=0.4,
                        metadata={"matches": [getattr(m, "name", "") for m in matches]},
                    )
                )
                ambiguities.append(f"Multiple clients match '{client_name}'.")
            else:
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="client",
                        canonical_id=None,
                        display_name=client_name,
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.NOT_FOUND,
                        confidence=0.0,
                        metadata={"reason": f"Client '{client_name}' not found in client store."},
                    )
                )
                unresolved_refs.append(f"client:{client_name}")

        except Exception as exc:
            retrieval_failures.append(f"Failed to query client store: {exc}")
            unresolved_refs.append(f"client:{client_name}")

    def _resolve_intelligence(
        self,
        intent: IntentRequest,
        evidence_refs: list[EvidenceReference],
        assumptions: list[str],
        retrieval_failures: list[str],
    ) -> None:
        """Retrieves semantic memory and knowledge graph context without throwing."""
        intel_service = self.intelligence_service
        if not intel_service:
            return

        try:
            result = intel_service.retrieve_unified_context(
                workspace_id=intent.workspace_id,
                task_instruction=intent.raw_input,
                max_items=4,
            )
            for ev in result.evidence:
                st = ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type)
                v_status = getattr(ev.provenance, "verification_status", "inferred")
                ev_ref = EvidenceReference(
                    id=f"ev-intel-{ev.id[:8]}",
                    source_type=st,
                    source_identifier=ev.id,
                    workspace=intent.workspace_id,
                    locator=f"{st}:{ev.id}",
                    verification_status=v_status,
                    excerpt=ev.summary[:200] if ev.summary else ev.title,
                    metadata={"score": ev.score, "confidence": ev.confidence},
                )
                evidence_refs.append(ev_ref)

                if v_status in ("inferred", "unverified"):
                    assumptions.append(f"Inferred context from workforce memory: {ev.title}")

        except Exception as exc:
            logger.warning("UnifiedIntelligenceService retrieval failure: %s", exc)
            retrieval_failures.append(f"Intelligence retrieval failed: {exc}")

    def _detect_prompt_ambiguity(
        self,
        intent: IntentRequest,
        ambiguities: list[str],
        unresolved_refs: list[str],
    ) -> None:
        """Detects underspecified pronouns or vague instructions."""
        p_lower = intent.raw_input.lower().strip()
        vague_phrases = [
            ("do it", "Vague instruction 'do it' lacks explicit action or goal."),
            ("take care of this", "Vague instruction 'take care of this' lacks concrete deliverables."),
            ("fix that", "Instruction 'fix that' lacks target file or error reference."),
            ("fallo", "Istruzione generica 'fallo' priva di obiettivo esplicito."),
            ("pensaci tu", "Istruzione generica 'pensaci tu' senza criteri di completamento."),
        ]
        for phrase, reason in vague_phrases:
            if p_lower == phrase or p_lower.startswith(phrase + " "):
                ambiguities.append(reason)

    def _compute_truthful_confidence(
        self,
        resolved_entities: list[ResolvedEntity],
        evidence_refs: list[EvidenceReference],
        unresolved_refs: list[str],
        ambiguities: list[str],
        retrieval_failures: list[str],
    ) -> float:
        """
        Derives an honest, evidence-based confidence score between 0.0 and 0.95.
        Penalizes unresolved entities, ambiguities, and retrieval failures.
        Never outputs a default fake 1.0.
        """
        # Baseline start: 0.5 (neutral prior)
        score = 0.5

        if resolved_entities:
            matched_count = sum(1 for e in resolved_entities if e.resolution_state == ResolutionState.MATCHED)
            total_count = len(resolved_entities)
            entity_ratio = matched_count / total_count
            score = 0.4 + (entity_ratio * 0.4)  # 0.4 to 0.8
        elif evidence_refs:
            score = 0.6

        # Evidence bonuses
        verified_ev = sum(1 for ev in evidence_refs if ev.verification_status in ("verified", "user_stated"))
        if verified_ev > 0:
            score = min(0.95, score + min(0.15, verified_ev * 0.05))

        # Penalties
        if retrieval_failures:
            score -= 0.25 * len(retrieval_failures)
        if ambiguities:
            score -= 0.15 * len(ambiguities)
        if unresolved_refs:
            score -= 0.15 * len(unresolved_refs)

        # Clamping: strictly between 0.05 and 0.95
        return round(max(0.05, min(0.95, score)), 3)
