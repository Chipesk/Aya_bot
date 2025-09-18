import re
from dataclasses import dataclass
from typing import List, Optional
from dialogue.humanizer import SpeechProfile

import logging
logging.getLogger("aya").setLevel(logging.INFO)

def _dbg(tag, **kw):
    try:
        logging.getLogger("aya").info("[cadence] %s %s", tag, kw)
    except Exception:
        pass

@dataclass
class CadencePlan:
    target_len: str
    ask: bool
    formality: str
    imagery_cap: int
    clause_cap: int
    emoji_mirror: bool
    behavior: str

_WORDS = re.compile(r"\w+", re.UNICODE)
def _wc(s: str) -> int:
    return len(_WORDS.findall(s or ""))

def infer_cadence(user_text: str, last_two_assistant: List[str], profile: Optional[SpeechProfile] = None) -> CadencePlan:
    txt = (user_text or "").lower()
    n_words = _wc(txt)
    is_question = txt.strip().endswith("?")

    looks_like_share = bool(re.search(
        r"\b(делал|сделал|занимаюсь|смотрел|читал|слушал|ката(л|юсь)|готовил|работал|учил|запустил|собираю|планирую)\w*\b",
        txt, re.IGNORECASE))
    is_greeting = bool(re.search(r"\b(привет|здоров|салют|хай|доброе|добрый|добрый день)\b", txt))
    is_minimal = n_words <= 2 or txt in {"да","ага","ок","угу","ну","понял"}

    if is_question:
        target_len = "medium"
    elif looks_like_share:
        target_len = "medium"
    elif is_greeting or is_minimal:
        target_len = "short"
    else:
        target_len = "short"

    if profile:
        if profile.avg_words <= 8.0 or profile.short_bias > 0.65:
            target_len = "short" if n_words <= 6 else target_len

    if profile and profile.q_ratio >= 0.28:
        behavior = "proactive"
    elif profile and profile.q_ratio < 0.18:
        behavior = "reactive"
    else:
        behavior = "balanced"

    q_tail = sum(1 for t in last_two_assistant if (t or "").rstrip().endswith("?"))
    ask = False
    if is_question and q_tail == 0 and behavior != "reactive":
        ask = True
    else:
        can_proactive = (q_tail == 0) and (behavior in ("balanced","proactive"))
        if can_proactive and (n_words >= 4 or looks_like_share):
            ask = True

    imagery_cap = 1 if target_len in ("medium","long") and n_words >= 8 else 0
    clause_cap = 2 if target_len == "short" else 3
    if is_question:
        clause_cap = max(clause_cap,2)
        imagery_cap = 0

    formality = "plain" if target_len == "short" else "warm"
    emoji_mirror = any(ch in (user_text or "") for ch in "🙂😉❤️👍🔥")

    _dbg("decision", target_len=target_len, imagery_cap=imagery_cap,
         clause_cap=clause_cap, ask=ask, n_words=n_words,
         short_bias=getattr(profile, "short_bias", None))

    return CadencePlan(target_len, ask, formality, imagery_cap, clause_cap, emoji_mirror, behavior)
