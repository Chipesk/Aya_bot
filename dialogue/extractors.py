# dialogue/extractors.py
import re

# Артисты для распознавания
ARTISTS = [
    r"radiohead", r"london\s+grammar", r"depeche\s+mode", r"massive\s+attack",
]
ART_RE = re.compile("|".join(ARTISTS), re.IGNORECASE)

# Дополнительные лёгкие триггеры тона
FLIRT_RE      = re.compile(r"\b(флирт|подмигн\w*|заигрыва(ть|ем))\b", re.IGNORECASE)
ROMANTIC_RE   = re.compile(r"\b(романтичн|нежн|ласк|обним|поцелу)\w*\b", re.IGNORECASE)
SUGGESTIVE_RE = re.compile(r"\b(посмелее|погорячее|намёк|страсть)\w*\b", re.IGNORECASE)
ROLEPLAY_RE   = re.compile(r"\b(вирт|role[-\s]?play|ролев(ой|ая)\s*игр\w*)\b", re.IGNORECASE)

# Прочие факты
ASTRO_RE = re.compile(r"\b(затмен|персеида|метеор|астроном)\w*", re.IGNORECASE)
CITY_RE  = re.compile(r"\bкраснодар\w*", re.IGNORECASE)
QUIET_RE = re.compile(r"\b(тих(о|ий)|спокойн(о|ый))\b", re.IGNORECASE)

def extract_facts(text: str) -> dict:
    facts = {}
    # Музыка
    artists = set(m.group(0).lower() for m in ART_RE.finditer(text))
    if artists:
        facts["artists"] = {a.title() for a in artists}

    # Интересы/факты
    if ASTRO_RE.search(text):
        facts["astronomy"] = True
    if CITY_RE.search(text):
        facts["location_hint"] = "Краснодар (пригород/предгорья)"
    if QUIET_RE.search(text):
        facts["likes_quiet"] = True

    # Подсказки по тону общения
    if FLIRT_RE.search(text):
        facts["tone_hint"] = "soft"
    elif ROMANTIC_RE.search(text):
        facts["tone_hint"] = "romantic"
    elif SUGGESTIVE_RE.search(text):
        facts["tone_hint"] = "suggestive"
    elif ROLEPLAY_RE.search(text):
        facts["tone_hint"] = "roleplay"

    return facts


INTEREST_TAGS = {
    "bike": re.compile(r"\b(вел[оа]\w*|bike|bicycle|шоссе|гравийник|маунтин)\b", re.I),
    "video": re.compile(r"\b(видос|видео|ютуб|youtube|ролик)\b", re.I),
    "film": re.compile(r"\b(фильм|кино|сериал|netflix|кинцо)\b", re.I),
    "music": re.compile(r"\b(музык|плейлист|концерт|бит|треки)\b", re.I),
    "tea": re.compile(r"\b(чай|улун|матча|пуэр)\b", re.I),
    "sports": re.compile(r"\b(бег|спортзал|качалка|футбол|теннис|баскет)\b", re.I),
}

def extract_interests(text: str) -> set[str]:
    tags = set()
    for tag, rx in INTEREST_TAGS.items():
        if rx.search(text or ""):
            tags.add(tag)
    return tags