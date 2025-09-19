# dialogue/guardrails.py
import re
from dataclasses import dataclass
from typing import Optional


# --- Лексиконы/паттерны (вынесены из разбросанных мест) ---

# Возраст — любые формулировки: «мне 33», «за тридцать», «я взрослый дядя», «подросток»
AGE_MENTION_RE = re.compile(
    r"(?i)\b("
    r"мне\s*\d{1,2}\s*лет"
    r"|мне\s*\d{1,2}\b"
    r"|за\s*(?:двадцать|тридцать|сорок|пятьдесят)"
    r"|я\s+взросл\w+"
    r"|взрослый\s+(?:мужик|дядя|человек)"
    r"|подросток"
    r")\b"
)

# Явные маркеры флирта (сердечки, поцелуи, прямо «флирт» и т.п.)
EXPLICIT_FLIRT_RE = re.compile(
    r"(?i)\b(флирт|заигр\w+|кокетнич\w+|поцелу\w+|романтич\w+|нежн\w+)\b|❤️|💋|💘|🥰|😘"
)

# «Сценические ремарки»: (смеётся), (вздыхает), *улыбается* — их нормализуем
PARENS_DIR_RE = re.compile(r"\(([^)]{0,80})\)")
STARS_DIR_RE  = re.compile(r"\*(?:[^*]{0,80})\*")

STAGE_MAP = [
    (re.compile(r"(?i)\bсме(е|ё)тс[яь]|хихик\w+|смеюсь\b"), "😄"),
    (re.compile(r"(?i)\bулыба\w+"), "🙂"),
    (re.compile(r"(?i)\bвздыхает|вздох\b"), "😮‍💨"),
]

# Навязчивые намёки «мягко/нежно/романтично продолжим» без согласия — гасим
SUGGESTIVE_HINT_RE = re.compile(
    r"(?i)\bпродолж\w{0,6}[^.!?]{0,30}\b(мягк\w*|нежн\w*|романтич\w*)\b"
)


@dataclass
class Perception:
    has_age_mention: bool = False
    has_explicit_flirt: bool = False
    has_stage_dirs: bool = False


@dataclass
class PolicyConfig:
    allow_stage_dirs_modes: set[str] = None

    def __post_init__(self):
        if self.allow_stage_dirs_modes is None:
            # Разрешаем скобочные/звёздочные ремарки только в roleplay
            self.allow_stage_dirs_modes = {"roleplay"}


class Guardrails:
    """
    Единая «перцепция+политика». Мы:
    1) распознаём ключевые феномены (возраст, флирт, ремарки);
    2) принимаем политические решения;
    3) пост-обрабатываем текст модели, чтобы держать стиль и границы.
    """
    def __init__(self, config: Optional[PolicyConfig] = None):
        self.cfg = config or PolicyConfig()

    # --- 1) Перцепция входного текста пользователя ---
    def perceive(self, user_text: str) -> Perception:
        t = (user_text or "").strip()
        if not t:
            return Perception()
        return Perception(
            has_age_mention=bool(AGE_MENTION_RE.search(t)),
            has_explicit_flirt=bool(EXPLICIT_FLIRT_RE.search(t)),
            has_stage_dirs=bool(PARENS_DIR_RE.search(t) or STARS_DIR_RE.search(t)),
        )

    # --- 2) Политика флирта: возрастные упоминания не повышают уровень сами по себе ---
    def flirt_allowed(self, *, user_consent: bool, perception: Perception) -> bool:
        if not user_consent:
            return False
        # Только явный флирт от пользователя — ок; одно лишь «мне 33 / я взрослый» — не сигнал
        return perception.has_explicit_flirt

    # --- 3) Пост-обработка текста ассистента ---
    def postprocess(
        self,
        text: str,
        *,
        mode,                  # объект/строка: 'chat' | 'roleplay' ...
        user_consent: bool,    # согласие на флирт
    ) -> str:
        out = text or ""

        mode_val = getattr(mode, "value", str(mode))

        # 3.1 Без ремарок вне roleplay: ( ... ) и * ... * → эмодзи/удаление
        if mode_val not in self.cfg.allow_stage_dirs_modes:
            out = self._replace_stage_parens(out)
            out = self._strip_star_dirs(out)

        # 3.2 Без «мягко/нежно/романтично продолжим» без согласия
        if not user_consent:
            out = SUGGESTIVE_HINT_RE.sub("можем продолжить, если интересно", out)

        # 3.3 Сжатие пробелов/знаков
        out = self._tidy(out)

        return out

    # --- helpers ---
    def _replace_stage_parens(self, text: str) -> str:
        def _repl(m: re.Match) -> str:
            chunk = (m.group(1) or "").strip()
            for rx, emoji in STAGE_MAP:
                if rx.search(chunk):
                    return f" {emoji} "
            return " "
        return PARENS_DIR_RE.sub(_repl, text)

    def _strip_star_dirs(self, text: str) -> str:
        return STARS_DIR_RE.sub(" ", text)

    def _tidy(self, text: str) -> str:
        out = re.sub(r"\s{2,}", " ", text)
        out = re.sub(r"\s+([.,!?])", r"\1", out)
        return out.strip()
