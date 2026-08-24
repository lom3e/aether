"""
Built-in Slash Commands for Aether AI Workforce.
Implements the core 26 agentic slash commands.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from aether.commands.models import (
    CommandCategory,
    CommandContext,
    CommandResult,
    CommandSpec,
)
from aether.commands.registry import CommandRegistry
from aether.core.security import OperationType
from aether.tools.web_search import DuckDuckGoSearchBackend


def register_builtin_commands(registry: CommandRegistry) -> None:
    """Register all 26 built-in Aether slash commands into the registry."""

    # =========================================================================
    # 1. CORE / SESSION COMMANDS
    # =========================================================================

    async def handle_help(ctx: CommandContext) -> CommandResult:
        if ctx.args:
            target = ctx.args[0].lower().lstrip("/")
            match = registry.get(target)
            if not match:
                return CommandResult(
                    command="help",
                    success=False,
                    error=f"Command '/{target}' not found.",
                    output=f"**Error**: Command `/{target}` not found. Type `/help` to see all commands.",
                )
            spec, _ = match
            lines = [
                f"### Command: `/{spec.name}`",
                f"**Description**: {spec.description}",
                f"**Usage**: `{spec.usage}`",
            ]
            if spec.aliases:
                lines.append(f"**Aliases**: {', '.join(f'`/{a}`' for a in spec.aliases)}")
            if spec.examples:
                lines.append("**Examples**:\n" + "\n".join(f"- `{ex}`" for ex in spec.examples))
            return CommandResult(command="help", success=True, output="\n\n".join(lines))

        # Full categorized list
        category_titles = {
            CommandCategory.CORE: "⚙️ Core & Session",
            CommandCategory.AI: "🧠 AI & Execution",
            CommandCategory.WORKFORCE: "👥 Workforce & Agents",
            CommandCategory.PROJECT: "📁 Project & Coding",
            CommandCategory.CONVERSATION: "💬 Conversation Lifecycle",
            CommandCategory.PERMISSIONS: "🛡️ Permissions & Safety",
            CommandCategory.UTILITY: "🔍 Utility & Search",
        }

        specs_by_cat: dict[CommandCategory, list[CommandSpec]] = {}
        for cat in CommandCategory:
            specs_by_cat[cat] = []

        for spec in registry.list_specs():
            cat = spec.category if isinstance(spec.category, CommandCategory) else CommandCategory(spec.category)
            specs_by_cat.setdefault(cat, []).append(spec)

        sections = ["## ⚡ Aether Slash Commands\n"]
        for cat, title in category_titles.items():
            specs = specs_by_cat.get(cat, [])
            if not specs:
                continue
            sections.append(f"### {title}")
            for s in specs:
                alias_str = f" (aliases: {', '.join(f'`/{a}`' for a in s.aliases)})" if s.aliases else ""
                sections.append(f"- `{s.usage}` — {s.description}{alias_str}")
            sections.append("")

        return CommandResult(
            command="help",
            success=True,
            output="\n".join(sections),
            data={"total_commands": len(registry.list_specs())},
        )

    registry.register(
        CommandSpec(
            name="help",
            description="Show available commands and usage guidance.",
            usage="/help [command]",
            category=CommandCategory.CORE,
            aliases=["h", "?"],
            examples=["/help", "/help model", "/help search"],
        ),
        handle_help,
    )

    async def handle_clear(ctx: CommandContext) -> CommandResult:
        return CommandResult(
            command="clear",
            success=True,
            output="🧹 **Conversation View Cleared**.\nSession view reset. Conversation history remains persisted in workspace database.",
            ui_action="clear_chat",
        )

    registry.register(
        CommandSpec(
            name="clear",
            description="Clear the active conversation display in the chat view.",
            usage="/clear",
            category=CommandCategory.CORE,
            aliases=["c", "cls"],
        ),
        handle_clear,
    )

    async def handle_compact(ctx: CommandContext) -> CommandResult:
        return CommandResult(
            command="compact",
            success=False,
            output="ℹ️ **Context Compaction**: Automated context compaction is not available in the current runtime.\nUse `/clear` or `/new` to start a clean context.",
            data={"supported": False},
        )

    registry.register(
        CommandSpec(
            name="compact",
            description="Compact and summarize long conversation context.",
            usage="/compact",
            category=CommandCategory.CORE,
        ),
        handle_compact,
    )

    async def handle_status(ctx: CommandContext) -> CommandResult:
        ws_name = ctx.workspace.name if ctx.workspace else "None"
        conv_id = ctx.conversation_id or ctx.session_id or "Draft Session"
        conv_title = "Active Task"
        if ctx.workspace and ctx.conversation_id:
            c_data = ctx.workspace.conversations.get(ctx.conversation_id)
            if c_data:
                conv_title = c_data.get("title", "Active Task")

        proj_info = "None (Default `files/` sandbox)"
        if ctx.workspace and ctx.workspace.project_path:
            proj_info = f"`{ctx.workspace.project_path.name}` ({ctx.workspace.project_path})"

        team_name = ctx.team.config.name if ctx.team else "Default Workforce"
        provider = ctx.team.config.default_provider if ctx.team else "ollama"
        model = ctx.team.config.default_model if ctx.team else "qwen3.5:9b"

        is_running = False
        if ctx.app_state and hasattr(ctx.app_state, "active_tasks"):
            is_running = bool(ctx.app_state.active_tasks.get(ctx.session_id or ctx.conversation_id))

        prov_health = None
        try:
            from aether.providers.health import get_default_health_checker
            api_key = None
            if ctx.workspace and hasattr(ctx.workspace, "root") and ctx.workspace.root:
                env_file = ctx.workspace.root / ".env"
                if env_file.exists():
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        if "=" in line and not line.strip().startswith("#"):
                            k, v = line.split("=", 1)
                            if k.strip().upper() == f"{provider.upper()}_API_KEY":
                                api_key = v.strip()
            prov_health = await get_default_health_checker().acheck_health(
                provider=provider,
                model=model,
                api_key=api_key,
                force_refresh=False,
            )
        except Exception:
            pass

        prov_indicator = "Unknown"
        if prov_health:
            if prov_health.status == "connected":
                lat = f" ({prov_health.latency_ms:.0f}ms)" if prov_health.latency_ms else ""
                prov_indicator = f"🟢 Connected{lat}"
            elif prov_health.status == "unconfigured":
                prov_indicator = "🟡 Unconfigured (API key missing)"
            elif prov_health.status == "error":
                prov_indicator = f"🔴 Error ({prov_health.error or 'Unreachable'})"
            else:
                prov_indicator = f"⚪ {prov_health.status.capitalize()}"

        status_text = (
            f"### 📊 Aether Workforce Status\n\n"
            f"- **Workspace**: `{ws_name}`\n"
            f"- **Conversation**: `{conv_title}` (`{conv_id}`)\n"
            f"- **Linked Project**: {proj_info}\n"
            f"- **Active Provider**: `{provider}` ({prov_indicator})\n"
            f"- **Default Model**: `{model}`\n"
            f"- **Workforce Team**: `{team_name}` ({len(ctx.team.agents()) if ctx.team else 0} agents)\n"
            f"- **Task State**: `{'⚡ Running' if is_running else '🟢 Idle'}`\n"
        )
        return CommandResult(
            command="status",
            success=True,
            output=status_text,
            data={
                "workspace": ws_name,
                "conversation_id": conv_id,
                "provider": provider,
                "model": model,
                "provider_status": prov_health.to_dict() if prov_health else None,
                "running": is_running,
            },
        )

    registry.register(
        CommandSpec(
            name="status",
            description="Display runtime status of workspace, conversation, provider, and workforce.",
            usage="/status",
            category=CommandCategory.CORE,
            aliases=["st", "info"],
        ),
        handle_status,
    )

    async def handle_context(ctx: CommandContext) -> CommandResult:
        ws_root = str(ctx.workspace.root) if ctx.workspace else "N/A"
        sb_root = str(ctx.workspace.sandbox.root) if (ctx.workspace and hasattr(ctx.workspace, "sandbox")) else "N/A"
        agents_list = [a.name for a in ctx.team.agents()] if ctx.team else []

        msg_count = 0
        if ctx.workspace and ctx.conversation_id:
            c = ctx.workspace.conversations.get(ctx.conversation_id)
            if c:
                msg_count = len(c.get("messages", []))

        skills_count = 0
        if ctx.team and hasattr(ctx.team, "skill_registry") and ctx.team.skill_registry:
            s_reg = ctx.team.skill_registry
            skills_count = len(s_reg.list_skills() if hasattr(s_reg, "list_skills") else s_reg.list())
        tools_count = 0
        if ctx.team and hasattr(ctx.team, "tool_registry") and ctx.team.tool_registry:
            t_reg = ctx.team.tool_registry
            tools_count = len(t_reg.list_tools() if hasattr(t_reg, "list_tools") else t_reg.list())
        elif ctx.team:
            tools_seen = set()
            for a in ctx.team.agents():
                if hasattr(a, "tool_registry") and a.tool_registry:
                    tools_seen.update(t.name for t in (a.tool_registry.list_tools() if hasattr(a.tool_registry, "list_tools") else a.tool_registry.list()))
        knowledge_str = "None"
        if ctx.team and ctx.team.knowledge:
            try:
                k_counts = ctx.team.knowledge.count_by_scope() if hasattr(ctx.team.knowledge, "count_by_scope") else {}
                ws_cnt = k_counts.get("workspace", 0)
                proj_cnt = k_counts.get("project", 0)
                sys_cnt = k_counts.get("system", 0)
                knowledge_str = f"`{ws_cnt}` workspace, `{proj_cnt}` project, `{sys_cnt}` system"
            except Exception:
                knowledge_str = f"`{ctx.team.knowledge.count()}` chunks"

        output = (
            f"### 🧩 Runtime Context Information\n\n"
            f"- **Workspace Root**: `{ws_root}`\n"
            f"- **Sandbox Root**: `{sb_root}`\n"
            f"- **Active Agents**: {', '.join(f'`{a}`' for a in agents_list) if agents_list else 'None'}\n"
            f"- **Conversation Messages**: `{msg_count}`\n"
            f"- **Registered Skills**: `{skills_count}`\n"
            f"- **Registered Tools**: `{tools_count}`\n"
            f"- **Indexed Knowledge**: {knowledge_str}\n"
        )
        return CommandResult(
            command="context",
            success=True,
            output=output,
            data={
                "workspace_root": ws_root,
                "sandbox_root": sb_root,
                "message_count": msg_count,
                "skills_count": skills_count,
                "tools_count": tools_count,
            },
        )

    registry.register(
        CommandSpec(
            name="context",
            description="Display runtime context details, paths, active agents, and counts.",
            usage="/context",
            category=CommandCategory.CORE,
            aliases=["ctx"],
        ),
        handle_context,
    )

    # =========================================================================
    # 2. AI / EXECUTION COMMANDS
    # =========================================================================

    async def handle_model(ctx: CommandContext) -> CommandResult:
        if not ctx.team:
            return CommandResult(
                command="model",
                success=False,
                error="No active workforce team.",
                output="**Error**: No active workforce team found to configure model.",
            )

        if not ctx.args:
            current_prov = ctx.team.config.default_provider
            current_model = ctx.team.config.default_model
            return CommandResult(
                command="model",
                success=True,
                output=f"**Current Model**: `{current_model}` (Provider: `{current_prov}`)\n\nTo change model, run: `/model <model_name>` (e.g. `/model qwen3.5:9b` or `/model gpt-4o`).",
                data={"provider": current_prov, "model": current_model},
            )

        new_model = ctx.args[0].strip()
        ctx.team.config.default_model = new_model
        return CommandResult(
            command="model",
            success=True,
            output=f"🔄 **Model Updated**: Active workforce model set to `{new_model}`.",
            data={"provider": ctx.team.config.default_provider, "model": new_model},
        )

    registry.register(
        CommandSpec(
            name="model",
            description="Inspect or change the active LLM model.",
            usage="/model [model_name]",
            category=CommandCategory.AI,
            aliases=["m"],
            examples=["/model", "/model gpt-4o", "/model qwen3.5:9b"],
        ),
        handle_model,
    )

    async def handle_plan(ctx: CommandContext) -> CommandResult:
        return CommandResult(
            command="plan",
            success=True,
            output="📋 **Planning Mode**: Activated for upcoming workforce tasks.\nThe lead manager agent will generate structured execution plans before invoking specialists.",
            data={"planning_mode": True},
        )

    registry.register(
        CommandSpec(
            name="plan",
            description="Activate explicit planning breakdown mode for upcoming tasks.",
            usage="/plan",
            category=CommandCategory.AI,
        ),
        handle_plan,
    )

    async def handle_fast(ctx: CommandContext) -> CommandResult:
        if not ctx.team:
            return CommandResult(
                command="fast",
                success=False,
                error="No active workforce team.",
                output="**Error**: No active workforce team found.",
            )

        current_prov = ctx.team.config.default_provider
        current_model = ctx.team.config.default_model

        fast_presets = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-20241022",
            "gemini": "gemini-2.0-flash",
            "ollama": "llama3.2:3b",
        }
        fast_model = fast_presets.get(current_prov)
        if not fast_model:
            return CommandResult(
                command="fast",
                success=True,
                output=f"ℹ️ **Fast Mode**: No lightweight fast model configured for provider `{current_prov}`.\nCurrent model: `{current_model}`.",
            )

        ctx.team.config.default_model = fast_model
        return CommandResult(
            command="fast",
            success=True,
            output=f"⚡ **Fast Mode**: Switched to fast lightweight model `{fast_model}` ({current_prov}).",
            data={"provider": current_prov, "model": fast_model},
        )

    registry.register(
        CommandSpec(
            name="fast",
            description="Switch to a fast lightweight model profile.",
            usage="/fast",
            category=CommandCategory.AI,
        ),
        handle_fast,
    )

    async def handle_review(ctx: CommandContext) -> CommandResult:
        if not ctx.workspace:
            return CommandResult(
                command="review",
                success=False,
                error="No active workspace.",
                output="**Error**: Workspace not active.",
            )

        target_dir = ctx.workspace.project_path or ctx.workspace.files_dir
        if (target_dir / ".git").exists():
            try:
                proc = subprocess.run(
                    ["git", "status", "--short"],
                    cwd=str(target_dir),
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                status_out = proc.stdout.strip()
                if status_out:
                    return CommandResult(
                        command="review",
                        success=True,
                        output=f"🔍 **Code Review Context**:\nFound modified files in `{target_dir.name}`:\n```\n{status_out}\n```\nWorkforce reviewer agent is ready to analyze changes.",
                        data={"modified_files": status_out.splitlines()},
                    )
                return CommandResult(
                    command="review",
                    success=True,
                    output=f"🔍 **Code Review Context**: Working tree in `{target_dir.name}` is clean. No uncommitted modifications found.",
                    data={"modified_files": []},
                )
            except Exception as e:
                return CommandResult(
                    command="review",
                    success=True,
                    output=f"🔍 **Code Review Context**: Project directory `{target_dir.name}` ready for review.",
                )

        return CommandResult(
            command="review",
            success=True,
            output=f"🔍 **Code Review Context**: Workspace target `{target_dir.name}` is ready for review.",
        )

    registry.register(
        CommandSpec(
            name="review",
            description="Initiate a review of project modifications and workspace state.",
            usage="/review",
            category=CommandCategory.AI,
        ),
        handle_review,
    )

    # =========================================================================
    # 3. WORKFORCE COMMANDS
    # =========================================================================

    async def handle_agents(ctx: CommandContext) -> CommandResult:
        if not ctx.team:
            return CommandResult(
                command="agents",
                success=False,
                error="No active workforce team.",
                output="**Error**: No active workforce team found.",
            )

        agents = ctx.team.agents()
        if not agents:
            return CommandResult(
                command="agents",
                success=True,
                output="👥 **Workforce Agents**: No agents defined in current team configuration.",
                data={"agents": []},
            )

        entry_agent = ctx.team.config.entry_agent() if ctx.team.config else None
        entry_name = entry_agent.name if entry_agent else None
        lines = [f"### 👥 Aether Workforce: `{ctx.team.config.name}` ({len(agents)} agents)\n"]
        agents_data = []

        for a in agents:
            is_entry = a.name == entry_name
            role_str = getattr(a, "role", None) or (a.config.role if hasattr(a, "config") else "Specialist")

            skills_items = []
            if hasattr(a, "skills") and a.skills:
                for s in a.skills:
                    if isinstance(s, str):
                        skills_items.append(f"`{s}`")
                    elif hasattr(s, "name"):
                        skills_items.append(f"`{s.name}`")
            skills_str = ", ".join(skills_items) if skills_items else "None"

            raw_tools = a.available_tools() if hasattr(a, "available_tools") else getattr(a, "tools", [])
            tools_items = []
            if raw_tools:
                for t in raw_tools:
                    if isinstance(t, str):
                        tools_items.append(f"`{t}`")
                    elif hasattr(t, "name"):
                        tools_items.append(f"`{t.name}`")
            tools_str = ", ".join(tools_items) if tools_items else "None"

            entry_badge = " *(Entry / Coordinator)*" if is_entry else ""
            identity_parts = []
            if getattr(a, "icon", None):
                identity_parts.append(f"icon: `{a.icon}`")
            if getattr(a, "color", None):
                identity_parts.append(f"color: `{a.color}`")
            identity_str = f" ({', '.join(identity_parts)})" if identity_parts else ""

            lines.append(f"- **`{a.name}`**{entry_badge}{identity_str}\n  - **Role**: {role_str}\n  - **Skills**: {skills_str}\n  - **Tools**: {tools_str}")
            agents_data.append({
                "name": a.name,
                "role": role_str,
                "icon": getattr(a, "icon", None),
                "color": getattr(a, "color", None),
                "tools": [str(t) if isinstance(t, str) else getattr(t, "name", str(t)) for t in raw_tools],
                "is_entry": is_entry,
            })

        return CommandResult(command="agents", success=True, output="\n".join(lines), data={"agents": agents_data})

    registry.register(
        CommandSpec(
            name="agents",
            description="List all specialist agents, roles, skills, and tools in active workforce.",
            usage="/agents",
            category=CommandCategory.WORKFORCE,
            aliases=["workforce", "team"],
        ),
        handle_agents,
    )

    async def handle_skills(ctx: CommandContext) -> CommandResult:
        reg = getattr(ctx.team, "skill_registry", None)
        if not reg:
            from aether.skills.builtin import get_default_skill_registry
            reg = get_default_skill_registry()

        skills = reg.list()
        if not skills:
            return CommandResult(
                command="skills",
                success=True,
                output="🎓 **Skills**: No skills currently registered.",
                data={"skills": []},
            )

        lines = [f"### 🎓 Registered Workforce Skills ({len(skills)})\n"]
        skills_data = []
        for s in skills:
            lines.append(f"- **`{s.name}`** (`v{s.version}`)\n  - {s.description}")
            skills_data.append({"name": s.name, "version": s.version, "description": s.description})

        return CommandResult(command="skills", success=True, output="\n".join(lines), data={"skills": skills_data})

    registry.register(
        CommandSpec(
            name="skills",
            description="List all available skills from the SkillRegistry.",
            usage="/skills",
            category=CommandCategory.WORKFORCE,
        ),
        handle_skills,
    )

    async def handle_tools(ctx: CommandContext) -> CommandResult:
        tools_dict = {}

        # 1. Collect from team agents tool registries
        if ctx.team:
            for agent in ctx.team.agents():
                if hasattr(agent, "tool_registry") and agent.tool_registry:
                    for t in agent.tool_registry.list():
                        if t.name not in tools_dict:
                            tools_dict[t.name] = t

        # 2. Collect from team tool_registry if present
        reg = getattr(ctx.team, "tool_registry", None)
        if reg:
            for t in reg.list():
                if t.name not in tools_dict:
                    tools_dict[t.name] = t

        # 3. Fallback to standard sandbox filesystem + web search tools if none found
        if not tools_dict and ctx.workspace:
            from aether.tools.filesystem import create_filesystem_tools
            from aether.tools.web_search import create_web_search_tool
            for t in create_filesystem_tools(ctx.workspace.sandbox):
                tools_dict[t.name] = t
            w_tool = create_web_search_tool()
            tools_dict[w_tool.name] = w_tool

        tools_list = list(tools_dict.values())
        if not tools_list:
            return CommandResult(
                command="tools",
                success=True,
                output="🛠️ **Tools**: No tools currently registered in runtime.",
                data={"tools": []},
            )

        lines = [f"### 🛠️ Registered Runtime Tools ({len(tools_list)})\n"]
        tools_data = []
        for t in sorted(tools_list, key=lambda x: x.name):
            desc = t.description or "No description provided."
            approval = " *(Requires Approval)*" if getattr(t, "requires_approval", False) else ""
            lines.append(f"- **`{t.name}`**{approval}\n  - {desc}")
            tools_data.append({"name": t.name, "description": desc, "requires_approval": getattr(t, "requires_approval", False)})

        return CommandResult(command="tools", success=True, output="\n".join(lines), data={"tools": tools_data})

    registry.register(
        CommandSpec(
            name="tools",
            description="List all available tools and execution capabilities in the runtime.",
            usage="/tools",
            category=CommandCategory.WORKFORCE,
        ),
        handle_tools,
    )

    async def handle_tasks(ctx: CommandContext) -> CommandResult:
        active_tasks = getattr(ctx.app_state, "active_tasks", {}) if ctx.app_state else {}

        if ctx.args and ctx.args[0].lower() == "stop":
            target_id = ctx.args[1] if len(ctx.args) > 1 else (ctx.session_id or ctx.conversation_id)
            if target_id and target_id in active_tasks:
                task = active_tasks[target_id]
                task.cancel()
                return CommandResult(
                    command="tasks",
                    success=True,
                    output=f"🛑 **Task Stopped**: Active task `{target_id}` was cancelled.",
                    data={"stopped_task": target_id},
                )
            return CommandResult(
                command="tasks",
                success=False,
                error=f"No active running task found with ID '{target_id}'.",
                output=f"**Error**: No active running task found matching `{target_id}`.",
            )

        if not active_tasks:
            return CommandResult(
                command="tasks",
                success=True,
                output="📋 **Active Tasks**: No background or workforce tasks currently executing (Idle).",
                data={"active_tasks": []},
            )

        lines = [f"### 📋 Active Tasks ({len(active_tasks)})\n"]
        for tid, t in active_tasks.items():
            status_str = "Running" if not t.done() else ("Cancelled" if t.cancelled() else "Completed")
            lines.append(f"- **`{tid}`** — State: `{status_str}`")

        lines.append("\nTo stop a task, run: `/tasks stop <task_id>`")
        return CommandResult(command="tasks", success=True, output="\n".join(lines), data={"active_tasks": list(active_tasks.keys())})

    registry.register(
        CommandSpec(
            name="tasks",
            description="List active workforce tasks or stop a running task.",
            usage="/tasks [stop [task_id]]",
            category=CommandCategory.WORKFORCE,
            aliases=["ps", "jobs"],
            examples=["/tasks", "/tasks stop", "/tasks stop conv_123"],
        ),
        handle_tasks,
    )

    # =========================================================================
    # 4. PROJECT / CODING COMMANDS
    # =========================================================================

    async def handle_files(ctx: CommandContext) -> CommandResult:
        if not ctx.workspace:
            return CommandResult(
                command="files",
                success=False,
                error="No active workspace.",
                output="**Error**: Workspace not active.",
            )

        sandbox = ctx.workspace.sandbox
        rel_target = ctx.args[0] if ctx.args else "."

        try:
            target_path = sandbox.validate_path(rel_target, operation=OperationType.LIST, must_exist=True)
            if not target_path.is_dir():
                return CommandResult(
                    command="files",
                    success=False,
                    error="Target is a file, not a directory.",
                    output=f"**Error**: `{rel_target}` is a file, not a directory.",
                )

            entries = []
            for item in sorted(target_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                item_rel = sandbox.get_relative_path(item)
                if sandbox.is_sensitive(item_rel):
                    continue
                if item.is_dir():
                    entries.append(f"📁 `{item.name}/`")
                else:
                    size = item.stat().st_size
                    entries.append(f"📄 `{item.name}` ({size} bytes)")

            title_dir = sandbox.get_relative_path(target_path)
            header = f"### 📁 Files in `{title_dir}` ({len(entries)} items)\n"
            if not entries:
                return CommandResult(command="files", success=True, output=f"{header}*(empty directory)*")
            return CommandResult(command="files", success=True, output=header + "\n".join(f"- {e}" for e in entries))
        except Exception as e:
            return CommandResult(command="files", success=False, error=str(e), output=f"**Error**: {e}")

    registry.register(
        CommandSpec(
            name="files",
            description="List files and directories in the sandboxed project/workspace.",
            usage="/files [path]",
            category=CommandCategory.PROJECT,
            aliases=["ls", "tree"],
            examples=["/files", "/files src", "/files docs"],
        ),
        handle_files,
    )

    async def handle_open(ctx: CommandContext) -> CommandResult:
        if not ctx.args:
            return CommandResult(
                command="open",
                success=False,
                error="Usage: /open <path>",
                output="**Usage**: `/open <path>` (e.g. `/open README.md` or `/open src/main.py`)",
            )

        if not ctx.workspace:
            return CommandResult(
                command="open",
                success=False,
                error="No active workspace.",
                output="**Error**: Workspace not active.",
            )

        rel_path = ctx.args[0]
        sandbox = ctx.workspace.sandbox

        try:
            target_path = sandbox.validate_path(rel_path, operation=OperationType.READ, must_exist=True)
            if target_path.is_dir():
                return CommandResult(
                    command="open",
                    success=False,
                    error=f"'{rel_path}' is a directory, not a file.",
                    output=f"**Error**: `{rel_path}` is a directory. Use `/files {rel_path}` to list contents.",
                )

            content = target_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            total_lines = len(lines)

            # Limit preview size if file is huge
            preview = "\n".join(lines[:250])
            if total_lines > 250:
                preview += f"\n\n... (truncated {total_lines - 250} lines) ..."

            ext = target_path.suffix.lstrip(".")
            lang = ext if ext in ("py", "ts", "tsx", "js", "json", "yaml", "yml", "html", "css", "md", "sql", "sh") else ""

            output = (
                f"### 📄 `{sandbox.get_relative_path(target_path)}` ({total_lines} lines)\n\n"
                f"```{lang}\n{preview}\n```"
            )
            return CommandResult(
                command="open",
                success=True,
                output=output,
                data={"path": rel_path, "total_lines": total_lines},
            )
        except Exception as e:
            return CommandResult(command="open", success=False, error=str(e), output=f"**Error**: {e}")

    registry.register(
        CommandSpec(
            name="open",
            description="Open and inspect the content of a sandboxed project file.",
            usage="/open <path>",
            category=CommandCategory.PROJECT,
            requires_args=True,
            min_args=1,
            aliases=["read", "cat"],
            examples=["/open README.md", "/open src/index.ts"],
        ),
        handle_open,
    )

    async def handle_diff(ctx: CommandContext) -> CommandResult:
        if not ctx.workspace:
            return CommandResult(
                command="diff",
                success=False,
                error="No active workspace.",
                output="**Error**: Workspace not active.",
            )

        target_dir = ctx.workspace.project_path or ctx.workspace.files_dir
        if not (target_dir / ".git").exists():
            return CommandResult(
                command="diff",
                success=True,
                output=f"ℹ️ **Git Diff**: `{target_dir.name}` is not a Git repository.",
                data={"is_git": False},
            )

        try:
            proc = subprocess.run(
                ["git", "diff"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            diff_text = proc.stdout.strip()
            if not diff_text:
                return CommandResult(
                    command="diff",
                    success=True,
                    output=f"✅ **Git Diff**: Working tree clean. No local modifications in `{target_dir.name}`.",
                    data={"diff": ""},
                )

            preview = diff_text[:3000]
            if len(diff_text) > 3000:
                preview += "\n... (truncated long diff) ..."

            return CommandResult(
                command="diff",
                success=True,
                output=f"### 🔍 Git Diff (`{target_dir.name}`)\n\n```diff\n{preview}\n```",
                data={"diff": diff_text},
            )
        except Exception as e:
            return CommandResult(
                command="diff",
                success=False,
                error=str(e),
                output=f"**Error executing git diff**: {e}",
            )

    registry.register(
        CommandSpec(
            name="diff",
            description="Show git diff of local modifications in the linked project.",
            usage="/diff",
            category=CommandCategory.PROJECT,
        ),
        handle_diff,
    )

    async def handle_init(ctx: CommandContext) -> CommandResult:
        if not ctx.workspace:
            return CommandResult(
                command="init",
                success=False,
                error="No active workspace.",
                output="**Error**: Workspace not active.",
            )

        if ctx.workspace.project_path:
            return CommandResult(
                command="init",
                success=True,
                output=f"📁 **Project Access**: Already linked to project at `{ctx.workspace.project_path.name}` (`{ctx.workspace.project_path}`).\nWorkforce tools operate directly on project files.",
                data={"linked": True, "project_path": str(ctx.workspace.project_path)},
            )

        return CommandResult(
            command="init",
            success=True,
            output=f"📁 **Project Access**: Workspace `{ctx.workspace.name}` is initialized with local sandbox (`files/`).\nTo connect an external code repository, use Workspace Settings.",
            data={"linked": False},
        )

    registry.register(
        CommandSpec(
            name="init",
            description="Display project context initialization status.",
            usage="/init",
            category=CommandCategory.PROJECT,
        ),
        handle_init,
    )

    async def handle_github(ctx: CommandContext) -> CommandResult:
        if not ctx.workspace:
            return CommandResult(
                command="github",
                success=False,
                error="No active workspace.",
                output="**Error**: Workspace not active.",
            )

        # Check if current conversation belongs to a project
        target_project = None
        if ctx.conversation_id:
            conv = ctx.workspace.conversations.get(ctx.conversation_id)
            if conv and conv.get("project_id"):
                target_project = ctx.workspace.conversations.get_project(conv["project_id"])

        if not target_project:
            # Fallback: check all projects in workspace for connected repository
            projects = ctx.workspace.conversations.list_projects()
            for p in projects:
                if p.get("github_repository"):
                    target_project = p
                    break

        if not target_project or not target_project.get("github_repository"):
            return CommandResult(
                command="github",
                success=True,
                output=(
                    "🐙 **GitHub Repository**\n"
                    "───────────────────────\n"
                    "No GitHub repository is currently connected to this project.\n\n"
                    "*To connect a repository, use the Project menu or the `/projects` manager.*"
                ),
                data={"connected": False},
            )

        gh = target_project["github_repository"]
        owner = gh.get("owner", "")
        repo_name = gh.get("repository", "")
        full_name = gh.get("full_name") or f"{owner}/{repo_name}"
        branch = gh.get("default_branch", "main")
        url = gh.get("url") or f"https://github.com/{full_name}"
        verified_at = gh.get("verified_at") or "Not yet verified"
        private_tag = "🔒 Private" if gh.get("private") else "🌐 Public"

        output_lines = [
            "🐙 **GitHub Repository**",
            "───────────────────────",
            f"- **Repository**: [{full_name}]({url}) ({private_tag})",
            f"- **Default Branch**: `{branch}`",
            f"- **Status**: 🟢 Connected",
            f"- **Project**: {target_project.get('name', 'Default')}",
            f"- **Verified**: {verified_at}",
        ]

        return CommandResult(
            command="github",
            success=True,
            output="\n".join(output_lines),
            data={"connected": True, "repository": gh, "project_id": target_project.get("id")},
        )

    registry.register(
        CommandSpec(
            name="github",
            description="Display the connected GitHub repository status and metadata.",
            usage="/github",
            category=CommandCategory.PROJECT,
            aliases=["gh", "repo"],
            examples=["/github", "/gh"],
        ),
        handle_github,
    )

    # =========================================================================
    # 5. CONVERSATION COMMANDS
    # =========================================================================

    async def handle_new(ctx: CommandContext) -> CommandResult:
        if not ctx.workspace:
            return CommandResult(
                command="new",
                success=False,
                error="No active workspace.",
                output="**Error**: Workspace not active.",
            )

        new_conv = ctx.workspace.conversations.create(title="New Task")
        return CommandResult(
            command="new",
            success=True,
            output=f"✨ **New Conversation**: Created new session `{new_conv['id']}`.",
            ui_action="new_conversation",
            data={"conversation": new_conv},
        )

    registry.register(
        CommandSpec(
            name="new",
            description="Start a new conversation session.",
            usage="/new",
            category=CommandCategory.CONVERSATION,
        ),
        handle_new,
    )

    async def handle_rename(ctx: CommandContext) -> CommandResult:
        if not ctx.raw_args:
            return CommandResult(
                command="rename",
                success=False,
                error="Usage: /rename <name>",
                output="**Usage**: `/rename <name>` (e.g. `/rename Backend Optimization`)",
            )

        if not ctx.workspace or not ctx.conversation_id:
            return CommandResult(
                command="rename",
                success=False,
                error="No active conversation to rename.",
                output="**Error**: No active conversation selected to rename.",
            )

        new_title = ctx.raw_args.strip()
        updated = ctx.workspace.conversations.update(ctx.conversation_id, title=new_title)
        if not updated:
            return CommandResult(
                command="rename",
                success=False,
                error="Conversation not found.",
                output="**Error**: Failed to rename conversation.",
            )

        return CommandResult(
            command="rename",
            success=True,
            output=f"✏️ **Conversation Renamed**: Updated title to **\"{new_title}\"**.",
            ui_action="rename_conversation",
            data={"conversation_id": ctx.conversation_id, "title": new_title},
        )

    registry.register(
        CommandSpec(
            name="rename",
            description="Rename the active conversation.",
            usage="/rename <name>",
            category=CommandCategory.CONVERSATION,
            requires_args=True,
            min_args=1,
            examples=["/rename Refactor Database", "/rename Sprint Planning"],
        ),
        handle_rename,
    )

    async def handle_resume(ctx: CommandContext) -> CommandResult:
        if not ctx.workspace:
            return CommandResult(
                command="resume",
                success=False,
                error="No active workspace.",
                output="**Error**: Workspace not active.",
            )

        if ctx.args:
            target_id = ctx.args[0].strip()
            conv = ctx.workspace.conversations.get(target_id)
            if not conv:
                return CommandResult(
                    command="resume",
                    success=False,
                    error=f"Conversation '{target_id}' not found.",
                    output=f"**Error**: Conversation `{target_id}` not found.",
                )
            return CommandResult(
                command="resume",
                success=True,
                output=f"▶️ **Resumed Conversation**: Switched to \"{conv['title']}\" (`{target_id}`).",
                ui_action="select_conversation",
                data={"conversation_id": target_id},
            )

        if ctx.conversation_id:
            conv = ctx.workspace.conversations.get(ctx.conversation_id)
            title = conv.get("title") if conv else "Active Task"
            return CommandResult(
                command="resume",
                success=True,
                output=f"▶️ **Active Conversation**: Continuing \"{title}\" (`{ctx.conversation_id}`).",
                data={"conversation_id": ctx.conversation_id},
            )

        return CommandResult(
            command="resume",
            success=False,
            error="Usage: /resume <conversation_id>",
            output="**Usage**: `/resume <conversation_id>`",
        )

    registry.register(
        CommandSpec(
            name="resume",
            description="Resume an existing conversation by ID.",
            usage="/resume [conversation_id]",
            category=CommandCategory.CONVERSATION,
        ),
        handle_resume,
    )

    async def handle_fork(ctx: CommandContext) -> CommandResult:
        if not ctx.workspace or not ctx.conversation_id:
            return CommandResult(
                command="fork",
                success=False,
                error="No active conversation to fork.",
                output="**Error**: No active conversation selected to fork.",
            )

        forked = ctx.workspace.conversations.duplicate(ctx.conversation_id)
        if not forked:
            return CommandResult(
                command="fork",
                success=False,
                error="Failed to fork conversation.",
                output="**Error**: Failed to duplicate conversation history.",
            )

        return CommandResult(
            command="fork",
            success=True,
            output=f"🌿 **Conversation Forked**: Created new branch **\"{forked['title']}\"** (`{forked['id']}`).",
            ui_action="select_conversation",
            data={"conversation_id": forked["id"], "forked_from": ctx.conversation_id},
        )

    registry.register(
        CommandSpec(
            name="fork",
            description="Fork the current conversation history into a new task session.",
            usage="/fork",
            category=CommandCategory.CONVERSATION,
        ),
        handle_fork,
    )

    async def handle_rewind(ctx: CommandContext) -> CommandResult:
        return CommandResult(
            command="rewind",
            success=False,
            output="ℹ️ **Rewind**: State checkpointing and conversation rewind are not available in the current runtime.\nTo branch from an earlier turn, use message edit or `/fork`.",
            data={"supported": False},
        )

    registry.register(
        CommandSpec(
            name="rewind",
            description="Rewind conversation state to a previous checkpoint.",
            usage="/rewind",
            category=CommandCategory.CONVERSATION,
        ),
        handle_rewind,
    )

    # =========================================================================
    # 6. PERMISSIONS & SAFETY COMMANDS
    # =========================================================================

    async def handle_permissions(ctx: CommandContext) -> CommandResult:
        sandbox_path = ctx.workspace.sandbox.root if (ctx.workspace and hasattr(ctx.workspace, "sandbox")) else "N/A"
        output = (
            f"### 🛡️ Runtime Safety & Permissions Policy\n\n"
            f"- **PathSandbox Root**: `{sandbox_path}`\n"
            f"- **`read_file`**: ✅ Allowed (Sandboxed)\n"
            f"- **`list_directory`**: ✅ Allowed (Sandboxed)\n"
            f"- **`write_file`**: ✅ Allowed (Sandboxed)\n"
            f"- **`patch_file`**: ✅ Allowed (Sandboxed)\n"
            f"- **`delete_file`**: 🔒 **Protected** (Requires Approval / HITL)\n"
            f"- **`search_web`**: ✅ Allowed (10s timeout, zero API key requirement)\n"
            f"- **Traversal & Symlink Protection**: 🛡️ **Enforced** (Realpath verification)\n"
            f"- **Sensitive Paths Blacklist**: 🛡️ **Protected** (`.env*`, `.git`, `.venv`, credentials)\n"
        )
        return CommandResult(command="permissions", success=True, output=output)

    registry.register(
        CommandSpec(
            name="permissions",
            description="Inspect runtime security boundaries, tool permissions, and HITL policies.",
            usage="/permissions",
            category=CommandCategory.PERMISSIONS,
            aliases=["perms", "safety"],
        ),
        handle_permissions,
    )

    # =========================================================================
    # 7. UTILITY COMMANDS
    # =========================================================================

    async def handle_search(ctx: CommandContext) -> CommandResult:
        if not ctx.raw_args:
            return CommandResult(
                command="search",
                success=False,
                error="Usage: /search <query>",
                output="**Usage**: `/search <query>` (e.g. `/search python asyncio best practices`)",
            )

        query = ctx.raw_args.strip()
        backend = DuckDuckGoSearchBackend(timeout=10.0)

        try:
            results = backend.search(query, max_results=5)
            if not results:
                return CommandResult(
                    command="search",
                    success=True,
                    output=f"🔍 **Web Search**: No results found for query `{query}`.",
                    data={"query": query, "results": []},
                )

            lines = [f"### 🔍 Web Search Results for `{query}`\n"]
            res_data = []
            for idx, r in enumerate(results, start=1):
                lines.append(f"{idx}. **[{r.title}]({r.url})**\n   {r.snippet}\n")
                res_data.append(r.to_dict())

            return CommandResult(
                command="search",
                success=True,
                output="\n".join(lines),
                data={"query": query, "results": res_data},
            )
        except Exception as e:
            return CommandResult(
                command="search",
                success=False,
                error=str(e),
                output=f"**Error executing web search**: {e}",
            )

    registry.register(
        CommandSpec(
            name="search",
            description="Execute real web search using the sandboxed search_web tool.",
            usage="/search <query>",
            category=CommandCategory.UTILITY,
            requires_args=True,
            min_args=1,
            aliases=["find", "web"],
            examples=["/search Python 3.14 release", "/search FastAPI websockets tutorial"],
        ),
        handle_search,
    )

    async def handle_btw(ctx: CommandContext) -> CommandResult:
        if not ctx.raw_args:
            return CommandResult(
                command="btw",
                success=False,
                error="Usage: /btw <question>",
                output="**Usage**: `/btw <question>` (e.g. `/btw what is the difference between map and filter?`)",
            )

        question = ctx.raw_args.strip()
        return CommandResult(
            command="btw",
            success=True,
            output=f"💡 **Side Question**: `{question}`\n\n*(Side questions allow isolated queries without mutating the main task context)*",
            data={"question": question},
        )

    registry.register(
        CommandSpec(
            name="btw",
            description="Ask a side question without modifying the main task context.",
            usage="/btw <question>",
            category=CommandCategory.UTILITY,
            requires_args=True,
            min_args=1,
            aliases=["ask", "side"],
            examples=["/btw what is the difference between async and thread?"],
        ),
        handle_btw,
    )

    async def handle_copy(ctx: CommandContext) -> CommandResult:
        return CommandResult(
            command="copy",
            success=True,
            output="📋 **Copy**: Use the copy button located at the top-right of any message or code block to copy content directly to your clipboard.",
        )

    registry.register(
        CommandSpec(
            name="copy",
            description="Copy the previous output or message content to clipboard.",
            usage="/copy",
            category=CommandCategory.UTILITY,
        ),
        handle_copy,
    )
