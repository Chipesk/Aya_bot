# orchestrator/planner.py
from dataclasses import dataclass
from typing import Optional
import re

@dataclass
class Plan:
    intent: str           # "answer" | "probe" | "continue_thread" | "close_promise" | "flirt"
    style_len: str        # "short" | "medium" | "long"
    ask: bool
    hook: Optional[str]   # конкретный вопрос, если есть

def plan_turn(user_text: str, profile) -> Plan:
    txt = (user_text or "").lower().strip()
    is_question = txt.endswith("?")
    looks_like_share = bool(re.search(r"\b(делал|сделал|занимаюсь|смотрел|читал|слушал|ката(л|юсь)|готовил|работал|учил|запустил|собираю|планирую)\w*\b", txt))
    if is_question:
        return Plan(intent="answer", style_len="medium", ask=True, hook=None)
    if looks_like_share:
        return Plan(intent="probe", style_len="medium", ask=True, hook=None)
    # fallback
    return Plan(intent="continue_thread", style_len="short", ask=True, hook=None)
