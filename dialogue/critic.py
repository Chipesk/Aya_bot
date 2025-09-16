# dialogue/critic.py
import re

METAPHOR = re.compile(r"\b(будто|словно|как будто|будто бы)\b", re.IGNORECASE)
SCENE_OPEN = re.compile(r"^\s*(представь|только представь|вообрази|картинка такая)\b", re.IGNORECASE)
CHEESY = [
    "в этом есть своя глубина",
    "в этом своё очарование",
    "это почти медитация",
    "кажется, будто весь мир сужается",
]

def sentence_count(text: str) -> int:
    return len(re.findall(r"[.!?…]+", text or "")) or (1 if text.strip() else 0)

def count_metaphors(text: str) -> int:
    return len(METAPHOR.findall(text or ""))

def count_cliches(text: str) -> int:
    t = text.lower()
    return sum(1 for c in CHEESY if c in t)

def starts_with_scene_setup(text: str) -> bool:
    return bool(SCENE_OPEN.search(text or ""))

def ai_score(text: str) -> int:
    score = 0
    score += 2 * count_metaphors(text)
    score += 1 * count_cliches(text)
    sc = sentence_count(text)
    score += max(0, sc - 2)
    if starts_with_scene_setup(text):
        score += 2
    if (text or "").rstrip().endswith("?"):
        score += 1
    return score
