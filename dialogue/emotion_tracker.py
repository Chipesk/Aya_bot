# dialogue/emotion_tracker.py
import re
from dataclasses import dataclass

EMO_MAP = [
    ("joy",       re.compile(r"\b(рад(ую|остно)|классно|супер|ура|обожаю|обожаю)\b|😊|😄|😍|🥳", re.I)),
    ("sad",       re.compile(r"\b(грустн|печал|тоск|хандр|плохо)\b|😞|😢|😭", re.I)),
    ("anger",     re.compile(r"\b(злюсь|бесит|ненавижу|раздражает|когда уже)\b|😤|😡", re.I)),
    ("anxiety",   re.compile(r"\b(тревожн|переживаю|боюсь|стресс)\b|😬|😰", re.I)),
    ("tired",     re.compile(r"\b(устал|выжат|сонн|нет сил|выгорел)\b|🥱", re.I)),
    ("interest",  re.compile(r"\b(интересн|расскажи|почему|как это|пример)\b|🤔", re.I)),
    ("bored",     re.compile(r"\b(скучно|неинтересно|ну и)\b|😐|🙄", re.I)),
]

INTENSITY_HINTS = re.compile(r"[!]{2,}|[.]{3,}|[(]{2,}|[)]{2,}|❤️|💔|🔥|💥")

@dataclass
class Emotion:
    label: str      # joy|sad|anger|anxiety|tired|interest|bored|neutral
    intensity: str  # low|mid|high

def detect_emotion(text: str) -> Emotion:
    t = text or ""
    for label, rx in EMO_MAP:
        if rx.search(t):
            return Emotion(label=label, intensity=_infer_intensity(t))
    return Emotion(label="neutral", intensity="low")

def _infer_intensity(t: str) -> str:
    # Эвристики: много восклицаний/многоточий/эмодзи → выше интенсивность
    ex = len(re.findall(r"[!]", t))
    dots = len(re.findall(r"\.\.+", t))
    emo = len(INTENSITY_HINTS.findall(t))
    score = (ex >= 2) + (dots >= 1) + (emo >= 1)
    if score >= 2:
        return "high"
    if score == 1:
        return "mid"
    return "low"
