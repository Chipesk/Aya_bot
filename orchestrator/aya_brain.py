"""Central orchestrator connecting intent detection, policies and NLG."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Sequence

from core.logging import get_logger
from domain.memory.manager import MemoryManager
from domain.persona.service import PersonaService
from domain.reasoning.decision_engine import DecisionEngine
from domain.reasoning.intent_classifier import classify_intent
from domain.reasoning.models import ReasoningContext
from domain.world_state.service import WorldStateService
from dialogue.humanizer import Humanizer
from memory.facts_repo import FactsRepo
from memory.repo import MemoryRepo
from services.deepseek_client import DeepSeekClient

log = get_logger("aya.brain")


@dataclass(slots=True)
class AyaResponse:
    text: str
    plan: Dict[str, Any]
    facts_used: Sequence[Dict[str, Any]]


class AyaBrain:
    def __init__(
        self,
        llm: DeepSeekClient,
        memory_repo: MemoryRepo,
        memory_manager: MemoryManager,
        world_state: WorldStateService,
        persona: PersonaService,
        decision_engine: DecisionEngine,
        facts_repo: FactsRepo,
    ) -> None:
        self.llm = llm
        self.memory_repo = memory_repo
        self.memory_manager = memory_manager
        self.world_state = world_state
        self.persona = persona
        self.decision_engine = decision_engine
        self.facts_repo = facts_repo
        self.humanizer = Humanizer()

    async def reset_user(self, tg_user_id: int) -> None:
        await self.memory_repo.set_affinity(tg_user_id, 0)
        await self.memory_repo.set_user_display_name(tg_user_id, "")
        await self.memory_repo.set_user_nickname(tg_user_id, "")
        await self.memory_repo.set_user_nickname_allowed(tg_user_id, False)
        await self.memory_repo.set_flirt_consent(tg_user_id, False)
        await self.memory_repo.set_flirt_level(tg_user_id, "off")

    async def respond(self, tg_user_id: int, user_text: str) -> AyaResponse:
        await self.memory_repo.touch_seen(tg_user_id)
        await self.memory_manager.remember_dialogue(tg_user_id, "user", user_text)
        await self.memory_manager.store_user_message(tg_user_id, user_text)

        persona_data = self.persona.data()
        persona_traits = self.persona.traits()
        world_snapshot = await self.world_state.snapshot()
        weather_condition = await self.world_state.weather_condition()

        intent_result = classify_intent(user_text)
        affinity = await self.memory_repo.get_affinity(tg_user_id)
        closeness = await self.memory_repo.get_affinity(tg_user_id)
        adult_confirmed = await self.memory_repo.get_adult_confirmed(tg_user_id)
        flirt_level = await self.memory_repo.get_flirt_level(tg_user_id)
        facts_recent = await self.facts_repo.get_all(tg_user_id, limit=25)

        policy_ctx = ReasoningContext(
            user_message=user_text,
            persona=persona_data,
            world_state=world_snapshot,
            memory_facts=facts_recent,
            chat_history=await self.memory_manager.recall_recent_dialogue(tg_user_id, limit=6),
            intent=intent_result.intent,
            user_emotion="neutral",
            affinity=affinity,
            closeness=closeness,
            adult_confirmed=adult_confirmed,
            flirt_level=flirt_level,
            persona_traits=tuple(persona_traits),
            memory_tags=tuple({row["predicate"] for row in facts_recent}),
            time_of_day=_time_of_day(world_snapshot.get("local_time_iso")),
            weather_condition=weather_condition,
        )

        plan = self.decision_engine.plan(policy_ctx)

        facts_for_output: List[Dict[str, Any]] = []
        if plan.intent in {"memory_query", "greeting"}:
            facts_for_output.extend(facts_recent[:5])
        for topic in plan.require_topics:
            facts_for_output.extend(await self._facts_for_topic(tg_user_id, topic))

        user_profile = await self._load_user_profile(tg_user_id)
        answer = self.humanizer.realize(
            plan,
            persona=persona_data,
            memory_facts=facts_for_output,
            world=world_snapshot,
            user_profile=user_profile,
        )

        await self.memory_manager.remember_dialogue(tg_user_id, "assistant", answer)

        log.info(
            "response",
            intent=plan.intent,
            applied_rules=plan.applied_rules,
            emotion=plan.emotion,
            follow_up=plan.follow_up_strategy,
            facts_used=len(facts_for_output),
        )

        return AyaResponse(text=answer, plan={"applied_rules": plan.applied_rules, "tone": plan.tone}, facts_used=facts_for_output)

    async def diagnostics(self, tg_user_id: int) -> Dict[str, Any]:
        metrics = self.memory_manager.snapshot_metrics()
        llm_ok, llm_note = await self.llm.health_check()
        return {
            "metrics": {
                "facts_stored": metrics.facts_stored,
                "facts_recalled": metrics.facts_recalled,
                "recall_attempts": metrics.recall_attempts,
                "recall_hit_rate": round(metrics.recall_hit_rate, 3),
            },
            "profile": await self._load_user_profile(tg_user_id),
            "persona_traits": self.persona.traits(),
            "policies": self.decision_engine.describe(),
            "llm": {"ok": llm_ok, "note": llm_note},
        }

    async def _load_user_profile(self, tg_user_id: int) -> Dict[str, Any]:
        name = await self.memory_repo.get_user_display_name(tg_user_id)
        prefs = await self.memory_repo.get_user_prefs(tg_user_id)
        return {
            "display_name": name,
            "nickname": prefs.get("nickname"),
            "nickname_allowed": prefs.get("nickname_allowed"),
        }

    async def _facts_for_topic(self, tg_user_id: int, topic: str) -> List[Dict[str, Any]]:
        topic_map = {
            "weather": [],
            "time": [],
            "identity": await self.memory_manager.recall(tg_user_id, "identity", limit=2),
            "age": await self.memory_manager.recall(tg_user_id, "age", limit=1),
            "health": await self.memory_manager.recall(tg_user_id, "health", limit=2),
        }
        rows = topic_map.get(topic)
        if rows is None:
            rows = await self.memory_manager.recall(tg_user_id, topic, limit=2)
        return [
            {"predicate": getattr(f, "predicate", f["predicate"] if isinstance(f, dict) else ""), "object": getattr(f, "object", f["object"] if isinstance(f, dict) else ""), "confidence": getattr(f, "confidence", f.get("confidence", 0.5) if isinstance(f, dict) else 0.5)}
            for f in rows
        ]


def _time_of_day(iso: Any) -> str:
    if not iso:
        return "unknown"
    try:
        dt = datetime.fromisoformat(str(iso))
    except ValueError:
        return "unknown"
    hour = dt.hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 23:
        return "evening"
    return "night"
