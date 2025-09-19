"""Memory domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FactConfidence = Literal["low", "medium", "high"]


@dataclass(slots=True)
class Fact:
    subject: str
    predicate: str
    object: str
    confidence: float
    tags: tuple[str, ...] = ()


@dataclass(slots=True)
class MemoryMetrics:
    facts_stored: int = 0
    facts_recalled: int = 0
    recall_attempts: int = 0

    @property
    def recall_hit_rate(self) -> float:
        if self.recall_attempts == 0:
            return 0.0
        return self.facts_recalled / self.recall_attempts
