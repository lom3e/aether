"""
Workforce Intelligence package (Phase B Macro Slice 3).
Unifies Workforce Memory and Knowledge Graph retrieval into compact agent execution context.
"""
from __future__ import annotations

from aether.intelligence.models import (
    EvidenceSourceType,
    UnifiedEvidence,
    UnifiedIntelligenceResult,
)
from aether.intelligence.service import (
    DEFAULT_CONTEXT_MAX_ITEMS,
    DEFAULT_ITEM_EXCERPT_MAX_CHARS,
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_TOTAL_CHAR_BUDGET,
    INTELLIGENCE_BLOCK_HEADER,
    UnifiedIntelligenceService,
)

__all__ = [
    "EvidenceSourceType",
    "UnifiedEvidence",
    "UnifiedIntelligenceResult",
    "UnifiedIntelligenceService",
    "DEFAULT_MIN_RELEVANCE_SCORE",
    "DEFAULT_CONTEXT_MAX_ITEMS",
    "DEFAULT_TOTAL_CHAR_BUDGET",
    "DEFAULT_ITEM_EXCERPT_MAX_CHARS",
    "INTELLIGENCE_BLOCK_HEADER",
]
