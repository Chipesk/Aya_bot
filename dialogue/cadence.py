# dialogue/cadence.py
import re
from dataclasses import dataclass
from typing import List, Optional
from dialogue.humanizer import SpeechProfile

@dataclass
class CadencePlan:
    target_len: str          # "one" | "short" | "medium" | "long"
    ask: bool                # задавать ли вопрос в конце
    formality: str           # "plain" | "warm"
    imagery_cap: int         # 0..1 (сколько образных вводок допустимо)
    clause_cap: int          # макс. число предложений
    emoji_mirror: bool
    behavior: str            # "reactive" | "balanced" | "proactive"

_WORDS = re.compile(r"\w+", re.UNICODE)

def _wc(s: str) -> int:
    return len(_WORDS.findall(s or ""))

def infer_cadence(
    user_text: str,
    last_two_assistant: List[str],
    profile: Optional[SpeechProfile] = None,
) -> CadencePlan:
    n = _wc(user_text)
    is_question = (user_text or "").strip().endswith("?")

    # --- базовая длина от пользователя (зеркалим)
    if n <= 2:
        target_len = "one"
    elif n <= 8:
        target_len = "short"
    elif n <= 22:
        target_len = "medium"
    else:
        target_len = "short"  # на простыни отвечаем короче

    # --- профиль пользователя корректирует
    if profile:
        if profile.avg_words <= 8.0 or profile.short_bias > 0.65:
            target_len = "one" if n <= 3 else "short"

    # --- поведение: если юзер часто спрашивает → можно проактивнее
    if profile and profile.q_ratio >= 0.28:
        behavior = "proactive"
    elif profile and profile.q_ratio < 0.18:
        behavior = "reactive"
    else:
        behavior = "balanced"

    # --- вопросы: если нас спросили — спрашиваем; иначе допускаем умеренную инициативу
    q_tail = sum(1 for t in last_two_assistant if (t or "").rstrip().endswith("?"))
    ask = False
    if is_question and q_tail == 0 and behavior != "reactive":
        ask = True
    else:
        # проактивная попытка: если нет хвоста из наших вопросов и поведение позволяет
        can_proactive = (q_tail == 0) and (behavior in ("balanced", "proactive"))
        n_words = n
        looks_like_share = bool(re.search(
            r"\b(ездил|катался|делал|получилось|смотрел|читал|готовил|работал|тренир|учил)\w*\b",
            (user_text or ""), re.IGNORECASE,
        ))
        if can_proactive and (n_words >= 6 or looks_like_share):
            ask = True

    # Образность/предложения:
    imagery_cap = 1 if target_len in ("medium", "long") and n >= 10 else 0
    clause_cap = 1 if target_len in ("one", "short") else 2

    if is_question:
        clause_cap = max(clause_cap, 2)
        imagery_cap = 0  # ответ-объяснение, без «красоты»

    # --- форма
    formality = "plain" if target_len in ("one", "short") else "warm"
    emoji_mirror = any(ch in (user_text or "") for ch in "🙂😉❤️👍🔥")

    return CadencePlan(
        target_len=target_len,
        ask=ask,
        formality=formality,
        imagery_cap=imagery_cap,
        clause_cap=clause_cap,
        emoji_mirror=emoji_mirror,
        behavior=behavior,
    )
