"""High level memory management."""
# mypy: ignore-errors
from __future__ import annotations

from typing import List, Sequence

from domain.memory.extraction import extract_facts
from domain.memory.models import Fact, MemoryMetrics

from memory.chat_history import ChatHistoryRepo
from memory.facts_repo import FactsRepo
from memory.repo import MemoryRepo


_TOPIC_PREDICATES = {
    "age": ("age",),
    "health": ("intolerance",),
    "location": ("location",),
    "identity": ("name",),
    "music": ("music_artists",),
}


class MemoryManager:
    def __init__(self, memory_repo: MemoryRepo, facts_repo: FactsRepo, chat_history: ChatHistoryRepo):
        self.memory_repo = memory_repo
        self.facts_repo = facts_repo
        self.chat_history = chat_history
        self.metrics = MemoryMetrics()

    async def store_user_message(self, tg_user_id: int, message: str, *, message_id: int | None = None) -> List[Fact]:
        facts = extract_facts(message, subject=str(tg_user_id))
        if facts:
            payload = [
                {"predicate": f.predicate, "object": f.object, "confidence": f.confidence, "tags": list(f.tags)}
                for f in facts
            ]
            await self.facts_repo.upsert_many(tg_user_id, payload, source_msg_id=message_id)
            self.metrics.facts_stored += len(facts)
        return facts

    async def recall(self, tg_user_id: int, topic: str, limit: int = 3) -> List[Fact]:
        self.metrics.recall_attempts += 1
        predicates = _TOPIC_PREDICATES.get(topic)
        rows: Sequence[dict] = []
        if predicates:
            all_facts = await self.facts_repo.get_all(tg_user_id, limit=50)
            rows = [row for row in all_facts if row["predicate"] in predicates][:limit]
        else:
            rows = await self.facts_repo.search(tg_user_id, topic, limit)
        facts = [Fact(str(tg_user_id), r["predicate"], r["object"], r["confidence"]) for r in rows]
        if facts:
            self.metrics.facts_recalled += len(facts)
        return facts

    async def remember_dialogue(self, tg_user_id: int, role: str, content: str) -> None:
        await self.memory_repo.db.add_chat_message(tg_user_id, role, content)

    async def recall_recent_dialogue(self, tg_user_id: int, limit: int = 6):
        return await self.chat_history.last(tg_user_id, limit=limit)

    def snapshot_metrics(self) -> MemoryMetrics:
        return self.metrics
