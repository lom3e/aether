"""
Authoritative Aether MCP Server implementation (Macro 1).
Provides standard Model Context Protocol (MCP 2024-11-05) over stdio transport.
Exposes read-only workspace context, persistent memory, tasks, and calendar events
to developer environments (Google Antigravity, VS Code, Cursor).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from aether.workspace.workspace import Workspace

# Configure logger to output STRICTLY to stderr so stdout remains 100% clean for JSON-RPC framing
logger = logging.getLogger("aether.mcp")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("[Aether-MCP] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)


class AetherMCPServer:
    """
    Standard Model Context Protocol (MCP) Server for Aether.
    Bound strictly to an authorized Workspace instance.
    """

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "aether-mcp"
    SERVER_VERSION = "1.7.0"

    def __init__(self, workspace: Workspace) -> None:
        if not workspace:
            raise ValueError("AetherMCPServer requires an active, initialized Workspace.")
        self.workspace = workspace
        self._tools = self._init_tool_definitions()

    # ---------------------------------------------------------------------------
    # Tool Schemas
    # ---------------------------------------------------------------------------

    def _init_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "aether_search_memory",
                "description": (
                    "Search persistent workforce intelligence and memory in Aether. "
                    "Supports filtering across 8 structured memory categories: "
                    "fact, preference, decision, process, person, project, outcome, lesson. "
                    "Returns factual content, verified category, and audit provenance."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query keywords to find in memories (e.g. 'università', 'deadline', 'architettura').",
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "fact",
                                "preference",
                                "decision",
                                "process",
                                "person",
                                "project",
                                "outcome",
                                "lesson",
                            ],
                            "description": "Optional category filter. Omit to search across all memory categories.",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "description": "Maximum number of memory items to return (1 to 50).",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "aether_get_project_context",
                "description": (
                    "Retrieve the active project context associated with the Aether workspace. "
                    "Returns project directory details, linked deliverables, output artifacts, "
                    "and project-specific persistent memories."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Optional project identifier or name. Defaults to the primary project configured in workspace.",
                        },
                    },
                },
            },
            {
                "name": "aether_list_tasks",
                "description": (
                    "List coordinated tasks and background operations in Aether. "
                    "Returns status, progress percentage, current step, and result summaries. "
                    "Does not mutate or delete tasks."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["pending", "running", "completed", "failed", "cancelled"],
                            "description": "Filter tasks by execution status.",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 20,
                            "description": "Maximum number of tasks to return.",
                        },
                    },
                },
            },
            {
                "name": "aether_list_calendar_events",
                "description": (
                    "Query calendar events across connected accounts (e.g. Google Calendar multi-calendar, "
                    "university timetable feeds, personal schedules). "
                    "Returns titles, local start/end times, locations, and descriptions. "
                    "Read-only query: does not create or modify events."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "time_min": {
                            "type": "string",
                            "description": "Start of time range in ISO-8601 format (e.g. '2026-10-12T00:00:00Z').",
                        },
                        "time_max": {
                            "type": "string",
                            "description": "End of time range in ISO-8601 format (e.g. '2026-10-12T23:59:59Z').",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search text filter to match specific titles or locations (e.g. 'lezione', 'esame').",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 25,
                            "description": "Maximum number of events to retrieve.",
                        },
                    },
                },
            },
        ]

    # ---------------------------------------------------------------------------
    # Tool Implementations (Strict Read-Only)
    # ---------------------------------------------------------------------------

    def _execute_search_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return {"error": "Query string is required for aether_search_memory."}

        category_filter = arguments.get("category")
        limit = min(max(int(arguments.get("limit", 10)), 1), 50)

        mem_store = getattr(self.workspace, "memory", None)
        if not mem_store:
            return {
                "query": query,
                "results_count": 0,
                "memories": [],
                "message": "Memory store not initialized in workspace.",
            }

        categories = [category_filter] if category_filter else None

        # 1. First probe ranked search
        matched_memories = []
        try:
            search_tuples = mem_store.search_memories(
                workspace_id=self.workspace.id,
                query=query,
                categories=categories,
                limit=limit,
            )
            for m, score in search_tuples:
                matched_memories.append(self._format_memory(m, score=score))
        except Exception as exc:
            logger.warning("Ranked memory search failed, falling back to listing: %s", exc)

        # 2. Fallback to list_memories query if no ranked results found
        if not matched_memories:
            try:
                listed = mem_store.list_memories(
                    workspace_id=self.workspace.id,
                    categories=categories,
                    query=query,
                    limit=limit,
                )
                for m in listed:
                    matched_memories.append(self._format_memory(m))
            except Exception as exc:
                logger.warning("Listing memories failed: %s", exc)

        return {
            "workspace_id": self.workspace.id,
            "workspace_name": self.workspace.name,
            "query": query,
            "category_filter": category_filter,
            "results_count": len(matched_memories),
            "search_mode": "sqlite_token_match",
            "notes": "Searched persistent workforce memory store. Semantic vector retrieval is enabled when embedding provider is active.",
            "memories": matched_memories,
        }

    def _format_memory(self, memory: Any, score: float | None = None) -> dict[str, Any]:
        category_val = memory.category.value if hasattr(memory.category, "value") else str(memory.category)
        prov = memory.provenance.to_dict() if hasattr(memory.provenance, "to_dict") else {}
        # Sanitize provenance: never expose credentials or internal hashes
        prov_clean = {
            "source_entity": prov.get("source_entity", "workspace"),
            "author_agent": prov.get("author_agent"),
            "verification_status": prov.get("verification_status", "verified"),
            "evidence_excerpt": prov.get("evidence_excerpt"),
        }
        res: dict[str, Any] = {
            "id": memory.id,
            "category": category_val,
            "summary": memory.summary,
            "content": memory.content,
            "tags": list(memory.tags or []),
            "provenance": prov_clean,
        }
        if score is not None:
            res["score"] = round(float(score), 3)
        return res

    def _execute_get_project_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_name = arguments.get("project_name")
        p_info = getattr(self.workspace, "project_info", None)
        p_path = getattr(self.workspace, "project_path", None)

        # Deliverables collector
        deliverables = []
        try:
            from aether.personal.context import collect_workspace_deliverables
            deliv_objects = collect_workspace_deliverables(self.workspace, limit=10)
            for d in deliv_objects:
                deliverables.append({
                    "id": d.id,
                    "title": d.title,
                    "source": d.source,
                    "file_path": d.file_path,
                    "file_type": d.file_type,
                    "file_size_bytes": d.file_size_bytes,
                    "summary": d.summary,
                    "created_at": d.created_at,
                })
        except Exception as exc:
            logger.debug("Deliverable collection encountered error: %s", exc)

        # Project memories
        project_memories = []
        mem_store = getattr(self.workspace, "memory", None)
        if mem_store:
            try:
                mems = mem_store.list_memories(
                    workspace_id=self.workspace.id,
                    category="project",
                    limit=10,
                )
                for m in mems:
                    project_memories.append(self._format_memory(m))
            except Exception as exc:
                logger.debug("Project memories listing error: %s", exc)

        # Inspect local files in workspace files_dir
        local_files = []
        if hasattr(self.workspace, "files_dir") and self.workspace.files_dir.exists():
            try:
                for entry in sorted(self.workspace.files_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)[:15]:
                    if not entry.name.startswith("."):
                        local_files.append({
                            "name": entry.name,
                            "size_bytes": entry.stat().st_size,
                            "type": entry.suffix.lstrip(".") or "file",
                        })
            except Exception as exc:
                logger.debug("Files enumeration error: %s", exc)

        return {
            "workspace_id": self.workspace.id,
            "workspace_name": self.workspace.name,
            "project_connected": bool(p_path or p_info),
            "project_info": p_info,
            "project_path": str(p_path) if p_path else None,
            "query_requested": project_name,
            "deliverables_count": len(deliverables),
            "deliverables": deliverables,
            "workspace_files": local_files,
            "project_memories": project_memories,
        }

    def _execute_list_tasks(self, arguments: dict[str, Any]) -> dict[str, Any]:
        status_filter = arguments.get("status")
        limit = min(max(int(arguments.get("limit", 20)), 1), 100)

        tasks = []
        p_store = getattr(self.workspace, "personal_store", None)
        if not p_store and hasattr(self.workspace, "personal"):
            p_store = getattr(self.workspace.personal, "store", None)

        if p_store:
            try:
                raw_tasks = p_store.list_tasks(
                    workspace_id=self.workspace.id,
                    status=status_filter,
                    limit=limit,
                )
                for t in raw_tasks:
                    tasks.append({
                        "id": t.id,
                        "title": t.title,
                        "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                        "tier": t.tier.value if hasattr(t.tier, "value") else str(t.tier),
                        "progress_percent": t.progress_percent,
                        "current_step": t.current_step,
                        "result_summary": t.result_summary,
                        "deliverable_path": t.deliverable_path,
                        "created_at": t.created_at,
                        "updated_at": t.updated_at,
                    })
            except Exception as exc:
                logger.warning("Personal tasks listing error: %s", exc)

        return {
            "workspace_id": self.workspace.id,
            "filter_status": status_filter,
            "total_tasks": len(tasks),
            "tasks": tasks,
        }

    def _execute_list_calendar_events(self, arguments: dict[str, Any]) -> dict[str, Any]:
        time_min = arguments.get("time_min")
        time_max = arguments.get("time_max")
        query = arguments.get("query")
        limit = min(max(int(arguments.get("limit", 25)), 1), 100)

        conn_service = getattr(self.workspace, "connections", None)
        if not conn_service:
            return {
                "connected": False,
                "provider": "google_calendar",
                "events_count": 0,
                "events": [],
                "message": "Connections service unavailable in workspace.",
            }

        gconn = conn_service.get_connection(self.workspace.id, "google_calendar")
        has_credentials = bool(
            gconn and (
                gconn.auth_metadata.get("access_token")
                or gconn.auth_metadata.get("refresh_token")
            )
        )

        if not gconn or not has_credentials:
            return {
                "connected": False,
                "provider": "google_calendar",
                "events_count": 0,
                "events": [],
                "message": "Google Calendar connection is not configured or authorized in this workspace.",
            }

        try:
            gconnector = conn_service.get_google_calendar_connector(self.workspace.id)
            raw_events = gconnector.list_events(
                limit=limit,
                time_min=time_min,
                time_max=time_max,
                query=query,
            )

            # Strict field sanitization: never expose tokens or private connector metadata
            sanitized_events = []
            for ev in raw_events:
                sanitized_events.append({
                    "id": ev.get("id"),
                    "title": ev.get("title") or ev.get("summary") or "Untitled Event",
                    "start_time": ev.get("start_time"),
                    "end_time": ev.get("end_time"),
                    "is_all_day": ev.get("is_all_day", False),
                    "location": ev.get("location") or "",
                    "description": ev.get("description") or "",
                    "calendar_summary": ev.get("calendar_summary") or "",
                    "calendar_id": ev.get("calendar_id"),
                })

            return {
                "connected": True,
                "provider": "google_calendar",
                "events_count": len(sanitized_events),
                "events": sanitized_events,
            }
        except Exception as exc:
            logger.error("Failed to query Google Calendar via MCP: %s", exc)
            return {
                "connected": False,
                "provider": "google_calendar",
                "error": str(exc),
                "events_count": 0,
                "events": [],
            }

    # ---------------------------------------------------------------------------
    # JSON-RPC 2.0 Dispatcher
    # ---------------------------------------------------------------------------

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any] | None:
        """
        Dispatches incoming JSON-RPC 2.0 message according to MCP protocol specifications.
        Returns a response dict, or None if the message is a notification.
        """
        method = req.get("method", "")
        req_id = req.get("id")

        logger.debug("Received MCP method: %s (id: %s)", method, req_id)

        # 1. Initial Handshake: initialize
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": self.SERVER_NAME,
                        "version": self.SERVER_VERSION,
                    },
                },
            }

        # 2. Notifications: no response returned
        if method in ("notifications/initialized", "$/cancelRequest"):
            logger.info("Handled MCP notification: %s", method)
            return None

        # 3. Liveness: ping
        if method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {},
            }

        # 4. List Tools: tools/list
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self._tools,
                },
            }

        # 5. Call Tool: tools/call
        if method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            try:
                if tool_name == "aether_search_memory":
                    data = self._execute_search_memory(arguments)
                elif tool_name == "aether_get_project_context":
                    data = self._execute_get_project_context(arguments)
                elif tool_name == "aether_list_tasks":
                    data = self._execute_list_tasks(arguments)
                elif tool_name == "aether_list_calendar_events":
                    data = self._execute_list_calendar_events(arguments)
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Tool '{tool_name}' not found.",
                        },
                    }

                is_err = "error" in data
                text_content = json.dumps(data, indent=2, ensure_ascii=False)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": text_content,
                            }
                        ],
                        "isError": is_err,
                    },
                }

            except Exception as exc:
                logger.exception("Error executing MCP tool '%s': %s", tool_name, exc)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error executing tool '{tool_name}': {exc}",
                            }
                        ],
                        "isError": True,
                    },
                }

        # 6. Unknown method
        logger.warning("Unrecognized MCP method requested: %s", method)
        if req_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' is not implemented.",
                },
            }
        return None

    # ---------------------------------------------------------------------------
    # Stdio Loop
    # ---------------------------------------------------------------------------

    def run_stdio(self, in_stream: TextIO = sys.stdin, out_stream: TextIO = sys.stdout) -> None:
        """
        Runs the standard newline-delimited JSON-RPC loop over stdio.
        """
        logger.info(
            "Aether MCP Server active (workspace: '%s' [%s]). Awaiting JSON-RPC requests on stdio...",
            self.workspace.name,
            self.workspace.id,
        )
        for line in in_stream:
            line_str = line.strip()
            if not line_str:
                continue

            try:
                req = json.loads(line_str)
                resp = self.handle_request(req)
                if resp is not None:
                    out_line = json.dumps(resp, ensure_ascii=False) + "\n"
                    out_stream.write(out_line)
                    out_stream.flush()
            except json.JSONDecodeError as exc:
                logger.error("JSON parse error: %s (payload: %s)", exc, line_str[:100])
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": f"Invalid JSON payload: {exc}",
                    },
                }
                out_stream.write(json.dumps(err_resp) + "\n")
                out_stream.flush()
            except Exception as exc:
                logger.exception("Unexpected error in stdio loop: %s", exc)
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": f"Internal server error: {exc}",
                    },
                }
                out_stream.write(json.dumps(err_resp) + "\n")
                out_stream.flush()

        logger.info("Stdio stream closed. Aether MCP Server shutting down.")
