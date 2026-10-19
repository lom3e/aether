"""Second opinion: the same question to up to three DIFFERENT configured models, plus an honest agreement summary.

The agreement is a textual comparison (shared content words and numbers). It says whether the models answered alike, not
which one is right: the UI states this. Every call goes through resolve_provider, so it is masked and ledgered like any other.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from typing import Any

from aether.core.execution import Message

MAX_OPINIONS = 3
_CLOUD = (("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY"), ("gemini", "GEMINI_API_KEY"), ("groq", "GROQ_API_KEY"))
_WORD = re.compile(r"[^\W_]{4,}", re.UNICODE)
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def configured_provider_names(workspace: Any) -> list[str]:
    """Providers that can really be reached: a stored key or an environment key (never read or returned)."""
    store = getattr(workspace, "secret_store", None)
    names: list[str] = []
    for name, env in _CLOUD:
        has = False
        if store is not None:
            try:
                has = bool(store.get_secret(f"provider_api_key:{name}"))
            except Exception:  # noqa: BLE001 - an unreadable vault means "not configured" here
                has = False
        if has or os.environ.get(env):
            names.append(name)
    return names


def _terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUM.findall(text)}


def compare(answers: list[str]) -> dict[str, Any]:
    """Pairwise overlap of content words; numbers that only some answers contain are listed as differences."""
    usable = [a for a in answers if a and a.strip()]
    if len(usable) < 2:
        return {"level": "single", "similarity": None, "differing_numbers": []}
    sims = []
    for a, b in combinations(usable, 2):
        ta, tb = _terms(a), _terms(b)
        union = ta | tb
        sims.append(len(ta & tb) / len(union) if union else 1.0)
    similarity = round(sum(sims) / len(sims), 2)
    sets = [_numbers(a) for a in usable]
    everything = set().union(*sets)
    common = set.intersection(*sets) if sets else set()
    differing = sorted(everything - common)[:12]
    level = "agree" if similarity >= 0.45 and not differing else "partial" if similarity >= 0.2 else "differ"
    if differing and level == "agree":
        level = "partial"
    return {"level": level, "similarity": similarity, "differing_numbers": differing}


def ask(workspace: Any, question: str, *, providers: list[str] | None = None, context: str = "", language: str = "it",
        resolver: Any = None) -> dict[str, Any]:
    """Runs the question on each provider in parallel. A failing provider is reported, never hidden or substituted."""
    from aether.privacy.scope import egress_scope
    from aether.providers.resolution import resolve_provider

    names = list(dict.fromkeys(providers or configured_provider_names(workspace)))[:MAX_OPINIONS]
    if len(names) < 2:
        return {"status": "unavailable", "reason": "needs_two_providers", "available": names}
    resolve = resolver or (lambda n: resolve_provider(workspace=workspace, preferred_provider_name=n))
    en = (language or "").lower().startswith("en")
    system = ("Answer the question directly and concisely." if en else "Rispondi alla domanda in modo diretto e conciso.")
    user = question.strip() if not context.strip() else f"{context.strip()}\n\n{question.strip()}"

    def one(name: str) -> dict[str, Any]:
        try:
            provider = resolve(name)
            if provider is None:
                return {"provider": name, "status": "failed", "reason": "not_configured"}
            with egress_scope(purpose="second_opinion"):
                response = provider.generate([Message(role="system", content=system), Message(role="user", content=user)])
            text = (getattr(response, "content", "") or "").strip()
            if not text:
                return {"provider": name, "status": "failed", "reason": "empty_response"}
            return {"provider": name, "model": getattr(response, "model", None) or getattr(getattr(provider, "config", None), "model", None),
                    "status": "ok", "content": text}
        except Exception as exc:  # noqa: BLE001
            return {"provider": name, "status": "failed", "reason": type(exc).__name__}

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        opinions = list(pool.map(one, names))
    summary = compare([o["content"] for o in opinions if o["status"] == "ok"])
    return {"status": "ok", "opinions": opinions, "agreement": summary}
