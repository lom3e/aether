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
