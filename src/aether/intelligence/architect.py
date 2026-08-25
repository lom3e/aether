"""
AI Workforce Auto-Architect & Prompt Enhancer.

Translates high-level natural language objectives into production-grade multi-agent
workforces with detailed system prompts, delegation topologies, and tool assignments.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from aether.core.execution import Message
from aether.team.config import SUPPORTED_AGENT_COLORS, SUPPORTED_AGENT_ICONS

logger = logging.getLogger(__name__)


class ArchitectAgentBlueprint(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    role: str = Field(min_length=1, max_length=120)
    system_prompt: str = Field(min_length=1)
    icon: str = "Bot"
    color: str = "violet"
    delegates_to: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class ArchitectWorkforceBlueprint(BaseModel):
    team_name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)
    icon: str = "Layers"
    color: str = "violet"
    entry_agent: str = "Manager"
    agents: list[ArchitectAgentBlueprint] = Field(min_length=1)
    suggested_starter_tasks: list[str] = Field(default_factory=list)
    generation_source: str = "heuristic"  # 'ai' or 'heuristic'


# -----------------------------------------------------------------------------
# Heuristic Workforce Blueprints (Zero-Config / Offline Guarantee)
# -----------------------------------------------------------------------------

def _clean_text(val: str) -> str:
    return re.sub(r"\s+", " ", val).strip()


def build_heuristic_workforce(goal: str) -> ArchitectWorkforceBlueprint:
    """
    Deterministically generate a high-quality workforce blueprint from a natural language goal.
    Provides a guaranteed instantaneous fallback when LLMs are offline or unconfigured.
    """
    g = goal.lower()

    if any(k in g for k in ("competitor", "e-commerce", "ecommerce", "prezz", "scrap", "shop", "market", "monitor")):
        return ArchitectWorkforceBlueprint(
            team_name="Market & Competitor Intelligence",
            description="Autonomous squad that tracks competitor pricing, discovers product trends, and compiles structured market analysis.",
            icon="Compass",
            color="emerald",
            entry_agent="Intelligence Lead",
            generation_source="heuristic",
            suggested_starter_tasks=[
                "Analyze recent competitor product launches and pricing changes.",
                "Extract market trends from top 3 e-commerce competitors and draft an executive report.",
                "Build a competitive comparison matrix with SWOT analysis.",
            ],
            agents=[
                ArchitectAgentBlueprint(
                    name="Intelligence Lead",
                    role="Squad Coordinator & Executive Synthesizer",
                    icon="Compass",
                    color="emerald",
                    delegates_to=["Market Researcher", "Pricing Analyst", "Report Writer"],
                    skills=["web_search", "search_knowledge"],
                    system_prompt=(
                        "You are the Intelligence Lead. Your mission is to orchestrate deep market & competitor intelligence tasks.\n\n"
                        "## Core Responsibilities:\n"
                        "1. Break down strategic market inquiries into discrete research and data extraction steps.\n"
                        "2. Delegate web crawling and competitor research to the Market Researcher.\n"
                        "3. Delegate quantitative pricing, margins, and trend analysis to the Pricing Analyst.\n"
                        "4. Review intermediate outputs and instruct the Report Writer to synthesize a final executive brief.\n\n"
                        "## Operational Constraints:\n"
                        "- Always cite verifiable sources and dates.\n"
                        "- Highlight actionable insights, threats, and market opportunities."
                    ),
                ),
                ArchitectAgentBlueprint(
                    name="Market Researcher",
                    role="Web Discovery & Competitor Monitor",
                    icon="Search",
                    color="cyan",
                    delegates_to=[],
                    skills=["web_search"],
                    system_prompt=(
                        "You are the Market Researcher. You specialize in live web discovery, news aggregation, and competitor tracking.\n\n"
                        "## Guidelines:\n"
                        "- Search online for latest competitor catalog changes, feature announcements, and customer sentiment.\n"
                        "- Structure your findings with clear headings, bullet points, and source URLs."
                    ),
                ),
                ArchitectAgentBlueprint(
                    name="Pricing Analyst",
                    role="Quantitative Benchmark & Data Specialist",
                    icon="Database",
                    color="blue",
                    delegates_to=[],
                    skills=["search_knowledge", "filesystem_tools"],
                    system_prompt=(
                        "You are the Pricing Analyst. You crunch competitive price tiers, discount strategies, and feature matrices.\n\n"
                        "## Guidelines:\n"
                        "- Organize comparison data into Markdown tables with columns: Competitor, Product, Price, Value Proposition, Pros/Cons.\n"
                        "- Calculate variance and percentage differences where relevant."
                    ),
                ),
                ArchitectAgentBlueprint(
                    name="Report Writer",
                    role="Executive Summary & Markdown Formatter",
                    icon="PenTool",
                    color="violet",
                    delegates_to=[],
                    skills=["filesystem_tools"],
                    system_prompt=(
                        "You are the Report Writer. You transform raw intelligence data into polished, board-ready executive summaries.\n\n"
                        "## Guidelines:\n"
                        "- Use clear typography, callout alerts, summary tables, and prioritized recommendation sections.\n"
                        "- Deliver crisp Markdown files ready for presentation."
                    ),
                ),
            ],
        )

    if any(k in g for k in ("code", "svilupp", "dev", "bug", "software", "api", "refactor", "test", "python", "react", "frontend", "backend")):
        return ArchitectWorkforceBlueprint(
            team_name="Full-Stack Engineering & QA",
            description="Engineering squad dedicated to automated code review, architectural design, bug fixing, and test generation.",
            icon="Code",
            color="blue",
            entry_agent="Tech Lead",
            generation_source="heuristic",
            suggested_starter_tasks=[
                "Review the codebase for security vulnerabilities and performance bottlenecks.",
                "Implement unit and integration tests for recent API changes.",
                "Design and document a clean architecture refactoring plan.",
            ],
            agents=[
                ArchitectAgentBlueprint(
                    name="Tech Lead",
                    role="Software Architect & Orchestrator",
                    icon="Code",
                    color="blue",
                    delegates_to=["Code Specialist", "QA & Test Engineer"],
                    skills=["filesystem_tools", "terminal_sandbox", "search_knowledge"],
                    system_prompt=(
                        "You are the Tech Lead. You orchestrate software engineering, architectural compliance, and code quality.\n\n"
                        "## Workflow:\n"
                        "1. Analyze technical requirements, project file structures, and dependencies.\n"
                        "2. Formulate implementation plans and delegate feature code / fixes to Code Specialist.\n"
                        "3. Delegate unit testing, test suites, and edge-case verification to QA & Test Engineer.\n"
                        "4. Inspect patches before approving final execution."
                    ),
                ),
                ArchitectAgentBlueprint(
                    name="Code Specialist",
                    role="Full-Stack Implementation & Refactoring",
                    icon="Terminal",
                    color="indigo",
                    delegates_to=[],
                    skills=["filesystem_tools", "terminal_sandbox"],
                    system_prompt=(
                        "You are the Code Specialist. You write robust, maintainable, idiomatic code adhering to best practices.\n\n"
                        "## Standards:\n"
                        "- Keep functions focused, strictly typed, and self-documenting.\n"
                        "- Produce clean diffs and preserve existing architectural conventions."
                    ),
                ),
                ArchitectAgentBlueprint(
                    name="QA & Test Engineer",
                    role="Test Suite & Validation Specialist",
                    icon="ShieldCheck",
                    color="emerald",
                    delegates_to=[],
                    skills=["filesystem_tools", "terminal_sandbox"],
                    system_prompt=(
                        "You are the QA & Test Engineer. Your objective is 100% test coverage and resilience verification.\n\n"
                        "## Standards:\n"
                        "- Write deterministic unit tests, mocking external I/O where appropriate.\n"
                        "- Verify edge cases, boundary conditions, and regression tests."
                    ),
                ),
            ],
        )

    if any(k in g for k in ("bilanc", "finanz", "finan", "kpi", "invest", "dati", "tax", "report", "contabil")):
        return ArchitectWorkforceBlueprint(
            team_name="Financial & Operations Intelligence",
            description="Specialized workforce for financial modeling, balance sheet extraction, KPI tracking, and compliance reporting.",
            icon="Brain",
            color="rose",
            entry_agent="Finance Director",
            generation_source="heuristic",
            suggested_starter_tasks=[
                "Extract balance sheet KPI metrics and calculate YoY growth rates.",
                "Audit operational expenses and identify optimization opportunities.",
                "Generate an executive financial brief with cashflow projections.",
            ],
            agents=[
                ArchitectAgentBlueprint(
                    name="Finance Director",
                    role="Strategic Financial Coordinator",
                    icon="Brain",
                    color="rose",
                    delegates_to=["Data Auditor", "Financial Analyst"],
                    skills=["search_knowledge", "filesystem_tools"],
                    system_prompt=(
                        "You are the Finance Director. You oversee corporate financial planning, accounting audit, and strategic forecasting.\n\n"
                        "## Core Responsibilities:\n"
                        "- Coordinate quantitative metric extraction and verify numerical accuracy.\n"
                        "- Guide the Financial Analyst in building projection models and risk assessments.\n"
                        "- Deliver executive financial summaries tailored for leadership."
                    ),
                ),
                ArchitectAgentBlueprint(
                    name="Data Auditor",
                    role="Document Extraction & Numerical Validation",
                    icon="Database",
                    color="amber",
                    delegates_to=[],
                    skills=["search_knowledge", "filesystem_tools"],
                    system_prompt=(
                        "You are the Data Auditor. You extract balance sheet line items, cashflows, and financial records from documents.\n\n"
                        "## Rules:\n"
                        "- Ensure zero hallucination: every number must match source records.\n"
                        "- Format financial data into structured tables with units clearly labeled."
                    ),
                ),
                ArchitectAgentBlueprint(
                    name="Financial Analyst",
                    role="Modeling & KPI Synthesis",
                    icon="Layers",
                    color="pink",
                    delegates_to=[],
                    skills=["filesystem_tools"],
                    system_prompt=(
                        "You are the Financial Analyst. You compute ratios (EBITDA, margins, debt-to-equity) and project cashflows.\n\n"
                        "## Rules:\n"
                        "- Present scenario analyses (Conservative, Expected, Optimistic).\n"
                        "- Highlight key risks and actionable financial recommendations."
                    ),
                ),
            ],
        )

    # General / Tailored Fallback Blueprint
    words = [w.capitalize() for w in re.findall(r"\b\w+\b", goal)[:4] if len(w) > 2]
    topic_name = " ".join(words) if words else "Strategic Operations"

    return ArchitectWorkforceBlueprint(
        team_name=f"{topic_name} Squad",
        description=f"AI Workforce customized to execute and coordinate: {goal.strip()[:180]}",
        icon="Sparkles",
        color="violet",
        entry_agent="Squad Lead",
        generation_source="heuristic",
        suggested_starter_tasks=[
            f"Analyze requirements and formulate an execution plan for: {goal.strip()[:80]}",
            "Perform in-depth domain research and compile relevant knowledge.",
            "Draft and deliver the final structured output.",
        ],
        agents=[
            ArchitectAgentBlueprint(
                name="Squad Lead",
                role="Strategic Manager & Task Orchestrator",
                icon="Bot",
                color="violet",
                delegates_to=["Domain Specialist", "Content Synthesizer"],
                skills=["web_search", "search_knowledge", "filesystem_tools"],
                system_prompt=(
                    f"You are the Squad Lead responsible for fulfilling the overarching goal: {goal}.\n\n"
                    "## Operational Protocol:\n"
                    "1. Clarify objectives and decompose the workload into sequential or parallel subtasks.\n"
                    "2. Delegate specialized deep-dives to Domain Specialist.\n"
                    "3. Delegate formatting, synthesis, and documentation to Content Synthesizer.\n"
                    "4. Review and validate all final deliverable artifacts."
                ),
            ),
            ArchitectAgentBlueprint(
                name="Domain Specialist",
                role="Research & Execution Expert",
                icon="Search",
                color="blue",
                delegates_to=[],
                skills=["web_search", "search_knowledge"],
                system_prompt=(
                    f"You are the Domain Specialist focusing on: {goal}.\n\n"
                    "## Guidelines:\n"
                    "- Conduct targeted searches, consult knowledge documents, and extract accurate facts.\n"
                    "- Present intermediate findings with crisp clarity."
                ),
            ),
            ArchitectAgentBlueprint(
                name="Content Synthesizer",
                role="Technical Writer & Deliverable Producer",
                icon="FileText",
                color="emerald",
                delegates_to=[],
                skills=["filesystem_tools"],
                system_prompt=(
                    "You are the Content Synthesizer. You transform raw notes and research into high-impact deliverables.\n\n"
                    "## Guidelines:\n"
                    "- Produce clean Markdown files, executive summaries, and structured data outputs.\n"
                    "- Ensure professional tone, logical flow, and zero fluff."
                ),
            ),
        ],
    )


# -----------------------------------------------------------------------------
# AI-Powered Workforce Generation with Robust JSON Normalization
# -----------------------------------------------------------------------------

def _normalize_agent_blueprint(data: dict[str, Any], all_agent_names: list[str]) -> ArchitectAgentBlueprint:
    name = str(data.get("name") or "Agent").strip()[:60]
    role = str(data.get("role") or "Specialist").strip()[:120]
    prompt = str(data.get("system_prompt") or data.get("prompt") or f"You are {name}, specialized in {role}.").strip()

    raw_icon = str(data.get("icon") or "Bot")
    icon = raw_icon if raw_icon in SUPPORTED_AGENT_ICONS else "Bot"

    raw_color = str(data.get("color") or "violet").lower()
    color = raw_color if raw_color in SUPPORTED_AGENT_COLORS else "violet"

    raw_del = data.get("delegates_to") or []
    if isinstance(raw_del, str):
        delegates_to = [d.strip() for d in raw_del.split(",") if d.strip()]
    elif isinstance(raw_del, list):
        delegates_to = [str(d).strip() for d in raw_del if str(d).strip()]
    else:
        delegates_to = []

    # Filter delegates to only valid agents other than self
    delegates_to = [d for d in delegates_to if d != name]

    raw_skills = data.get("skills") or []
    if isinstance(raw_skills, list):
        skills = [str(s).strip() for s in raw_skills if str(s).strip()]
    else:
        skills = []

    return ArchitectAgentBlueprint(
        name=name,
        role=role,
        system_prompt=prompt,
        icon=icon,
        color=color,
        delegates_to=delegates_to,
        skills=skills,
        tools=[],
    )


async def generate_workforce_architecture(
    goal: str,
    provider: Any | None = None,
    model: str | None = None,
) -> ArchitectWorkforceBlueprint:
    """
    Generate an AI workforce blueprint. If an AIProvider is given and reachable, uses LLM
    structured reasoning. Otherwise falls back to heuristic generation with 100% reliability.
    """
    if not goal or not goal.strip():
        return build_heuristic_workforce("General Strategic Operations")

    if not provider:
        return build_heuristic_workforce(goal)

    system_instruction = (
        "You are Aether's AI Workforce Architect. Your task is to design an elite multi-agent team "
        "tailored to accomplish the user's specific business or technical goal.\n\n"
        "Return ONLY a valid JSON object strictly matching this schema with NO markdown code block wrappers:\n"
        "{\n"
        '  "team_name": "Short, catchy team name",\n'
        '  "description": "1-2 sentence description of team purpose",\n'
        '  "icon": "One of: Bot, Code, Search, Database, Brain, Compass, Layers, Zap, PenTool, ShieldCheck",\n'
        '  "color": "One of: violet, blue, emerald, amber, rose, cyan, indigo, pink",\n'
        '  "entry_agent": "Name of the leading agent",\n'
        '  "suggested_starter_tasks": ["Task 1", "Task 2", "Task 3"],\n'
        '  "agents": [\n'
        "    {\n"
        '      "name": "Agent Name",\n'
        '      "role": "Agent Role summary",\n'
        '      "icon": "One of supported icons",\n'
        '      "color": "One of supported colors",\n'
        '      "delegates_to": ["OtherAgentName"],\n'
        '      "skills": ["web_search", "filesystem_tools", "search_knowledge"],\n'
        '      "system_prompt": "Detailed multi-paragraph operational instructions for this agent with Goals, Guidelines, and Guardrails."\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Design between 2 and 4 highly complementary agents with unambiguous delegation topology."
    )

    user_prompt = f"Goal: {goal.strip()}"

    try:
        raw_response = None
        messages = [
            Message(role="system", content=system_instruction),
            Message(role="user", content=user_prompt),
        ]
        if hasattr(provider, "generate"):
            response = provider.generate(messages)
            raw_response = getattr(response, "content", str(response))
        elif hasattr(provider, "async_generate"):
            response = await provider.async_generate(messages)
            raw_response = getattr(response, "content", str(response))
        elif hasattr(provider, "chat"):
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                model=model,
                temperature=0.3,
            )
            raw_response = getattr(response, "content", str(response))
        elif hasattr(provider, "complete"):
            prompt_str = f"{system_instruction}\n\nUser: {user_prompt}\nAssistant JSON:"
            raw_response = await provider.complete(prompt_str, model=model, temperature=0.3)

        if not raw_response:
            logger.warning("Empty response from AI provider during architect generation. Using heuristic fallback.")
            return build_heuristic_workforce(goal)

        # Clean code fence if model wrapped in ```json ... ```
        cleaned_json = str(raw_response).strip()
        cleaned_json = re.sub(r"^```(?:json)?\s*", "", cleaned_json)
        cleaned_json = re.sub(r"\s*```$", "", cleaned_json)
        cleaned_json = cleaned_json.strip()

        parsed = json.loads(cleaned_json)
        if not isinstance(parsed, dict) or "agents" not in parsed or not isinstance(parsed["agents"], list) or len(parsed["agents"]) == 0:
            raise ValueError("Invalid workforce schema returned by model")

        agent_names = [str(a.get("name", "")).strip() for a in parsed["agents"] if isinstance(a, dict)]
        normalized_agents = [_normalize_agent_blueprint(a, agent_names) for a in parsed["agents"] if isinstance(a, dict)]

        team_name = str(parsed.get("team_name") or "Custom Squad").strip()[:80]
        desc = str(parsed.get("description") or f"Workforce designed for {goal[:100]}").strip()[:300]
        icon = str(parsed.get("icon") or "Layers")
        color = str(parsed.get("color") or "violet").lower()
        if color not in SUPPORTED_AGENT_COLORS:
            color = "violet"
        if icon not in SUPPORTED_AGENT_ICONS:
            icon = "Layers"

        entry_agent = str(parsed.get("entry_agent") or (normalized_agents[0].name if normalized_agents else "Lead")).strip()

        raw_tasks = parsed.get("suggested_starter_tasks") or []
        starter_tasks = [str(t).strip() for t in raw_tasks if str(t).strip()] if isinstance(raw_tasks, list) else []

        return ArchitectWorkforceBlueprint(
            team_name=team_name,
            description=desc,
            icon=icon,
            color=color,
            entry_agent=entry_agent,
            agents=normalized_agents,
            suggested_starter_tasks=starter_tasks,
            generation_source="ai",
        )

    except Exception as exc:
        logger.warning(f"AI Architect generation failed ({exc}). Falling back to heuristic blueprint.")
        return build_heuristic_workforce(goal)


# -----------------------------------------------------------------------------
# Magic Prompt Enhancer
# -----------------------------------------------------------------------------

def build_heuristic_enhanced_prompt(
    raw_prompt: str,
    role: str | None = None,
    agent_name: str | None = None,
    team_name: str | None = None,
) -> str:
    """Deterministic prompt enhancement structuring raw intent into robust sections."""
    name = agent_name.strip() if agent_name else "Agent"
    r = role.strip() if role else "Autonomous Specialist"
    base_intent = raw_prompt.strip()

    return (
        f"You are {name}, operating as the {r}"
        + (f" in the '{team_name}' workforce." if team_name else ".\n\n")
        + f"## 🎯 Primary Objective & Role:\n{base_intent}\n\n"
        "## 📋 Operational Guidelines:\n"
        "1. Break complex requests into clear, verifiable steps before execution.\n"
        "2. Consult workspace files, system knowledge, and available tools when data or verification is needed.\n"
        "3. Provide concise, high-signal responses with zero conversational fluff.\n\n"
        "## 📦 Deliverable Format:\n"
        "- Structure technical findings using Markdown headers, lists, and code blocks.\n"
        "- When providing code or file edits, preserve existing conventions and ensure testability.\n\n"
        "## 🛡️ Guardrails & Constraints:\n"
        "- Do not guess or hallucinate facts; explicitly state assumptions when data is absent.\n"
        "- Maintain security and verify all inputs before invoking file or terminal tools."
    )


async def enhance_system_prompt(
    raw_prompt: str,
    role: str | None = None,
    agent_name: str | None = None,
    team_name: str | None = None,
    provider: Any | None = None,
    model: str | None = None,
) -> str:
    """
    Enhance a short or draft prompt into an enterprise-grade agent instruction set.
    Preserves 100% of user intent while adding structured guidelines and guardrails.
    """
    if not raw_prompt or not raw_prompt.strip():
        return build_heuristic_enhanced_prompt(raw_prompt or "Execute assigned tasks with precision.", role, agent_name, team_name)

    if not provider:
        return build_heuristic_enhanced_prompt(raw_prompt, role, agent_name, team_name)

    instruction = (
        "You are Aether's Prompt Engineering Assistant. Enhance the provided draft agent instructions "
        "into a structured, professional, production-ready system prompt for an autonomous AI agent.\n\n"
        "Requirements:\n"
        "- Preserve the exact domain, role intent, and tone from the user's input.\n"
        "- Organize into clear Markdown sections: Objective, Workflow/Guidelines, Output Format, and Guardrails.\n"
        "- Keep it actionable, crisp, and high-impact. Do NOT wrap in JSON or conversational introductory text."
    )

    user_content = (
        f"Agent Name: {agent_name or 'Agent'}\n"
        f"Role: {role or 'Specialist'}\n"
        f"Team Context: {team_name or 'General'}\n"
        f"Draft Prompt: {raw_prompt.strip()}"
    )

    try:
        messages = [
            Message(role="system", content=instruction),
            Message(role="user", content=user_content),
        ]
        if hasattr(provider, "generate"):
            resp = provider.generate(messages)
            result = getattr(resp, "content", str(resp)).strip()
            if result:
                return result
        elif hasattr(provider, "async_generate"):
            resp = await provider.async_generate(messages)
            result = getattr(resp, "content", str(resp)).strip()
            if result:
                return result
        elif hasattr(provider, "chat"):
            resp = await provider.chat(
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": user_content},
                ],
                model=model,
                temperature=0.4,
            )
            result = getattr(resp, "content", str(resp)).strip()
            if result:
                return result
        elif hasattr(provider, "complete"):
            prompt_str = f"{instruction}\n\n{user_content}\nEnhanced System Prompt:"
            resp = await provider.complete(prompt_str, model=model, temperature=0.4)
            result = str(resp).strip()
            if result:
                return result
    except Exception as exc:
        logger.warning(f"AI Prompt Enhancement failed ({exc}). Using heuristic template.")

    return build_heuristic_enhanced_prompt(raw_prompt, role, agent_name, team_name)


# -----------------------------------------------------------------------------
# Single Agent Draft Generator ("✨ Crea con l'IA")
# -----------------------------------------------------------------------------

def build_heuristic_agent_draft(
    goal: str,
    available_skills: list[str] | None = None,
    available_agents: list[str] | None = None,
) -> ArchitectAgentBlueprint:
    """Deterministic fallback to draft an agent configuration from a user goal."""
    g = goal.lower()
    skills_pool = available_skills or ["search_knowledge", "web_search", "filesystem_tools", "run_command"]
    candidates = available_agents or []

    if any(k in g for k in ("ricerca", "research", "studia", "cerca", "search", "notizie", "news", "trend")):
        name = "Research Specialist"
        role = "Autonomous Researcher & Information Gatherer"
        icon = "Search"
        color = "cyan"
        matched_skills = [s for s in ["web_search", "search_knowledge"] if s in skills_pool] or ["search_knowledge"]
    elif any(k in g for k in ("scrivi", "writer", "report", "redigi", "sintesi", "document", "copy", "blog")):
        name = "Content Specialist"
        role = "Technical & Executive Synthesizer"
        icon = "FileText"
        color = "violet"
        matched_skills = [s for s in ["search_knowledge", "filesystem_tools"] if s in skills_pool] or ["search_knowledge"]
    elif any(k in g for k in ("codice", "code", "dev", "program", "script", "python", "bug", "software")):
        name = "Developer Specialist"
        role = "Software Engineer & Code Architect"
        icon = "Cpu"
        color = "blue"
        matched_skills = [s for s in ["filesystem_tools", "run_command", "search_knowledge"] if s in skills_pool] or ["filesystem_tools"]
    elif any(k in g for k in ("dati", "data", "finanz", "analis", "analyst", "excel", "bilanc", "prezz", "price")):
        name = "Data Analyst"
        role = "Quantitative & Structured Data Analyst"
        icon = "Database"
        color = "emerald"
        matched_skills = [s for s in ["filesystem_tools", "search_knowledge", "web_search"] if s in skills_pool] or ["search_knowledge"]
    elif any(k in g for k in ("sicurezza", "guard", "audit", "check", "review", "qualit")):
        name = "Quality & Safety Auditor"
        role = "Compliance & Verification Reviewer"
        icon = "ShieldCheck"
        color = "rose"
        matched_skills = [s for s in ["search_knowledge", "filesystem_tools"] if s in skills_pool] or ["search_knowledge"]
    else:
        name = "Autonomous Specialist"
        role = "Domain Task Execution Expert"
        icon = "Bot"
        color = "violet"
        matched_skills = [skills_pool[0]] if skills_pool else ["search_knowledge"]

    system_prompt = build_heuristic_enhanced_prompt(
        raw_prompt=goal.strip() or f"Execute tasks related to {role}.",
        role=role,
        agent_name=name,
    )

    return ArchitectAgentBlueprint(
        name=name,
        role=role,
        icon=icon if icon in SUPPORTED_AGENT_ICONS else "Bot",
        color=color if color in SUPPORTED_AGENT_COLORS else "violet",
        skills=matched_skills,
        delegates_to=[],
        system_prompt=system_prompt,
    )


async def generate_agent_draft(
    goal: str,
    available_skills: list[str] | None = None,
    available_agents: list[str] | None = None,
    provider: Any | None = None,
    model: str | None = None,
) -> ArchitectAgentBlueprint:
    """
    Draft a comprehensive agent configuration (name, role, icon, color, prompt, skills, delegates_to)
    from a natural language objective. Everything remains 100% user-editable before saving.
    """
    if not goal or not goal.strip():
        return build_heuristic_agent_draft("Autonomous specialist", available_skills, available_agents)

    if not provider:
        return build_heuristic_agent_draft(goal, available_skills, available_agents)

    skills_hint = f"Available skills in workspace: {', '.join(available_skills)}" if available_skills else "Common skills: search_knowledge, web_search, filesystem_tools, run_command"
    agents_hint = f"Other available agents in team: {', '.join(available_agents)}" if available_agents else "No other agents currently registered in team."

    system_instruction = (
        "You are Aether's Agent Architect. The user wants to create a new AI agent and provided an informal goal.\n"
        "Generate a complete, production-grade agent configuration in STRICT JSON format matching this schema:\n\n"
        "{\n"
        '  "name": "Short Professional Name (e.g. Financial Analyst)",\n'
        '  "role": "Concise Role Description (e.g. Extracts and compares balance sheets)",\n'
        f'  "icon": "One of: {", ".join(SUPPORTED_AGENT_ICONS)}",\n'
        f'  "color": "One of: {", ".join(SUPPORTED_AGENT_COLORS)}",\n'
        '  "skills": ["relevant_skill_1", "relevant_skill_2"],\n'
        '  "delegates_to": ["OtherAgentName"],\n'
        '  "system_prompt": "Detailed multi-section system prompt (Objectives, Guidelines, Output Format, Guardrails)."\n'
        "}\n\n"
        f"{skills_hint}\n"
        f"{agents_hint}\n"
        "Respond ONLY with the JSON object."
    )

    user_prompt = f"Agent Goal: {goal.strip()}"

    try:
        raw_response = None
        messages = [
            Message(role="system", content=system_instruction),
            Message(role="user", content=user_prompt),
        ]
        if hasattr(provider, "generate"):
            resp = provider.generate(messages)
            raw_response = getattr(resp, "content", str(resp))
        elif hasattr(provider, "async_generate"):
            resp = await provider.async_generate(messages)
            raw_response = getattr(resp, "content", str(resp))
        elif hasattr(provider, "chat"):
            resp = await provider.chat(
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                model=model,
                temperature=0.3,
            )
            raw_response = getattr(resp, "content", str(resp))
        elif hasattr(provider, "complete"):
            prompt_str = f"{system_instruction}\n\nUser: {user_prompt}\nAssistant JSON:"
            resp = await provider.complete(prompt_str, model=model, temperature=0.3)
            raw_response = str(resp)

        if not raw_response:
            return build_heuristic_agent_draft(goal, available_skills, available_agents)

        cleaned = str(raw_response).strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("Parsed output is not a JSON object")

        name = str(parsed.get("name") or "Specialist").strip()[:60]
        role = str(parsed.get("role") or "Autonomous Specialist").strip()[:120]
        icon = str(parsed.get("icon") or "Bot").strip()
        if icon not in SUPPORTED_AGENT_ICONS:
            icon = "Bot"
        color = str(parsed.get("color") or "violet").strip().lower()
        if color not in SUPPORTED_AGENT_COLORS:
            color = "violet"

        skills = parsed.get("skills") or []
        if isinstance(skills, list):
            skills = [str(s).strip() for s in skills if str(s).strip()]
        else:
            skills = []

        delegates = parsed.get("delegates_to") or []
        if isinstance(delegates, list):
            valid_candidates = set(available_agents or [])
            delegates = [str(d).strip() for d in delegates if str(d).strip() and str(d).strip() in valid_candidates]
        else:
            delegates = []

        system_prompt = str(parsed.get("system_prompt") or "").strip()
        if not system_prompt or len(system_prompt) < 15:
            system_prompt = build_heuristic_enhanced_prompt(goal, role, name)

        return ArchitectAgentBlueprint(
            name=name,
            role=role,
            icon=icon,
            color=color,
            skills=skills,
            delegates_to=delegates,
            system_prompt=system_prompt,
        )

    except Exception as exc:
        logger.warning(f"AI Agent Draft generation failed ({exc}). Using heuristic fallback.")
        return build_heuristic_agent_draft(goal, available_skills, available_agents)

