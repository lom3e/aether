from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
import urllib.error
import urllib.parse
import urllib.request

from aether.agents.agent import Agent
from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import ExecutionContext, ExecutionResult, ExecutionStatus, Task

logger = logging.getLogger(__name__)


@dataclass
class ExternalAgentConfig:
    """
    Configuration for an external agent or worker accessible via HTTP, CLI, or MCP.
    """
    name: str
    role: str = "external_worker"
    protocol: str = "http"  # "http" | "command" | "mcp"
    endpoint_url: str | None = None
    command: list[str] | str | None = None
    timeout_seconds: float = 60.0
    auth_token: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    icon: str | None = "Bot"
    color: str | None = "cyan"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "protocol": self.protocol,
            "endpoint_url": self.endpoint_url,
            "command": self.command,
            "timeout_seconds": self.timeout_seconds,
            "auth_token": "***" if self.auth_token else None,
            "headers": {k: ("***" if "auth" in k.lower() or "token" in k.lower() or "key" in k.lower() else v) for k, v in self.headers.items()},
            "capabilities": list(self.capabilities),
            "metadata": dict(self.metadata),
            "cwd": self.cwd,
            "icon": self.icon,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExternalAgentConfig:
        return cls(
            name=str(data.get("name", "external_worker")),
            role=str(data.get("role", "external_worker")),
            protocol=str(data.get("protocol", "http")).lower(),
            endpoint_url=data.get("endpoint_url"),
            command=data.get("command"),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            auth_token=data.get("auth_token"),
            headers=dict(data.get("headers", {})),
            capabilities=list(data.get("capabilities", [])),
            metadata=dict(data.get("metadata", {})),
            cwd=data.get("cwd"),
            env=dict(data.get("env", {})),
            icon=data.get("icon", "Bot"),
            color=data.get("color", "cyan"),
        )


class ExternalAgentAdapter(Agent):
    """
    Adapter that executes tasks against external agents or workers
    via HTTP endpoints, CLI subprocesses, or Model Context Protocol (MCP) servers.

    Subclasses Agent to provide seamless inter-agent delegation through AgentTool
    and direct execution inside Aether Teams and Workforces.
    """

    is_external: bool = True

    def __init__(
        self,
        config: ExternalAgentConfig | None = None,
        *,
        name: str | None = None,
        role: str = "external_worker",
        protocol: str = "http",
        endpoint_url: str | None = None,
        command: list[str] | str | None = None,
        timeout_seconds: float = 60.0,
        auth_token: str | None = None,
        headers: dict[str, str] | None = None,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        icon: str | None = "Bot",
        color: str | None = "cyan",
        **agent_kwargs: Any,
    ) -> None:
        if config is not None:
            self.external_config = config
        else:
            self.external_config = ExternalAgentConfig(
                name=name or "external_worker",
                role=role,
                protocol=protocol,
                endpoint_url=endpoint_url,
                command=command,
                timeout_seconds=timeout_seconds,
                auth_token=auth_token,
                headers=headers or {},
                capabilities=capabilities or [],
                metadata=metadata or {},
                cwd=cwd,
                env=env or {},
                icon=icon,
                color=color,
            )

        super().__init__(
            name=self.external_config.name,
            role=self.external_config.role,
            icon=self.external_config.icon,
            color=self.external_config.color,
            config=self.external_config,
            **agent_kwargs,
        )

    @property
    def protocol(self) -> str:
        return self.external_config.protocol

    @property
    def endpoint_url(self) -> str | None:
        return self.external_config.endpoint_url

    def execute(self, task: Task, context: ExecutionContext | None = None) -> ExecutionResult:
        """
        Executes a task by dispatching it over the configured external protocol.
        """
        self.lifecycle.start()
        start_time = time.time()
        meta = {
            "task_id": task.id,
            "agent_name": self.name,
            "instruction": task.instruction,
            "protocol": self.external_config.protocol,
            "is_external": True,
        }

        # Check cancellation before dispatching
        cancellation_token = (task.metadata or {}).get("cancellation_token")
        if cancellation_token and cancellation_token.is_set():
            self.lifecycle.fail("Execution cancelled by user.")
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.CANCELLED,
                error="Execution cancelled by user.",
                metadata=meta,
            )

        # Emit start event if event emitter is configured
        if getattr(self, "events", None):
            try:
                from aether.coordination.events import AgentEvent, EventType
                self.events.emit(AgentEvent(
                    event_type=EventType.AGENT_STARTED,
                    agent_name=self.name,
                    task_id=task.id,
                    metadata=meta,
                ))
            except Exception:
                pass

        try:
            proto = self.external_config.protocol.lower()
            if proto in ("http", "https"):
                result = self._execute_http(task, cancellation_token)
            elif proto in ("command", "process", "cli"):
                result = self._execute_command(task, cancellation_token)
            elif proto == "mcp":
                result = self._execute_mcp(task, cancellation_token)
            else:
                raise ValueError(f"Unsupported external protocol: {self.external_config.protocol}")

            duration_s = round(time.time() - start_time, 3)
            result.metadata.update(meta)
            result.metadata["duration_seconds"] = duration_s

            if result.success:
                self.lifecycle.complete()
                if getattr(self, "events", None):
                    try:
                        from aether.coordination.events import AgentEvent, EventType
                        self.events.emit(AgentEvent(
                            event_type=EventType.AGENT_COMPLETED,
                            agent_name=self.name,
                            task_id=task.id,
                            metadata=result.metadata,
                        ))
                    except Exception:
                        pass
            else:
                self.lifecycle.fail(result.error or "External execution failed")
                if getattr(self, "events", None):
                    try:
                        from aether.coordination.events import AgentEvent, EventType
                        self.events.emit(AgentEvent(
                            event_type=EventType.AGENT_FAILED,
                            agent_name=self.name,
                            task_id=task.id,
                            metadata=result.metadata,
                        ))
                    except Exception:
                        pass

            return result

        except Exception as exc:
            duration_s = round(time.time() - start_time, 3)
            err_msg = str(exc)
            meta["duration_seconds"] = duration_s
            self.lifecycle.fail(err_msg)
            if getattr(self, "events", None):
                try:
                    from aether.coordination.events import AgentEvent, EventType
                    self.events.emit(AgentEvent(
                        event_type=EventType.AGENT_FAILED,
                        agent_name=self.name,
                        task_id=task.id,
                        metadata={"error": err_msg, **meta},
                    ))
                except Exception:
                    pass
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=err_msg,
                metadata=meta,
            )

    def _execute_http(self, task: Task, cancellation_token: Any | None = None) -> ExecutionResult:
        endpoint = self.external_config.endpoint_url
        if not endpoint:
            raise ValueError(f"External agent '{self.name}' has no endpoint_url configured.")

        payload = {
            "task_id": task.id,
            "instruction": task.instruction,
            "agent_name": self.name,
            "role": self.role,
            "context_data": task.context_data or {},
            "action_args": task.action_args or {},
            "metadata": {k: v for k, v in (task.metadata or {}).items() if k != "cancellation_token"},
            "expected_output": task.expected_output,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Aether-ExternalWorker/1.0",
        }
        if self.external_config.auth_token:
            headers["Authorization"] = f"Bearer {self.external_config.auth_token}"
        if self.external_config.headers:
            headers.update(self.external_config.headers)

        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.external_config.timeout_seconds) as resp:
                resp_bytes = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                resp_text = resp_bytes.decode(charset)
                
                try:
                    resp_json = json.loads(resp_text)
                except Exception:
                    # Non-JSON response, treat as raw text
                    return ExecutionResult(
                        success=True,
                        status=ExecutionStatus.COMPLETED,
                        output=resp_text.strip(),
                    )

                return self._parse_worker_response(resp_json)

        except urllib.error.HTTPError as http_err:
            error_body = ""
            try:
                error_body = http_err.read().decode("utf-8")
            except Exception:
                pass
            err_msg = f"HTTP {http_err.code} {http_err.reason}: {error_body.strip() or 'No details'}"
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=err_msg,
            )
        except urllib.error.URLError as url_err:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=f"Connection error to '{endpoint}': {url_err.reason}",
            )
        except TimeoutError:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=f"Execution timed out after {self.external_config.timeout_seconds}s connecting to '{endpoint}'",
            )

    def _execute_command(self, task: Task, cancellation_token: Any | None = None) -> ExecutionResult:
        cmd = self.external_config.command
        if not cmd:
            raise ValueError(f"External agent '{self.name}' has no command configured.")

        cmd_list = cmd if isinstance(cmd, list) else [cmd]
        payload = {
            "task_id": task.id,
            "instruction": task.instruction,
            "agent_name": self.name,
            "role": self.role,
            "context_data": task.context_data or {},
            "action_args": task.action_args or {},
            "metadata": {k: v for k, v in (task.metadata or {}).items() if k != "cancellation_token"},
            "expected_output": task.expected_output,
        }

        env = os.environ.copy()
        if self.external_config.env:
            env.update(self.external_config.env)
        if self.external_config.auth_token:
            env["AETHER_AUTH_TOKEN"] = self.external_config.auth_token

        try:
            proc = subprocess.run(
                cmd_list,
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                cwd=self.external_config.cwd,
                env=env,
                timeout=self.external_config.timeout_seconds,
                shell=isinstance(cmd, str),
            )

            if proc.returncode != 0:
                err_msg = (proc.stderr or proc.stdout or f"Process exited with code {proc.returncode}").strip()
                return ExecutionResult(
                    success=False,
                    status=ExecutionStatus.FAILED,
                    error=err_msg,
                )

            stdout = proc.stdout.strip()
            try:
                data = json.loads(stdout)
                return self._parse_worker_response(data)
            except Exception:
                return ExecutionResult(
                    success=True,
                    status=ExecutionStatus.COMPLETED,
                    output=stdout,
                )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=f"Process execution timed out after {self.external_config.timeout_seconds}s",
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=f"Failed to execute command '{cmd}': {exc}",
            )

    def _execute_mcp(self, task: Task, cancellation_token: Any | None = None) -> ExecutionResult:
        from aether.tools.mcp import MCPClient

        client = None
        if self.external_config.endpoint_url:
            client = MCPClient(
                endpoint_url=self.external_config.endpoint_url,
                auth_token=self.external_config.auth_token,
                headers=self.external_config.headers,
                timeout_seconds=self.external_config.timeout_seconds,
            )
        elif self.external_config.command:
            client = MCPClient(
                command=self.external_config.command,
                cwd=self.external_config.cwd,
                env=self.external_config.env,
                timeout_seconds=self.external_config.timeout_seconds,
            )
        else:
            raise ValueError(f"MCP agent '{self.name}' must specify endpoint_url or command.")

        try:
            client.connect()
            tools = client.list_tools()
            if not tools:
                return ExecutionResult(
                    success=False,
                    status=ExecutionStatus.FAILED,
                    error=f"MCP server '{self.name}' provides no tools.",
                )

            # Target tool selection: if action_id or task specifies tool name, use it; else use first tool
            target_tool_name = None
            if task.action_id and task.action_id in [t.name for t in tools]:
                target_tool_name = task.action_id
            elif "tool_name" in (task.context_data or {}):
                target_tool_name = task.context_data["tool_name"]
            else:
                target_tool_name = tools[0].name

            args = task.action_args or {"instruction": task.instruction, "query": task.instruction}
            call_res = client.call_tool(target_tool_name, args)

            client.close()

            content = call_res.get("content", [])
            output_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    output_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    output_parts.append(item)
                else:
                    output_parts.append(json.dumps(item))

            output_text = "\n".join(output_parts).strip()
            is_error = call_res.get("isError", False)

            if is_error:
                return ExecutionResult(
                    success=False,
                    status=ExecutionStatus.FAILED,
                    error=output_text or "MCP tool returned error",
                )

            return ExecutionResult(
                success=True,
                status=ExecutionStatus.COMPLETED,
                output=output_text,
                metadata={"tool_name": target_tool_name},
            )

        except Exception as exc:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=f"MCP execution failed: {exc}",
            )

    def _parse_worker_response(self, data: Any) -> ExecutionResult:
        if not isinstance(data, dict):
            return ExecutionResult(
                success=True,
                status=ExecutionStatus.COMPLETED,
                output=str(data),
            )

        # Handle failure cases
        error = data.get("error")
        success = data.get("success", error is None)
        status_val = data.get("status")
        if status_val == "failed" or error:
            success = False

        status = ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED
        if status_val in (s.value for s in ExecutionStatus):
            status = ExecutionStatus(status_val)

        output = (
            data.get("output")
            or data.get("result")
            or data.get("response")
            or data.get("message")
            or data.get("text")
        )
        if output is not None and not isinstance(output, str):
            output = json.dumps(output, indent=2)

        artifacts = data.get("artifacts") or []
        deliverables = data.get("deliverables") or []
        meta = data.get("metadata") or {}

        return ExecutionResult(
            success=success,
            status=status,
            output=output,
            error=str(error) if error else None,
            artifacts=artifacts if isinstance(artifacts, list) else [],
            deliverables=deliverables if isinstance(deliverables, list) else [],
            metadata=meta if isinstance(meta, dict) else {},
        )
