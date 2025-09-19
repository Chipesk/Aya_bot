# dialogue/humanizer.py
import re
import random
from dataclasses import dataclass

EMOJI_RE = re.compile(r"[🙂😉❤️👍🔥😂😅😊🤣😭✨🤔👏👌💪🌟🤷‍♂️🤷‍♀️🥲🙃😌😍🤗]", re.UNICODE)
WORD_RE = re.compile(r"\w+", re.UNICODE)

# Порог «короткого» сообщения пользователя (информативный, сейчас не используется напрямую)
_SHORT_LEN = 40


@dataclass
class SpeechProfile:
    avg_words: float = 9.0     # средняя длина сообщений
    q_ratio: float = 0.2       # доля вопросов
    emoji_ratio: float = 0.05  # доля эмодзи на слово
    short_bias: float = 0.6    # 0..1 — склонность к коротким ответам


# --- utils ---
def _count_words(s: str) -> int:
    return len(WORD_RE.findall(s or ""))


def _safe_float(x, default: float | None = None) -> float | None:
    try:
        return float(x) if x is not None else default
    except Exception:
        return default


def _ema(prev: float | None, x: float, alpha: float) -> float:
    if prev is None:
        return x
    return (1 - alpha) * prev + alpha * x


def _short_target_from_words(words: int) -> float:
    """
    Маппинг числа слов → целевое значение short_bias в диапазоне [0..1].
    Чем короче реплика, тем выше target.
    """
    if words <= 2:
        return 1.0
    if words <= 6:
        return 0.9
    if words <= 12:
        return 0.7
    if words <= 20:
        return 0.5
    if words <= 35:
        return 0.3
    return 0.15


# --- async profile API (через memory_repo.kv) ---
async def update_user_profile(memory_repo, tg_user_id: int, text: str) -> SpeechProfile:
    w = _count_words(text)
    is_q = (text or "").strip().endswith("?")
    emojis = len(EMOJI_RE.findall(text or ""))

    # прежние значения
    aw_prev = _safe_float(await memory_repo.get_kv(tg_user_id, "profile", "avg_words"))
    qr_prev = _safe_float(await memory_repo.get_kv(tg_user_id, "profile", "q_ratio"))
    er_prev = _safe_float(await memory_repo.get_kv(tg_user_id, "profile", "emoji_ratio"))
    sb_prev = _safe_float(await memory_repo.get_kv(tg_user_id, "profile", "short_bias"))

    # обновляем EMA
    new_aw = _ema(aw_prev, float(w), alpha=0.25)
    new_qr = _ema(qr_prev, 1.0 if is_q else 0.0, alpha=0.20)
    density = emojis / max(1, w)
    new_er = _ema(er_prev, density, alpha=0.20)

    # short_bias — через EMA к целевому значению, зависящему от длины сообщения
    short_target = _short_target_from_words(w)
    new_sb = _ema(sb_prev, short_target, alpha=0.25)
    new_sb = max(0.0, min(1.0, new_sb))  # clamp

    # сохраняем
    await memory_repo.set_kv(tg_user_id, "profile", "avg_words", f"{new_aw:.4f}")
    await memory_repo.set_kv(tg_user_id, "profile", "q_ratio", f"{new_qr:.4f}")
    await memory_repo.set_kv(tg_user_id, "profile", "emoji_ratio", f"{new_er:.4f}")
    await memory_repo.set_kv(tg_user_id, "profile", "short_bias", f"{new_sb:.4f}")
    await memory_repo.set_kv(tg_user_id, "profile", "last_len", str(len(text or "")))

    return SpeechProfile(avg_words=new_aw, q_ratio=new_qr, emoji_ratio=new_er, short_bias=new_sb)


async def get_user_profile(memory_repo, tg_user_id: int) -> SpeechProfile:
    aw = _safe_float(await memory_repo.get_kv(tg_user_id, "profile", "avg_words"), 9.0)
    qr = _safe_float(await memory_repo.get_kv(tg_user_id, "profile", "q_ratio"), 0.2)
    er = _safe_float(await memory_repo.get_kv(tg_user_id, "profile", "emoji_ratio"), 0.05)
    sb = _safe_float(await memory_repo.get_kv(tg_user_id, "profile", "short_bias"), 0.6)
    return SpeechProfile(
        avg_words=aw if aw is not None else 9.0,
        q_ratio=qr if qr is not None else 0.2,
        emoji_ratio=er if er is not None else 0.05,
        short_bias=sb if sb is not None else 0.6,
    )


# --- «снэп»-ответы без LLM ---
HUMAN_SNIPS = {
    "ack": ["ага", "угу", "ок", "ясно", "поняла", "вижу", "слышно", "норм"],
    "pos": ["круто", "класс", "отлично", "звук топ", "мило", "нравится"],
}


def maybe_snap_reply(user_text: str, *, profile: SpeechProfile, last_assistant: str = "") -> str | None:
    txt = (user_text or "").strip()
    if txt.endswith("?"):
        return None  # на вопрос — не «угу»
    if len(last_assistant.split()) <= 3:
        return None  # два «снэпа» подряд нельзя

    w = _count_words(txt)

    # Вероятности адаптируем под short_bias пользователя
    ack_p = 0.15 + 0.25 * float(profile.short_bias)  # 0.15..0.40
    pos_p = 0.20 + 0.15 * float(profile.short_bias)  # 0.20..0.35

    if w <= 2 and random.random() < ack_p:
        return random.choice(HUMAN_SNIPS["ack"])

    if w <= 5 and re.search(r"\b(круто|класс|супер|нравит|ок)\b", txt, re.IGNORECASE):
        if random.random() < pos_p:
            return random.choice(HUMAN_SNIPS["pos"])

    return None
