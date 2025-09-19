from __future__ import annotations
# mypy: ignore-errors

from pathlib import Path
from typing import Any, Dict

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest_asyncio

from domain.memory.manager import MemoryManager
from domain.persona.service import PersonaService
from domain.policies.loader import load_policy_bundle
from domain.reasoning.decision_engine import DecisionEngine
from domain.world_state.service import WorldStateService
from memory.chat_history import ChatHistoryRepo
from memory.facts_repo import FactsRepo
from memory.repo import MemoryRepo
from orchestrator.aya_brain import AyaBrain
from services.world_state import WorldState
from storage.db import DB


class DummyLLM:
    async def chat(self, messages, model: str = "") -> Dict[str, str]:  # pragma: no cover - simple stub
        return {"role": "assistant", "content": "stub"}

    async def health_check(self) -> tuple[bool, str]:
        return False, "stub"

    async def aclose(self) -> None:  # pragma: no cover - simple stub
        return None


@pytest_asyncio.fixture
async def db(tmp_path) -> DB:
    database = DB(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def memory_stack(db: DB):
    memory_repo = MemoryRepo(db)
    chat_history = ChatHistoryRepo(db)
    facts_repo = FactsRepo(db)
    memory_manager = MemoryManager(memory_repo, facts_repo, chat_history)
    return memory_repo, chat_history, facts_repo, memory_manager


@pytest_asyncio.fixture
async def make_brain(memory_stack):
    memory_repo, chat_history, facts_repo, memory_manager = memory_stack
    persona_service = PersonaService()
    policy_bundle = load_policy_bundle(tmp_policy_dir())
    decision_engine = DecisionEngine(policy_bundle)

    async def factory(world_payload: Dict[str, Any] | None = None) -> AyaBrain:
        async def fetcher():
            return _world_stub(world_payload or {})

        world_backend = WorldState(db=memory_repo.db, fetcher=fetcher, ttl_sec=10)
        world_service = WorldStateService(world_backend)
        return AyaBrain(
            DummyLLM(),
            memory_repo,
            memory_manager,
            world_service,
            persona_service,
            decision_engine,
            facts_repo,
        )

    return factory


@pytest_asyncio.fixture
async def brain(make_brain):
    return await make_brain(None)


def tmp_policy_dir() -> Path:
    return Path("policies")


def _world_stub(extra: Dict[str, Any]) -> Dict[str, Any]:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Europe/Moscow"))
    payload = {
        "city": "Санкт-Петербург",
        "local_time_iso": now.isoformat(timespec="seconds"),
        "weather": {"temp_c": 12, "is_rainy": False},
    }
    payload.update(extra)
    return payload
