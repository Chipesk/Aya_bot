# orchestrator/integration_adapter.py
from typing import Tuple
from orchestrator.weather_gate import WEATHER_GATE
from orchestrator.planner import plan_turn
from dialogue.topic_threader import TOPICS
from dialogue.personal_palette import random_slice
from dialogue.style_guard import style_constraints

def augment_brief(user_text: str, brief: str, profile, last_two_assistant) -> Tuple[str, dict]:
    # enqueue topics
    TOPICS.enqueue_from_user(user_text)
    # plan
    pl = plan_turn(user_text, profile)
    # threads
    hook = TOPICS.maybe_hook()
    # weather
    weather_ok = WEATHER_GATE.allow(user_text)

    # smalltalk facts
    facts = random_slice(1)

    extra = []
    extra.append(f"STYLE.length={pl.style_len}")
    extra.append(f"ASK={'yes' if pl.ask else 'no'}")
    if hook:
        extra.append(f"ADD_CONCRETE_QUESTION: {hook}")
    extra.append(f"weather_allowed={'yes' if weather_ok else 'no'}")
    extra.append("SMALLTALK_FACTS:")
    for f in facts:
        extra.append(f"- {f}")
    extra.append("STYLE_GUARD:")
    extra.append(style_constraints(weather_ok))

    # merge
    if not brief.endswith("\n"):
        brief += "\n"
    brief += "\n" + "\n".join(extra) + "\n"
    meta = {"weather_allowed": weather_ok, "hook": hook, "plan": pl}
    return brief, meta
