"""
Privacy and Sanitization Engine for Workforce Memory.
Enforces strict anti-leakage boundaries: zero chain-of-thought, reasoning, system prompts, or secrets.
"""
from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEY_SUBSTRINGS = {
    "thought",
    "reasoning",
    "chain_of_thought",
    "cot",
    "system_prompt",
    "prompt_template",
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
    "private_key",
    "cookie",
    "access_token",
    "bearer",
    "credentials",
}

COT_PATTERNS = [
    re.compile(r"<thought(?:>|\s[^>]*>).*?</thought>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<thinking(?:>|\s[^>]*>).*?</thinking>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<reasoning(?:>|\s[^>]*>).*?</reasoning>", re.DOTALL | re.IGNORECASE),
    re.compile(r"^System\s+Prompt\s*:.*$", re.MULTILINE | re.IGNORECASE),
]

SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"gho_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE),
    re.compile(r"(?:api[_\-]?key|secret|password|token)\s*[:=]\s*[^\s\n]+", re.IGNORECASE),
]


def is_sensitive_key(key: str) -> bool:
    """Check if a dictionary key matches any forbidden sensitive patterns."""
    k_lower = key.lower()
    return any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS)


def sanitize_memory_text(text: str) -> str:
    """
    Sanitizes plain text content by redacting detected API tokens, credential patterns,
    and removing any internal CoT (chain of thought) or system prompts.
    """
    if not text or not isinstance(text, str):
        return ""
    sanitized = text

    # 1. Strip CoT and thinking blocks
    for cot_pattern in COT_PATTERNS:
        sanitized = cot_pattern.sub("", sanitized)

    # 2. Redact credential and secret patterns
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)

    return sanitized.strip()


def sanitize_memory_data(val: Any) -> Any:
    """
    Recursively sanitize dictionaries and lists to eliminate any private reasoning, CoT or secrets.
    """
    if isinstance(val, dict):
        cleaned: dict[str, Any] = {}
        for k, v in val.items():
            if is_sensitive_key(k):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_memory_data(v)
        return cleaned
    elif isinstance(val, list):
        return [sanitize_memory_data(item) for item in val]
    elif isinstance(val, str):
        return sanitize_memory_text(val)
    return val
