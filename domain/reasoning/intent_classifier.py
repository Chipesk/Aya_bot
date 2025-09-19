"""Lightweight rule-based intent classifier."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Intent = Literal[
    "greeting",
    "farewell",
    "weather",
    "time",
    "date",
    "memory_query",
    "flirt",
    "plan",
    "smalltalk",
    "sos",
    "unknown",
]


@dataclass(slots=True)
class IntentResult:
    intent: Intent
    confidence: float


_WEATHER_RE = re.compile(r"\b(какая|что\s+по)\s+погод[аеы]\b", re.IGNORECASE)
_TIME_RE = re.compile(r"\b(который\s+час|сколько\s+(?:сейчас\s+)?времени)\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(какая\s+сегодня\s+дата|какое\s+число)\b", re.IGNORECASE)
_GREETING_RE = re.compile(r"\b(привет|здравствуй|доброе\s+утро|добрый\s+(?:день|вечер))\b", re.IGNORECASE)
_FAREWELL_RE = re.compile(r"\b(пока|до\s+свидания|спокойной\s+ночи)\b", re.IGNORECASE)
_MEMORY_RE = re.compile(r"\b(что\s+ты\s+(?:помнишь|запомнила)\s+обо\s+мне)\b", re.IGNORECASE)
_FLIRT_RE = re.compile(r"флирт|поцелу\w*|романтик\w*|мило\s+говори", re.IGNORECASE)
_SOS_RE = re.compile(r"\b(помоги|плохо|депрессия|тревога|я\s+сломал(ся)?|не\s+справляюсь)\b", re.IGNORECASE)
_PLAN_RE = re.compile(r"\b(план|что\s+делать|как\s+провести|куда\s+сходить)\b", re.IGNORECASE)


def classify_intent(text: str) -> IntentResult:
    if not text:
        return IntentResult("unknown", 0.0)
    stripped = text.strip()
    lower = stripped.lower()
    if _SOS_RE.search(lower):
        return IntentResult("sos", 0.9)
    if _WEATHER_RE.search(lower):
        return IntentResult("weather", 0.85)
    if _TIME_RE.search(lower):
        return IntentResult("time", 0.8)
    if _DATE_RE.search(lower):
        return IntentResult("date", 0.7)
    if _MEMORY_RE.search(lower):
        return IntentResult("memory_query", 0.75)
    if _FLIRT_RE.search(lower):
        return IntentResult("flirt", 0.6)
    if _PLAN_RE.search(lower):
        return IntentResult("plan", 0.6)
    if _GREETING_RE.search(lower):
        return IntentResult("greeting", 0.6)
    if _FAREWELL_RE.search(lower):
        return IntentResult("farewell", 0.6)
    if len(lower) <= 3:
        return IntentResult("smalltalk", 0.3)
    return IntentResult("smalltalk", 0.4)
