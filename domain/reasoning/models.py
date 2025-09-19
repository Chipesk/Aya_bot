"""Core reasoning data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence


@dataclass(slots=True)
class DialoguePlan:
    intent: str
    tone: str
    emotion: str
    register: str
    response_length: str
    follow_up_strategy: str
    content_goals: List[str] = field(default_factory=list)
    forbid_topics: List[str] = field(default_factory=list)
    require_topics: List[str] = field(default_factory=list)
    safety_directives: List[str] = field(default_factory=list)
    style_mods: Dict[str, Any] = field(default_factory=dict)
    applied_rules: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def apply_effect(self, rule_id: str, effect: Dict[str, Any]) -> None:
        self.applied_rules.append(rule_id)
        for key, value in effect.items():
            if value is None:
                continue
            if key == "tone":
                self.tone = value
            elif key == "emotion":
                self.emotion = value
            elif key == "register":
                self.register = value
            elif key == "response_length":
                self.response_length = value
            elif key == "follow_up":
                self.follow_up_strategy = value
            elif key == "content_goals":
                self.content_goals = list({*self.content_goals, *value})
            elif key == "forbid_topics":
                self.forbid_topics = list({*self.forbid_topics, *value})
            elif key == "require_topics":
                self.require_topics = list({*self.require_topics, *value})
            elif key == "safety":
                self.safety_directives = list({*self.safety_directives, *value})
            elif key == "style_mods":
                self.style_mods.update(value)
            elif key == "metadata":
                self.metadata.update(value)


@dataclass(slots=True)
class ReasoningContext:
    user_message: str
    persona: Dict[str, Any]
    world_state: Dict[str, Any]
    memory_facts: Sequence[Dict[str, Any]]
    chat_history: Sequence[Dict[str, Any]]
    intent: str
    user_emotion: str
    affinity: int
    closeness: int
    adult_confirmed: bool
    flirt_level: str
    persona_traits: Sequence[str]
    memory_tags: Sequence[str]
    time_of_day: str
    weather_condition: str

    def as_policy_context(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "affinity": self.affinity,
            "closeness": self.closeness,
            "adult_confirmed": self.adult_confirmed,
            "flirt_level": self.flirt_level,
            "user_emotion": self.user_emotion,
            "persona_traits": list(self.persona_traits),
            "memory_tags": list(self.memory_tags),
            "time_of_day": self.time_of_day,
            "weather_condition": self.weather_condition,
        }
