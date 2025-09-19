# dialogue/flirt.py
import re
from typing import Optional
from dialogue.guardrails import AGE_MENTION_RE, EXPLICIT_FLIRT_RE

# =========================
# УРОВНИ БЛИЗОСТИ (без NSFW)
# =========================
LEVEL_ORDER = ["off", "soft", "romantic", "suggestive", "roleplay"]
LEVEL_INDEX = {lvl: i for i, lvl in enumerate(LEVEL_ORDER)}

def _clamp(level: str) -> str:
    return level if level in LEVEL_INDEX else "off"

def detect_flirt_intent(text: str):
    t = (text or "").strip()
    if not t:
        return None

    # Упоминание возраста само по себе — не флирт
    if AGE_MENTION_RE.search(t):
        return None

    if EXPLICIT_FLIRT_RE.search(t):
        return {"kind": "toggle_or_level"}  # оставь формат под свой код

    return None

def _step_up(level: str, cap: str) -> str:
    i = LEVEL_INDEX.get(_clamp(level), 0)
    j = min(i + 1, LEVEL_INDEX.get(_clamp(cap), LEVEL_INDEX["suggestive"]))
    return LEVEL_ORDER[j]

def _step_down(level: str, floor: str = "off") -> str:
    i = LEVEL_INDEX.get(_clamp(level), 0)
    j = max(i - 1, LEVEL_INDEX.get(_clamp(floor), 0))
    return LEVEL_ORDER[j]


# =========================
# ТРИГГЕРЫ УПРАВЛЕНИЯ
# =========================
OPEN_RE      = re.compile(r"\b(флирт|пофлиртуем|можно\s+флиртовать|давай\s+флиртовать)\b", re.IGNORECASE)
SOFTER_RE    = re.compile(r"\b(мягче|помягче|чуть\s+ласковее|по[-\s]*доброму)\b", re.IGNORECASE)
WARMER_RE    = re.compile(r"\b(посмелее|чуть\s+смелее|погорячее|поигривее)\b", re.IGNORECASE)
STOP_RE      = re.compile(r"\b(стоп|прекрати|хватит|без\s+флирта)\b", re.IGNORECASE)
CONSENT_RE   = re.compile(r"\b(соглас[иеа]\s+на\s+флирт|флирт\s+можно)\b", re.IGNORECASE)

# Ролевой режим / «вирт» (сценка/roleplay)
ROLEPLAY_RE  = re.compile(
    r"\b(вирт\w*|role[-\s]?play|роле(ва\w*|плей)|сыграем\s*сценку|давай\s*сценку|ролевую\s*игру)\b",
    re.IGNORECASE | re.UNICODE,
)

# Возрастные сигналы
AGE_OK_RE    = re.compile(
    r"\b("
    r"мне\s*(?:18|19|2[0-9]|[3-9][0-9])\s*(?:год(?:а|ов)?|лет)?"
    r"|мне\s*больше\s*18"
    r"|я\s*совершеннолетн\w+"
    r"|18\s*\+"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)
AGE_MINOR_RE = re.compile(
    r"\b("
    r"мне\s*(?:[1-9]|1[0-7])\s*(?:год|года|лет)"
    r"|я\s*несовершеннолетн\w+"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

# Суггестивные/взрослые маркеры (без анатомической «графики»)
SUGGESTIVE_RE = re.compile(
    r"\b("
    r"посмелее|погорячее|пошлее|грязненько|пошал\w*"
    r"|раздень\s*(?:ся|меня)|снимай\s*(?:одежду|лифчик|трус\w+)"
    r"|поцелу\w*\s*ниже|прикоснись\s*ко\s*мне"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

# Явно-графичные запросы / платформы — будем мягко «гасить» в suggestive
EXPLICIT_ANY_RE = re.compile(
    r"\b("
    r"порно\w*|xxx|nsfw|only\s*fans|онли\s*фанс|оф\s*лифанс"
    r"|pornhub|xvideos|xhamster|redtube|youporn|erome|rule34|hentai"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

ADULT_EMOJI_RE = re.compile(r"[🍑🍆💦😈🔞👅👙👄]", re.UNICODE)


def detect_flirt_intent(text: str) -> Optional[str]:
    """
    Возвращает один из тегов:
      stop | age_minor | age_ok | consent | open | softer | warmer | roleplay | suggestive | explicit | None
    """
    if not text:
        return None

    # Управляющие сигналы — приоритетно
    if STOP_RE.search(text):       return "stop"
    if AGE_MINOR_RE.search(text):  return "age_minor"
    if AGE_OK_RE.search(text):     return "age_ok"
    if CONSENT_RE.search(text):    return "consent"
    if OPEN_RE.search(text):       return "open"
    if SOFTER_RE.search(text):     return "softer"
    if WARMER_RE.search(text):     return "warmer"

    # Запрос на ролевую сценку (вирт без графики)
    if ROLEPLAY_RE.search(text):   return "roleplay"

    # Маркеры «взрослого» тона: либо мягко суггестивный, либо явный
    if SUGGESTIVE_RE.search(text) or ADULT_EMOJI_RE.search(text):
        return "suggestive"
    if EXPLICIT_ANY_RE.search(text):
        return "explicit"

    return None


# ========================================
# Основная функция управления состоянием
# ========================================
async def apply_flirt_state(memory_repo, tg_user_id: int, intent: str) -> str:
    """
    Возвращает короткий ДETERMINISTIC ответ БЕЗ LLM.
    Логика (PG-13):
      - stop / age_minor: выключаем флирт.
      - age_ok: отмечаем 18+.
      - consent / open: включаем мягкий флирт (soft).
      - softer: понижаем до soft.
      - warmer: повышаем на шаг, но максимум suggestive.
      - roleplay: включаем roleplay ТОЛЬКО при adult_confirmed и consent; иначе — деликатный редирект.
      - suggestive: поднимаем максимум до suggestive (намёки).
      - explicit: не повышаем выше suggestive; отвечаем деликатно и без графики.
    """
    if not intent:
        return ""

    current_level = await memory_repo.get_flirt_level(tg_user_id) or "off"
    current_level = _clamp(current_level)

    # Стоп / несовершеннолетний — полный выход в OFF
    if intent == "stop":
        await memory_repo.set_flirt_consent(tg_user_id, False)
        await memory_repo.set_flirt_level(tg_user_id, "off")
        return "Поняла. Переключаюсь на нейтральный тон."

    if intent == "age_minor":
        await memory_repo.set_flirt_consent(tg_user_id, False)
        await memory_repo.set_flirt_level(tg_user_id, "off")
        return "Извини, но я не могу продолжать эту тему. Давай о чём-то другом."

    if intent == "age_ok":
        await memory_repo.set_adult_confirmed(tg_user_id, True)
        # Согласие на флирт остаётся как было — пользователь может дать его отдельно
        return "Хорошо, поняла, что ты взрослый. Если хочешь, можем продолжить мягко."

    # Согласие/открытие флирта
    if intent in ("open", "consent"):
        await memory_repo.set_flirt_consent(tg_user_id, True)
        await memory_repo.set_flirt_level(tg_user_id, "soft")
        return "Окей, буду нежнее и теплее."

    # Понижение/повышение
    if intent == "softer":
        await memory_repo.set_flirt_level(tg_user_id, "soft")
        return "Сделаю мягче."

    if intent == "warmer":
        next_level = _step_up(current_level, cap="suggestive")
        await memory_repo.set_flirt_level(tg_user_id, next_level)
        return "Чуть смелее — но деликатно."

    # Мягко «взрослый» тон → suggestive (намёки)
    if intent == "suggestive":
        await memory_repo.set_flirt_level(tg_user_id, "suggestive")
        return "Понимаю намёк. Давай останемся деликатными."

    # Ролевой режим (вирт/сценка) — только при adult_confirmed и consent
    if intent == "roleplay":
        adult_ok = await memory_repo.get_adult_confirmed(tg_user_id)
        consent = await memory_repo.get_flirt_consent(tg_user_id)
        if adult_ok and consent:
            await memory_repo.set_flirt_level(tg_user_id, "roleplay")
            return "Хорошо, сыграем сценку. Я буду бережной и без лишней детализации."
        else:
            # Не даём войти в roleplay, но не рубим разговор
            target = "romantic" if current_level == "off" else current_level
            await memory_repo.set_flirt_level(tg_user_id, target)
            if not adult_ok:
                return "Сценку сможем позже — сначала подтверждай возраст. Пока давай мягче."
            if not consent:
                return "Сценку только по взаимному согласию. Могу быть романтичнее."

    # Явно-графичный запрос: не повышаем выше suggestive, отвечаем деликатно
    if intent == "explicit":
        await memory_repo.set_flirt_consent(tg_user_id, True)
        await memory_repo.set_flirt_level(tg_user_id, "suggestive")
        return "Давай оставим без подробностей и обойдёмся намёками."

    # Если сигнал не распознан — без изменения уровня и без ответа
    return ""
