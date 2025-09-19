"""Policy-driven decision engine."""
from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Iterable, List

from core.logging import get_logger
from domain.policies.models import PolicyBundle, PolicyEffect, PolicyRule

from .models import DialoguePlan, ReasoningContext

log = get_logger("decision_engine")


_DEFAULT_EFFECT = PolicyEffect(
    tone="warm",
    emotion="curious",
    register="casual",
    response_length="medium",
    follow_up="adaptive",
    content_goals=["acknowledge_user"],
)


class DecisionEngine:
    def __init__(self, bundle: PolicyBundle):
        self.bundle = bundle

    def _base_plan(self, ctx: ReasoningContext) -> DialoguePlan:
        return DialoguePlan(
            intent=ctx.intent,
            tone=_DEFAULT_EFFECT.tone or "warm",
            emotion=_DEFAULT_EFFECT.emotion or "curious",
            register=_DEFAULT_EFFECT.register or "casual",
            response_length=_DEFAULT_EFFECT.response_length or "medium",
            follow_up_strategy=_DEFAULT_EFFECT.follow_up or "adaptive",
            content_goals=list(_DEFAULT_EFFECT.content_goals),
        )

    def _apply_rules(self, plan: DialoguePlan, rules: Iterable[PolicyRule], ctx: Dict[str, object]) -> None:
        for rule in rules:
            if rule.applies_to(ctx):
                effect_dict = asdict(rule.effect)
                plan.apply_effect(rule.id, effect_dict)

    def plan(self, ctx: ReasoningContext) -> DialoguePlan:
        policy_ctx = ctx.as_policy_context()
        plan = self._base_plan(ctx)
        self._apply_rules(plan, self.bundle.content, policy_ctx)
        self._apply_rules(plan, self.bundle.style, policy_ctx)
        self._apply_rules(plan, self.bundle.safety, policy_ctx)

        # derived safety heuristics
        if ctx.intent == "sos" or "escalate" in plan.safety_directives:
            plan.follow_up_strategy = "grounding"
        if ctx.intent == "weather" and "weather" not in plan.require_topics:
            plan.require_topics.append("weather")
        if ctx.intent == "time" and "time" not in plan.require_topics:
            plan.require_topics.append("time")

        log.debug(
            "plan_ready",
            intent=ctx.intent,
            applied_rules=plan.applied_rules,
            tone=plan.tone,
            emotion=plan.emotion,
            follow_up=plan.follow_up_strategy,
        )
        return plan

    def describe(self) -> Dict[str, List[str]]:
        info: Dict[str, List[str]] = {"content": [], "style": [], "safety": []}
        for bucket, rules in (("content", self.bundle.content), ("style", self.bundle.style), ("safety", self.bundle.safety)):
            info[bucket] = [f"{r.id}: {r.description}" for r in rules]
        return info
