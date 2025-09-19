"""Policy rule definitions for Aya."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence


@dataclass(slots=True)
class PolicyCondition:
    intents: Sequence[str] = ()
    min_affinity: Optional[int] = None
    max_affinity: Optional[int] = None
    min_closeness: Optional[int] = None
    require_adult: bool = False
    allow_when_not_adult: bool = True
    only_when_not_adult: bool = False
    emotions: Sequence[str] = ()
    weather: Sequence[str] = ()
    time_of_day: Sequence[str] = ()
    persona_traits: Sequence[str] = ()
    memory_tags: Sequence[str] = ()

    def matches(self, context: Dict[str, Any]) -> bool:
        intent = context.get("intent")
        if self.intents and intent not in self.intents:
            return False
        affinity = context.get("affinity", 0)
        if self.min_affinity is not None and affinity < self.min_affinity:
            return False
        if self.max_affinity is not None and affinity > self.max_affinity:
            return False
        closeness = context.get("closeness", 0)
        if self.min_closeness is not None and closeness < self.min_closeness:
            return False
        adult_ok = bool(context.get("adult_confirmed", False))
        if self.require_adult and not adult_ok:
            return False
        if not adult_ok and not self.allow_when_not_adult:
            return False
        if self.only_when_not_adult and adult_ok:
            return False
        if self.emotions:
            if context.get("user_emotion") not in self.emotions:
                return False
        if self.weather:
            weather_tag = context.get("weather_condition")
            if weather_tag not in self.weather:
                return False
        if self.time_of_day:
            tod = context.get("time_of_day")
            if tod not in self.time_of_day:
                return False
        if self.persona_traits:
            persona_tags = set(context.get("persona_traits", ()))
            if not persona_tags.issuperset(self.persona_traits):
                return False
        if self.memory_tags:
            mem_tags = set(context.get("memory_tags", ()))
            if not set(self.memory_tags).intersection(mem_tags):
                return False
        return True


@dataclass(slots=True)
class PolicyEffect:
    tone: Optional[str] = None
    emotion: Optional[str] = None
    register: Optional[str] = None
    response_length: Optional[str] = None
    follow_up: Optional[str] = None
    content_goals: List[str] = field(default_factory=list)
    forbid_topics: List[str] = field(default_factory=list)
    require_topics: List[str] = field(default_factory=list)
    safety: List[str] = field(default_factory=list)
    style_mods: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def merge(self, other: "PolicyEffect") -> "PolicyEffect":
        effect = PolicyEffect(
            tone=other.tone or self.tone,
            emotion=other.emotion or self.emotion,
            register=other.register or self.register,
            response_length=other.response_length or self.response_length,
            follow_up=other.follow_up or self.follow_up,
            content_goals=list({*self.content_goals, *other.content_goals}),
            forbid_topics=list({*self.forbid_topics, *other.forbid_topics}),
            require_topics=list({*self.require_topics, *other.require_topics}),
            safety=list({*self.safety, *other.safety}),
            style_mods={**self.style_mods, **other.style_mods},
            metadata={**self.metadata, **other.metadata},
        )
        return effect


@dataclass(slots=True)
class PolicyRule:
    id: str
    description: str
    priority: int
    condition: PolicyCondition
    effect: PolicyEffect

    def applies_to(self, context: Dict[str, Any]) -> bool:
        return self.condition.matches(context)


@dataclass
class PolicyBundle:
    content: Iterable[PolicyRule]
    style: Iterable[PolicyRule]
    safety: Iterable[PolicyRule]

    def all_rules(self) -> List[PolicyRule]:
        out: List[PolicyRule] = []
        for group in (self.content, self.style, self.safety):
            out.extend(group)
        return out
