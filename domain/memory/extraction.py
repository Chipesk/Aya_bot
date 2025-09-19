"""Simple fact extraction utilities."""
from __future__ import annotations

import re
from typing import List

from .models import Fact

_AGE_RE = re.compile(r"\bмне\s+(?P<age>\d{1,3})\b", re.IGNORECASE)
_INTOLERANCE_RE = re.compile(r"\bнепереносимост[ьи]\s+(?P<item>[а-яa-z\s]+)\b", re.IGNORECASE)
_LOCATION_RE = re.compile(r"\b(живу|живет|живём|я\s+из)\s+(?P<city>[а-яa-z\s\-]+)\b", re.IGNORECASE)
_NAME_RE = re.compile(r"\bменя\s+зовут\s+(?P<name>[а-яa-z\-]{2,25})\b", re.IGNORECASE)


def _norm(text: str) -> str:
    return text.strip().title()


def extract_facts(text: str, *, subject: str) -> List[Fact]:
    if not text:
        return []
    facts: List[Fact] = []
    for match in _AGE_RE.finditer(text):
        age = int(match.group("age"))
        if 5 <= age <= 120:
            facts.append(Fact(subject, "age", str(age), confidence=0.9, tags=("profile", "age")))
    for match in _INTOLERANCE_RE.finditer(text):
        item = match.group("item").strip().lower()
        facts.append(Fact(subject, "intolerance", item, confidence=0.8, tags=("health",)))
    for match in _LOCATION_RE.finditer(text):
        city = _norm(match.group("city"))
        facts.append(Fact(subject, "location", city, confidence=0.7, tags=("location",)))
    for match in _NAME_RE.finditer(text):
        name = _norm(match.group("name"))
        facts.append(Fact(subject, "name", name, confidence=0.95, tags=("identity",)))
    return facts
