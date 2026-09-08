"""
Aether Learning & Correction Loop Package (Phase B — Slice 4).
"""
from aether.learning.models import (
    Correction,
    DistilledLesson,
    LearningEvent,
    LearningEventType,
    LearningScope,
    LearningVerificationStatus,
)
from aether.learning.service import LearningService
from aether.learning.store import LearningStore

__all__ = [
    "LearningEventType",
    "LearningVerificationStatus",
    "LearningScope",
    "LearningEvent",
    "Correction",
    "DistilledLesson",
    "LearningStore",
    "LearningService",
]
