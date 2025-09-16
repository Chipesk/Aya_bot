# dialogue/humanizer.py
import re
import random
from dataclasses import dataclass

EMOJI_RE = re.compile(r"[🙂😉❤️👍🔥😂😅😊🤣😭✨🤔👏👌💪🌟🤷‍♂️🤷‍♀️🥲🙃😌😍🤗]", re.UNICODE)
WORD_RE  = re.compile(r"\w+", re.UNICODE)

@dataclass
class SpeechProfile:
    avg_words: float = 9.0     # средняя длина сообщений
    q_ratio: float = 0.2       # доля вопросов
    emoji_ratio: float = 0.05  # доля эмодзи на слово
    short_bias: float = 0.6    # склонность к коротким ответам

# --- utils ---
def _count_words(s: str) -> int:
    return len(WORD_RE.findall(s or ""))

def _ema(old: float | None, value: float, alpha: float = 0.2, default: float = 0.0) -> float:
    base = default if old is None else float(old)
    return (1 - alpha) * base + alpha * value

# --- async profile API (через memory_repo.kv) ---
async def update_user_profile(memory_repo, tg_user_id: int, text: str) -> SpeechProfile:
    w = _count_words(text)
    is_q = (text or "").strip().endswith("?")
    emojis = len(EMOJI_RE.findall(text or ""))

    # читаем прежние значения
    aw = await memory_repo.get_kv(tg_user_id, "profile", "avg_words")
    qr = await memory_repo.get_kv(tg_user_id, "profile", "q_ratio")
    er = await memory_repo.get_kv(tg_user_id, "profile", "emoji_ratio")
    sb = await memory_repo.get_kv(tg_user_id, "profile", "short_bias")

    # обновляем EMA
    new_aw = _ema(float(aw) if aw else None, float(w), alpha=0.25, default=9.0)
    new_qr = _ema(float(qr) if qr else None, 1.0 if is_q else 0.0, alpha=0.2, default=0.2)
    new_er = _ema(float(er) if er else None, (emojis / max(1, w)), alpha=0.2, default=0.05)

    # короткие ответы пользователя → растим short_bias
    short_boost = 0.05 if w <= 6 else (-0.02 if w >= 20 else 0.0)
    new_sb = min(0.9, max(0.1, float(sb) if sb else 0.6 + short_boost))

    # сохраняем
    await memory_repo.set_kv(tg_user_id, "profile", "avg_words", f"{new_aw:.4f}")
    await memory_repo.set_kv(tg_user_id, "profile", "q_ratio", f"{new_qr:.4f}")
    await memory_repo.set_kv(tg_user_id, "profile", "emoji_ratio", f"{new_er:.4f}")
    await memory_repo.set_kv(tg_user_id, "profile", "short_bias", f"{new_sb:.4f}")

    return SpeechProfile(avg_words=new_aw, q_ratio=new_qr, emoji_ratio=new_er, short_bias=new_sb)

async def get_user_profile(memory_repo, tg_user_id: int) -> SpeechProfile:
    aw = await memory_repo.get_kv(tg_user_id, "profile", "avg_words")
    qr = await memory_repo.get_kv(tg_user_id, "profile", "q_ratio")
    er = await memory_repo.get_kv(tg_user_id, "profile", "emoji_ratio")
    sb = await memory_repo.get_kv(tg_user_id, "profile", "short_bias")
    return SpeechProfile(
        avg_words=float(aw) if aw else 9.0,
        q_ratio=float(qr) if qr else 0.2,
        emoji_ratio=float(er) if er else 0.05,
        short_bias=float(sb) if sb else 0.6,
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
    if w <= 2 and random.random() < 0.2:    # 0.35 -> 0.20
        return random.choice(HUMAN_SNIPS["ack"])
    if w <= 5 and re.search(r"\b(круто|класс|супер|нравит|ок)\b", txt, re.IGNORECASE):
        if random.random() < 0.30:          # 0.45 -> 0.30
            return random.choice(HUMAN_SNIPS["pos"])
    return None
