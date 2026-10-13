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
        valid_ws_identifiers = {
            expected_ws,
            getattr(self.workspace, "id", ""),
            getattr(self.workspace, "name", ""),
            getattr(getattr(self.workspace, "root", None), "name", ""),
        } - {"", None}

        resolved_entities: list[ResolvedEntity] = []
        evidence_refs: list[EvidenceReference] = []
        unresolved_refs: list[str] = []
        ambiguities: list[str] = []
        assumptions: list[str] = []
        retrieval_failures: list[str] = []

        # 1. Workspace scope check
        if ws_id not in valid_ws_identifiers and ws_id != "default" and expected_ws != "default":
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

        ADJECTIVE_TOKENS = {
            "locale", "local", "corrente", "attuale", "esistente",
            "questo", "mio", "nostro", "this", "current", "attivo"
        }

        # Look for explicit repo or project keywords in prompt, skipping optional adjectives like 'locale', 'local', etc.
        repo_mention = re.search(
            r"\b(?:repo|repository|progetto|project|codebase)\s+(?:(?:locale|local|corrente|attuale|esistente|questo|mio)\s+)?[`'\"]?([a-zA-Z0-9_\-\./]+)[`'\"]?",
            prompt,
            re.IGNORECASE,
        )
        # Also look for explicit directory paths like /tmp/... or /Users/...
        abs_path_mention = (
            re.search(r"[`'\"\s\(](/[a-zA-Z0-9_\-\./]+)", prompt)
            # Windows drive paths: quoted (may contain spaces) or bare, with either kind of separator
            or re.search(r"[`'\"]([A-Za-z]:[\\/][^`'\"]+)[`'\"]", prompt)
            or re.search(r"(?:^|[`'\"\s\(])([A-Za-z]:[\\/][^\s`'\"\(\)<>|?*]*)", prompt)
        )
        branch_mention = re.search(
            r"\b(?:branch|ramo)\s+[`'\"]?([a-zA-Z0-9_\-\./]+)[`'\"]?",
            prompt,
            re.IGNORECASE,
        )

        # Multi-stage resolution for target_repo:
        # 1. intent.action_args.get("project_path") if provided and is an existing directory
        # 2. abs_path_mention if it resolves to an existing directory
        # 3. repo_mention if not an adjective token
        target_repo: str | None = None
        target_path: Path | None = None

        if intent.action_args and intent.action_args.get("project_path"):
            cand = Path(intent.action_args["project_path"]).resolve()
            if cand.is_dir():
                target_repo = str(cand)
                target_path = cand

        if not target_path and abs_path_mention:
            cand = Path(abs_path_mention.group(1).strip().strip("`'\":,.;")).resolve()
            if cand.is_dir():
                target_repo = str(cand)
                target_path = cand

        if not target_path and repo_mention:
            raw_repo = repo_mention.group(1).strip().strip("`'\":,.;")
            if raw_repo.lower() not in ADJECTIVE_TOKENS:
                cand = Path(raw_repo).resolve()
                if cand.is_dir():
                    target_repo = str(cand)
                    target_path = cand
                else:
                    target_repo = raw_repo

        if target_path and target_path.is_dir():
            ev_id = f"ev-repo-{uuid.uuid4().hex[:6]}"
            evidence_refs.append(
                EvidenceReference(
                    id=ev_id,
                    source_type="git" if (target_path / ".git").exists() else "filesystem",
                    source_identifier=str(target_path),
                    workspace=intent.workspace_id,
                    locator=str(target_path),
                    verification_status="verified",
                    excerpt=f"Verified local repository path at {target_path}",
                    metadata={"path": str(target_path)},
                )
            )
            resolved_entities.append(
                ResolvedEntity(
                    entity_type="repository",
                    canonical_id=str(target_path),
                    display_name=target_path.name,
                    workspace_scope=intent.workspace_id,
                    resolution_state=ResolutionState.MATCHED,
                    confidence=0.95,
                    evidence_references=[ev_id],
                    metadata={"path": str(target_path)},
                )
            )
            self._target_repo_path = target_path
            return

        if project_info and project_info.get("exists"):
            proj_name = project_info.get("name") or "active_project"
            proj_id = project_info.get("id") or proj_name
            ws_root = getattr(self.workspace, "root", None)
            rel_locator = proj_name
            if project_path and ws_root:
                try:
                    rel_locator = Path(project_path).relative_to(Path(ws_root)).as_posix()
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

            # Check if prompt targets a different project that does not exist
            if target_repo and target_repo.lower() not in (proj_name.lower(), proj_id.lower(), "current", "this", "questo", "attivo"):
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
                            locator=f"{rel_locator}:refs/heads/{target_branch}",
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
            # No connected project in workspace, and explicit repo path did not exist on disk
            if target_repo:
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
        known_providers = ["github", "slack", "email", "calendar", "telegram", "notion"]

        detected_providers = [
            p for p in known_providers
            if re.search(r"\b" + re.escape(p) + r"\b", prompt)
        ]
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
                is_configured = (status_val in ("verified", "configured"))
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
                if not is_configured:
                    ambiguities.append(f"Connection '{p.capitalize()}' is in status '{status_val}'.")
                resolved_entities.append(
                    ResolvedEntity(
                        entity_type="connection",
                        canonical_id=str(getattr(m, "id", p)),
                        display_name=getattr(m, "account_name", p.capitalize()) or p.capitalize(),
                        workspace_scope=intent.workspace_id,
                        resolution_state=ResolutionState.MATCHED if is_configured else ResolutionState.UNRESOLVED,
                        confidence=0.9 if is_verified else (0.75 if is_configured else 0.4),
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

    _KNOWN_FILE_EXTENSIONS = frozenset({
        "py", "pyi", "ts", "tsx", "js", "jsx", "mjs", "json", "md", "txt", "html", "css", "scss", "rs", "go", "java",
        "kt", "swift", "c", "cc", "cpp", "h", "hpp", "cs", "rb", "php", "sh", "yaml", "yml", "toml", "ini", "cfg", "csv",
        "tsv", "xml", "sql", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "png", "jpg", "jpeg", "svg", "zip", "log",
        "lock", "env",
    })
    # Product names that look like "file.ext" but are not files.
    _NOT_FILES = frozenset({"node.js", "next.js", "vue.js", "react.js", "express.js", "three.js", "d3.js", "nuxt.js", "nest.js"})

    @classmethod
    def _looks_like_file_reference(cls, token: str) -> bool:
        """True only for plausible file references: not version numbers, not product names, known extension."""
        tok = token.strip()
        if not tok or tok.lower() in cls._NOT_FILES:
            return False
        name = tok.rsplit("/", 1)[-1]
        if "." not in name:
            return False
        stem, ext = name.rsplit(".", 1)
        if not stem or stem.replace(".", "").isdigit():  # 3.14, 1.2.3
            return False
        return ext.lower() in cls._KNOWN_FILE_EXTENSIONS

    @staticmethod
    def _safe_join(base: Path, rel: str) -> Path | None:
        """Joins ``rel`` under ``base`` and refuses anything that resolves outside it (.., absolute paths)."""
        try:
            base_resolved = base.resolve()
            target = (base_resolved / rel).resolve()
        except Exception:
            return None
        if target == base_resolved or base_resolved in target.parents:
            return target
        return None

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
        # Strip email addresses and URLs so email domains and web hosts are not mistaken for local files
        prompt_clean = re.sub(r'[\w\.-]+@[\w\.-]+', '', prompt)
        prompt_clean = re.sub(r'https?://[^\s]+', '', prompt_clean)
        # Find explicit filenames like doc.txt, main.py, data/report.pdf, stripping trailing punctuation
        raw_candidates = re.findall(r"(?<![\w/.\-])([a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]{1,5})(?![\w])", prompt_clean)
        file_candidates: list[str] = []
        for cand in raw_candidates:
            cand = cand.rstrip(",;.:")
            if self._looks_like_file_reference(cand) and cand not in file_candidates:
                file_candidates.append(cand)
        if intent.action_args and intent.action_args.get("context_files"):
            for cf in intent.action_args["context_files"]:
                # Keep the path identity: a/utils.py and b/utils.py are different files.
                clean_cf = str(cf).strip().replace("\\", "/")
                if clean_cf and clean_cf not in file_candidates:
                    file_candidates.append(clean_cf)

        if not file_candidates:
            return

        ws_root = getattr(self.workspace, "root", None) or Path(".")
        proj_root = getattr(self.workspace, "project_path", None)
        files_dir = getattr(self.workspace, "files_dir", None) or (ws_root / "files")

        for f_name in file_candidates:
            # Check if file exists in project or files_dir
            found_path: Path | None = None
            search_paths = []
            if getattr(self, "_target_repo_path", None):
                search_paths.append(Path(self._target_repo_path))
            # Also check if project_path was supplied in intent constraints or args
            if intent.action_args and intent.action_args.get("project_path"):
                p_arg = Path(intent.action_args["project_path"]).resolve()
                if p_arg not in search_paths and p_arg.is_dir():
                    search_paths.append(p_arg)
            if proj_root:
                search_paths.append(Path(proj_root))
            if files_dir:
                search_paths.append(Path(files_dir))
            search_paths.append(Path(ws_root))

            for s_path in search_paths:
                candidate = self._safe_join(Path(s_path), f_name)
                if candidate is not None and candidate.exists() and candidate.is_file():
                    found_path = candidate
                    break

            if found_path:
                rel_file_locator = f_name
                if getattr(self, "_target_repo_path", None):
                    try:
                        rel_file_locator = found_path.relative_to(Path(self._target_repo_path)).as_posix()
                    except ValueError:
                        rel_file_locator = found_path.name
                else:
                    ws_root_path = getattr(self.workspace, "root", None)
                    if ws_root_path:
                        try:
                            rel_file_locator = found_path.relative_to(Path(ws_root_path)).as_posix()
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
                # File does not exist on disk.
                # Check whether the intent explicitly instructs creating this file as a new deliverable,
                # versus modifying, reading, fixing, or attaching a missing file.
                p_lower = prompt.lower()
                f_escaped = re.escape(f_name.lower())

                # 1. Check for explicit read / modify / fix / attach directives targeting this file or in prompt
                modify_patterns = [
                    rf"\b(?:modifica|modificare|modify|update|aggiorna|aggiornare|edit)\b.*?\b{f_escaped}\b",
                    rf"\b(?:risolvi|correggi|fix|debug|fixa)\b.*?\b{f_escaped}\b",
                    rf"\b(?:bug|errore|issue|problem)\b.*?\b(?:in|su|nel\s+file)\b.*?\b{f_escaped}\b",
                    rf"\b(?:leggi|leggere|read|riassumi|riassumere|summarize|apri|open|mostra|show)\b.*?\b{f_escaped}\b",
                    rf"\b(?:allega|allegare|attach|attaching|invia|manda|send)\b.*?\b{f_escaped}\b",
                ]
                has_modify_or_read_directive = any(re.search(pat, p_lower) for pat in modify_patterns)

                # 2. Check for explicit creation directive targeting this file
                create_patterns = [
                    rf"\b(?:crea|creare|create|creating|scrivi|write|genera|generate|build)\b.*?\b{f_escaped}\b",
                    rf"\b(?:nuovo\s+file|new\s+file|file\s+nuovo)\b.*?\b{f_escaped}\b",
                ]
                has_explicit_creation = any(re.search(pat, p_lower) for pat in create_patterns)

                # Word-boundary check for general creation words (avoiding substrings like 'add' in 'address')
                general_creation = bool(re.search(r"\b(?:crea\s+un\s+nuovo\s+file|crea\s+file\s+nuovo|crea\s+un\s+file\s+nuovo|create\s+new\s+file|nuovo\s+file|new\s+file|file\s+nuovo)\b", p_lower))

                is_target_output = False
                if has_explicit_creation and not has_modify_or_read_directive:
                    is_target_output = True
                elif general_creation and not has_modify_or_read_directive:
                    is_target_output = True

                if is_target_output:
                    resolved_entities.append(
                        ResolvedEntity(
                            entity_type="file",
                            canonical_id=f"target:{f_name}",
                            display_name=f_name,
                            workspace_scope=intent.workspace_id,
                            resolution_state=ResolutionState.MATCHED,
                            confidence=0.6,
                            metadata={"target_to_create": True, "reason": f"File '{f_name}' is a target deliverable to be created."},
                        )
                    )
                else:
                    is_ambiguous = not has_modify_or_read_directive and not has_explicit_creation
                    res_state = ResolutionState.AMBIGUOUS if is_ambiguous else ResolutionState.UNRESOLVED
                    reason_msg = (
                        f"File '{f_name}' does not exist on disk and was requested for reading/modification."
                        if has_modify_or_read_directive
                        else f"File '{f_name}' does not exist on disk."
                    )
                    resolved_entities.append(
                        ResolvedEntity(
                            entity_type="file",
                            canonical_id=None,
                            display_name=f_name,
                            workspace_scope=intent.workspace_id,
                            resolution_state=res_state,
                            confidence=0.1,
                            metadata={"reason": reason_msg, "missing": True},
                        )
                    )
                    unresolved_refs.append(f"file:{f_name}")
                    if is_ambiguous:
                        ambiguities.append(f"File '{f_name}' is referenced but does not exist and is not explicitly marked for creation.")
                    else:
                        ambiguities.append(f"Referenced file '{f_name}' does not exist on disk.")

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
            # A "file to create" is an intention, not something resolved against evidence: it neither raises
            # nor lowers confidence in what could actually be verified.
            verifiable = [e for e in resolved_entities if not (e.metadata or {}).get("target_to_create")]
            if verifiable:
                matched_count = sum(1 for e in verifiable if e.resolution_state == ResolutionState.MATCHED)
                entity_ratio = matched_count / len(verifiable)
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
