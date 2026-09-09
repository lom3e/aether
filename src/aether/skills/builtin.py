"""
Built-in Skills for Aether AI Workforce.

Provides a core set of standard skills:
- coding: Professional software engineering, type safety, modular architecture, robust error handling.
- debugging: Root-cause problem diagnosis, systematic tracing, and targeted minimal fixes.
- code_review: Code quality evaluation, security boundary checks, performance optimization, and best practices.
- documentation: Technical writing, API specifications, clear code comments, and architectural walkthroughs.
"""
from __future__ import annotations

from aether.skills.skill import Skill
from aether.skills.registry import SkillRegistry


BUILTIN_SKILLS: list[Skill] = [
    Skill(
        name="coding",
        description="Professional software engineering, clean code architecture, type safety, modular design, and robust error handling.",
        version="1.0.0",
        instructions=(
            "When writing software code:\n"
            "- Design clean, modular, and maintainable implementations adhering to language idioms.\n"
            "- Implement strict input validation, edge case handling, and defensive error boundaries.\n"
            "- Maintain strong type safety and explicit return types.\n"
            "- Write clean, self-documenting code with clear variable and function names.\n"
            "- Verify that changes integrate smoothly without introducing regressions or side effects."
        ),
        metadata={"builtin": True, "category": "development"},
    ),
    Skill(
        name="debugging",
        description="Root-cause problem diagnosis, systematic debugging, tracing execution errors, and targeted minimal fixes.",
        version="1.0.0",
        instructions=(
            "When diagnosing and fixing bugs or errors:\n"
            "- Identify the exact root cause before proposing any code modification.\n"
            "- Formulate a testable hypothesis and verify it against observed errors and execution traces.\n"
            "- Implement the minimal targeted fix that resolves the issue cleanly.\n"
            "- Avoid speculative refactoring while debugging.\n"
            "- Validate that edge cases and downstream dependents are tested and preserved."
        ),
        metadata={"builtin": True, "category": "development"},
    ),
    Skill(
        name="code_review",
        description="Code quality evaluation, security vulnerability checks, performance optimization, and architectural adherence.",
        version="1.0.0",
        instructions=(
            "When conducting code review:\n"
            "- Verify logic correctness, boundary conditions, and algorithmic efficiency.\n"
            "- Check for security vulnerabilities, path traversal risks, and sensitive data leakage.\n"
            "- Identify anti-patterns, code duplication, and unnecessary complexity.\n"
            "- Ensure backward compatibility with existing public contracts and schemas.\n"
            "- Provide structured, actionable, and constructive feedback with concrete improvements."
        ),
        metadata={"builtin": True, "category": "quality"},
    ),
    Skill(
        name="documentation",
        description="Technical writing, API specifications, clear code comments, architectural documentation, and developer guides.",
        version="1.0.0",
        instructions=(
            "When generating technical documentation:\n"
            "- Structure content with clear markdown headings, concise descriptions, and accurate code examples.\n"
            "- Document parameter types, return values, exceptions, and side effects for APIs and tools.\n"
            "- Provide clear step-by-step guides and architecture overviews.\n"
            "- Ensure documentation reflects the exact reality of the codebase without speculation."
        ),
        metadata={"builtin": True, "category": "documentation"},
    ),
    Skill(
        name="web_search",
        description="Search live information across the web using DuckDuckGo to augment model knowledge with real-time data.",
        version="1.5.0",
        instructions="Use search queries to retrieve up-to-date facts, verify citations, and fetch external references.",
        metadata={"builtin": True, "category": "native", "permissions": ["net:http", "search:duckduckgo"]},
    ),
    Skill(
        name="filesystem_tools",
        description="Inspect directories, read project files, patch source code, and create workspace deliverables.",
        version="1.5.0",
        instructions="Execute local file reads and safe workspace modifications with strict path boundary validation.",
        metadata={"builtin": True, "category": "native", "permissions": ["fs:read", "fs:write", "fs:patch"]},
    ),
    Skill(
        name="knowledge_retrieval",
        description="Perform semantic and lexical search across indexed workspace and system knowledge documents.",
        version="1.5.0",
        instructions="Retrieve relevant knowledge graph entities, concepts, and memory notes to provide grounded context.",
        metadata={"builtin": True, "category": "native", "permissions": ["kb:read", "vectors:query"]},
    ),
    Skill(
        name="terminal_sandbox",
        description="Execute shell commands, run tests, compile builds, and verify code execution in a secure sandbox.",
        version="1.5.0",
        instructions="Run terminal commands in isolated sandboxed subshells, inspect standard output, and verify exit codes.",
        metadata={"builtin": True, "category": "native", "permissions": ["exec:shell", "sandbox:isolated"]},
    ),
    Skill(
        name="gmail_integration",
        description="Read, search, draft, and organize emails and thread communications through Google Workspace APIs.",
        version="1.0.0",
        instructions="Prepare email drafts and summarize thread communications with user approval.",
        metadata={"builtin": True, "category": "integration", "permissions": ["email:read", "email:draft"]},
    ),
    Skill(
        name="github_tools",
        description="Connect private repositories, create pull requests, review issues, and synchronize project trees.",
        version="1.2.0",
        instructions="Interact with Git branches, inspect diffs, and create PRs with safety checks.",
        metadata={"builtin": True, "category": "integration", "permissions": ["git:read", "git:commit"]},
    ),
    Skill(
        name="slack_notifications",
        description="Broadcast task updates, human-in-the-loop approvals, and workflow notifications to Slack channels.",
        version="1.0.0",
        instructions="Post structured notifications and workflow alerts to configured team Slack channels.",
        metadata={"builtin": True, "category": "integration", "permissions": ["chat:write"]},
    ),
]


def get_builtin_skills() -> list[Skill]:
    """Return a list of all standard built-in skills."""
    return list(BUILTIN_SKILLS)


def get_default_skill_registry() -> SkillRegistry:
    """Create and return a SkillRegistry populated with all standard built-in skills."""
    registry = SkillRegistry()
    for skill in BUILTIN_SKILLS:
        registry.register(skill)
    return registry
