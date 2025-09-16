# dialogue/planner.py
import re
from dataclasses import dataclass
from typing import Optional
from dialogue.emotion_tracker import Emotion

@dataclass
class Plan:
    topic: str            # e.g., "mood", "life", "study", "hobby", "food_drink", ...
    subtopic: str         # e.g., "shared_sadness", "ask_reason", "give_example"
    act: str              # "ack"|"ask"|"answer"|"reflect"|"encourage"|"joke"
    tone: str             # "plain"|"warm"|"supportive"|"curious"|"calm"
    length: str           # "one"|"short"|"medium"|"long"
    ask: bool             # ставить ли вопрос в конце

ASK_MORE_RE = re.compile(r"\b(расскажи|пример|поясни|что это|как это|почему)\b", re.I)

def plan_response(turn: int, user_text: str, last_topic: Optional[str], em: Optional[Emotion] = None) -> Plan:
    t = (user_text or "").strip()
    em = em or Emotion("neutral", "low")

    # 1) Если эмоция грусть/тревога — это главный контекст
    if em.label in ("sad", "anxiety", "tired"):
        topic = "mood"
        if ASK_MORE_RE.search(t):
            return Plan(topic, "explain_coping", "answer", "supportive", "short", False)
        # если собеседник тоже поделился эмоцией — разделяем и мягко уточняем
        if em.intensity in ("mid", "high"):
            return Plan(topic, "shared_sadness", "reflect", "supportive", "short", True)
        return Plan(topic, "check_reason", "ask", "supportive", "short", True)

    # 2) Если радость — поддерживаем и просим подробности
    if em.label == "joy":
        return Plan("mood", "share_joy", "encourage", "warm", "short", True)

    # 3) Если явная заинтересованность (interest) — отвечаем и даём пример
    if em.label == "interest" or ASK_MORE_RE.search(t):
        return Plan("topic_followup", "give_example", "answer", "plain", "medium", False)

    # 4) Иначе — плавное продолжение прошлой темы
    topic = last_topic or "life"
    return Plan(topic, "smalltalk_continue", "ack", "plain", "short", False)
