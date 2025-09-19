# orchestrator/aya_brain.py
from orchestrator.integration_adapter import augment_brief

import logging
import re
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dialogue.fact_extractor import extract_facts_generic
from dialogue.guardrails import Guardrails
from dialogue.extractors import extract_facts, extract_interests
from dialogue.cadence import infer_cadence
from dialogue.humanizer import update_user_profile, get_user_profile, maybe_snap_reply
from dialogue.critic import ai_score
from dialogue.greeting import is_user_greeting, greeting_policy, is_bot_greeting
from dialogue.addressing import pick_address_form, should_use_address
from dialogue.emotion_tracker import detect_emotion
from dialogue.planner import plan_response


log = logging.getLogger("aya")

# -----------------------------
# Приветствия: срезаем лишние "Привет!"
# -----------------------------
GREETING_HEAD_RE = re.compile(
    r"^\s*(?:привет(?:ствую)?|здравствуй(?:те)?|доброе\s+утро|добрый\s+(?:день|вечер))[\s,)!.\-–—]*",
    re.IGNORECASE
)

def strip_forbidden_greeting(text: str, allow: bool, kind: str) -> str:
    if allow and kind != "ack":
        return text
    prev = None
    s = text.lstrip()
    for _ in range(3):
        if prev == s:
            break
        prev = s
        s = GREETING_HEAD_RE.sub("", s, count=1).lstrip()
    return s


# -----------------------------
# Уровни "тона/режима"
# -----------------------------
class Mode(str, Enum):
    OFF = "off"            # обычный разговор
    SOFT = "soft"          # мягкий флирт
    ROMANTIC = "romantic"  # романтика
    SUGGESTIVE = "suggestive"  # намёки (без графики)
    ROLEPLAY = "roleplay"  # "Вирт"/ролеплей-сценка (ремарки *, допускается 3-е лицо по твоим правилам)


@dataclass
class ToneDecision:
    mode: Mode
    reason: str


# -----------------------------
# Эвристики определения режима
# -----------------------------
_ADULT_HINT_RE = re.compile(
    r"\b(вирт|роль(е|e)ва(я|я)|сыграем сценку|сценарий|role[- ]?play)\b",
    re.IGNORECASE
)
_FLIRT_SOFT_RE = re.compile(r"\b(флирт|заигрыва(ть|ем)|подмиг(иваю|нёшь)|красива(я|ый)|симпатич|мила(я|й)|очаровательн|прекрасн)\w*\b", re.IGNORECASE)
_ROMANTIC_RE = re.compile(r"\b(романтичн|нежн|ласк|обним|поцелу)\w*\b", re.IGNORECASE)
_SUGGESTIVE_RE = re.compile(
    r"\b(возбуд|намёк|намека|жарко|интим|страсть|страстн)\w*\b", re.IGNORECASE
)

_CHEESY_PHRASES = [
    "в этом есть своя глубина",
    "в этом своё очарование",
    "будто прокручиваешь их вместе с педалями",
    "это почти медитация",
    "кажется, будто весь мир сужается",
]
_METAPHOR_MARKERS = re.compile(r"\b(будто|словно|как будто|будто бы)\b", re.IGNORECASE)


def _classify_user_tone(user_text: str) -> Mode:
    if _ADULT_HINT_RE.search(user_text):
        return Mode.ROLEPLAY
    if _SUGGESTIVE_RE.search(user_text):
        return Mode.SUGGESTIVE
    if _ROMANTIC_RE.search(user_text):
        return Mode.ROMANTIC
    if _FLIRT_SOFT_RE.search(user_text):
        return Mode.SOFT
    return Mode.OFF


# -----------------------------
# Контент-роутер (единый арбитр)
# -----------------------------
def decide_mode(user_text: str, *, adult_ok: bool, consent: bool) -> ToneDecision:
    hint = _classify_user_tone(user_text)
    # Без подтверждения 18+ — потолок ROMANTIC
    if not adult_ok:
        cap = Mode.ROMANTIC
    else:
        # Есть 18+, но нет согласия на флирт → без эскалации
        if not consent:
            cap = Mode.OFF
        else:
            # Согласие есть: максимум SUGGESTIVE (намёки).
            cap = Mode.SUGGESTIVE
    order = [Mode.OFF, Mode.SOFT, Mode.ROMANTIC, Mode.SUGGESTIVE, Mode.ROLEPLAY]
    capped = order[min(order.index(hint), order.index(cap))]
    return ToneDecision(mode=capped, reason=f"hint={hint.value}, cap={cap.value}")


# -----------------------------
# Пост-стилистический санитайзер (усиленный)
# -----------------------------
_STAGE_LINE_RE = re.compile(r"^\s*\*[^*\n]+\*\s*$")         # строка-ремарка
_STAGE_INLINE_RE = re.compile(r"\*[^*\n]+\*")               # inline-ремарка

def _strip_stage_directions(text: str) -> str:
    lines = []
    for ln in text.splitlines():
        if _STAGE_LINE_RE.match(ln.strip()):
            continue
        lines.append(ln)
    text = "\n".join(lines)
    text = _STAGE_INLINE_RE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text

# Простая эвристика перевода 3-го лица → 1-го (мягко, без морфоанализа)
_THIRD_TO_FIRST_PATTERNS = [
    (re.compile(r"(?i)\b(она|ая)\s+(улыбается|смотрит|вздыхает|смущается|думает)\b"), r"Я \2"),
]

def _to_first_person(text: str) -> str:
    for pat, rep in _THIRD_TO_FIRST_PATTERNS:
        text = pat.sub(rep, text)
    return text

def _limit_clauses(text: str, max_sentences: int) -> str:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return " ".join(parts[:max_sentences]).strip()

def _strip_cliches(text: str) -> str:
    t = text
    for p in _CHEESY_PHRASES:
        t = re.sub(re.escape(p), "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

def _cap_metaphors(text: str, max_count: int) -> str:
    if max_count <= 0:
        return _METAPHOR_MARKERS.sub("", text)
    found = list(_METAPHOR_MARKERS.finditer(text))
    if len(found) <= max_count:
        return text
    # срезаем маркеры сверх лимита
    out, last = [], 0
    for idx, m in enumerate(found):
        if idx >= max_count:
            out.append(text[last:m.start()])
            last = m.end()
    out.append(text[last:])
    return "".join(out)

def _tone_plainify(text: str) -> str:
    t = re.sub(r"\s*—\s*", " — ", text)
    t = re.sub(r"(?:,){2,}", ",", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t

def _suppress_unasked_questions(text: str, allow_question: bool) -> str:
    if allow_question:
        return text
    # заменяем все ? на .
    t = re.sub(r"\?", ".", text)
    # убираем простые «инициирующие» хвосты вида «А ты ...»
    t = re.sub(r"(?:^|\s)(А\s+)?(ты|расскажешь|поделишься)[^.]*\.$", ".", t, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", t).strip()

def _reduce_question_frequency(text: str, ask_flag: bool, history) -> str:
    # Если ask_flag=False — не заканчиваем вопросом.
    if not ask_flag and text.rstrip().endswith("?"):
        return text.rstrip(" ?") + "."
    # Если два последних ассист-ответа уже заканчивались вопросом — текущий завершаем точкой
    last_two = [m for m in history[-2:] if m.get("role") == "assistant"]
    q_count = sum(1 for m in last_two if m.get("content", "").rstrip().endswith("?"))
    if q_count >= 2 and text.rstrip().endswith("?"):
        return text.rstrip(" ?") + "."
    return text

def post_style_sanitizer(
    text: str, *, mode: Mode, ask_flag: bool, history, imagery_cap: int = 0, clause_cap: int = 2
) -> str:
    # Вне roleplay запрещаем ремарки и 3-е лицо
    if mode != Mode.ROLEPLAY:
        text = _strip_stage_directions(text)
        text = _to_first_person(text)
    # Ограничим число предложений
    text = _limit_clauses(text, max_sentences=clause_cap)
    # Срежем фиолетовость
    text = _cap_metaphors(text, max_count=imagery_cap)
    text = _strip_cliches(text)
    text = _tone_plainify(text)
    # Запрет непрошенных вопросов
    text = _suppress_unasked_questions(text, allow_question=ask_flag)
    # Финальная защита от «?» подряд
    text = _reduce_question_frequency(text, ask_flag, history)
    return text


# -----------------------------
# Мозг Аи
# -----------------------------
class AyaBrain:
    def _goodbye_policy(self, user_text: str) -> bool:
        """
        Возвращает True, если пользователь явно прощается, и тогда мы можем завершить диалог тёплой фразой.
        """
        txt = (user_text or "").strip().lower()
        BYE = ("пока", "до встречи", "бай", "споки", "спокойной ночи", "досвидания", "до свидания")
        return any(txt == w or txt.startswith(w + " ") for w in BYE)

    def __init__(self, deepseek_client, memory_repo, world_state, chat_history, persona_manager, facts_repo=None):
        self.deepseek = deepseek_client
        self.memory = memory_repo
        self.world = world_state
        self.history = chat_history
        self.facts = facts_repo
        self.persona = persona_manager
        self.guardrails = Guardrails()

    async def health_check(self):
        return await self.deepseek.health_check()

    async def reset_user(self, tg_user_id: int):
        # 1) История диалога
        try:
            await self.history.clear(tg_user_id)
        except Exception:
            pass

        # 2) Диалоговые состояния / тема
        try:
            await self.memory.set_topic(tg_user_id, "")
        except Exception:
            pass
        try:
            # предпочтительно: явный сброс intent/payload/ts
            await self.memory.set_dialog_state(tg_user_id, intent="", payload="", ts=None)
        except Exception:
            try:
                # фолбэк: если есть только clear_dialog_state()
                await self.memory.clear_dialog_state(tg_user_id)
            except Exception:
                pass

        # 3) Приветствия/счётчики
        try:
            # если метод принимает (id, iso) — шлём None; если без iso — ловим и игнорируем
            await self.memory.set_last_bot_greet_at(tg_user_id, None)
        except TypeError:
            try:
                await self.memory.set_last_bot_greet_at(tg_user_id)
            except Exception:
                pass
        except Exception:
            pass
        try:
            await self.memory.reset_daily_greet(tg_user_id)
        except Exception:
            try:
                # возможная альтернатива, если есть сеттер
                await self.memory.set_daily_greet(tg_user_id, 0)
            except Exception:
                pass

        # 4) Формы обращения, чтобы начать «с чистого листа»
        try:
            await self.memory.remove_set_fact(tg_user_id, "address_allow")
        except Exception:
            pass
        try:
            await self.memory.remove_set_fact(tg_user_id, "address_deny")
        except Exception:
            pass

        # 5) Флирт/согласия
        try:
            await self.memory.set_flirt_consent(tg_user_id, False)
        except Exception:
            pass
        try:
            await self.memory.set_flirt_level(tg_user_id, "off")
        except Exception:
            pass

        # 6) Близость/симпатия
        try:
            await self.memory.set_affinity(tg_user_id, 0)
        except Exception:
            pass

        # 7) Имя и ник — начать знакомство заново
        try:
            await self.memory.set_user_display_name(tg_user_id, "")
        except Exception:
            pass
        try:
            await self.memory.set_user_nickname(tg_user_id, "")
        except Exception:
            pass
        try:
            await self.memory.set_user_nickname_allowed(tg_user_id, False)
        except Exception:
            pass

        # Жёстко сбросим last_bot_greet_at, если метод не принимает None — ставим «очень старую» дату
        try:
            await self.memory.set_last_bot_greet_at(tg_user_id, None)
        except TypeError:
            try:
                await self.memory.set_last_bot_greet_at(tg_user_id, "1970-01-01T00:00:00")
            except Exception:
                pass
        except Exception:
            pass

    async def _collect_user_facts(self, tg_user_id: int) -> list[str]:
        name = await self.memory.get_user_display_name(tg_user_id)
        prefs = await self.memory.get_user_prefs(tg_user_id)
        artists = await self.memory.get_set_fact(tg_user_id, "music_artists")
        astro = await self.memory.get_kv(tg_user_id, "facts", "astronomy")
        loc = await self.memory.get_kv(tg_user_id, "facts", "location_hint")
        quiet = await self.memory.get_kv(tg_user_id, "facts", "likes_quiet")

        facts = []
        if name: facts.append(f"name={name}")
        if prefs.get("nickname") and prefs.get("nickname_allowed"):
            facts.append(f"nickname={prefs['nickname']}")
        if artists: facts.append("music_artists=" + ",".join(artists[:5]))
        if astro == "1": facts.append("likes_astronomy=true")
        if loc: facts.append(f"location_hint={loc}")
        if quiet == "1": facts.append("likes_quiet=true")
        return facts

    async def reply(self, tg_user_id: int, user_text: str) -> str:
        # --- окружение/память ---
        turn = await self.memory.inc_turn(tg_user_id)
        world = await self.world.get_context()
        em = detect_emotion(user_text)
        display_name = await self.memory.get_user_display_name(tg_user_id)
        prefs = await self.memory.get_user_prefs(tg_user_id)
        topic = await self.memory.get_topic(tg_user_id)

        adult_ok = await self.memory.get_adult_confirmed(tg_user_id)
        consent = await self.memory.get_flirt_consent(tg_user_id)
        flirt_level = await self.memory.get_flirt_level(tg_user_id)
        perception = self.guardrails.perceive(user_text)
        last_intent, _, ts = await self.memory.get_dialog_state(tg_user_id)
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        weather_allowed = False
        if last_intent == "weather":
            try:
                is_fresh = (now - datetime.fromisoformat(ts)) <= timedelta(seconds=60) if ts else False
            except Exception:
                is_fresh = False
            weather_allowed = is_fresh

        last_seen_iso = await self.memory.get_last_seen(tg_user_id)
        if last_seen_iso:
            try:
                idle_sec = int((now - datetime.fromisoformat(last_seen_iso)).total_seconds())
            except Exception:
                idle_sec = None
        else:
            idle_sec = None

        last_bot_greet_iso = await self.memory.get_last_bot_greet_at(tg_user_id)
        daily_greets = await self.memory.get_daily_greet(tg_user_id)

        user_greeted = is_user_greeting(user_text)
        greet = greeting_policy(
            now=now,
            last_bot_greet_iso=last_bot_greet_iso,
            daily_greet_count=daily_greets,
            user_greeted=user_greeted,
            turn=turn,
            idle_seconds=idle_sec,
        )

        # --- универсальное извлечение фактов из текущей реплики ---
        if self.facts is not None and (user_text or "").strip():
            try:
                gen_facts = await extract_facts_generic(user_text, self.deepseek)
                for f in gen_facts:
                    # нормализуем object в строку для хранения; числа/булеан — тоже ок, приведём к str
                    obj = f["object"]
                    if isinstance(obj, (dict, list)):
                        obj_str = json.dumps(obj, ensure_ascii=False)
                    else:
                        obj_str = str(obj)
                    await self.facts.upsert_fact(
                        tg_user_id,
                        predicate=f["predicate"],
                        obj=obj_str,
                        dtype=f.get("dtype"),
                        unit=f.get("unit"),
                        confidence=float(f.get("confidence", 0.7)),
                        source="chat",
                        source_msg_id=None,
                    )
            except Exception as _e:
                logger = globals().get("logger", None)
                if logger:
                    logger.debug("extract_facts_generic failed: %s", _e)

        # --- профиль речи пользователя (EMA) ---
        profile = await update_user_profile(self.memory, tg_user_id, user_text)

        # --- план ответа ---
        plan = plan_response(turn, user_text, topic, em=em)
        await self.memory.set_topic(tg_user_id, plan.topic)

        history = await self.history.last(tg_user_id, limit=8)
        last_two_assistant_texts = [m.get("content", "") for m in history if m.get("role") == "assistant"][-2:]
        last_assistant_text = last_two_assistant_texts[-1] if last_two_assistant_texts else ""
        cad = infer_cadence(user_text, last_two_assistant_texts, profile=profile)

        # --- dead-end detector ---
        SHORT_ACK_RE = re.compile(r"^\s*(ок(ей)?|ну ок|понял[а]?|ясно|угу|ладно)\.?\s*$", re.IGNORECASE)
        user_ack = bool(SHORT_ACK_RE.match(user_text or ""))

        # если короткий кивок, и мы не планировали спрашивать — мягко оживляем
        if user_ack and not getattr(cad, "ask", False):
            cad.ask = True  # дать шанс вопросу

        # комбинированное решение об вопросе
        ask_flag = bool(getattr(cad, "ask", False) or getattr(plan, "ask", False))

        # если два наших последних ответа уже были с вопросом — текущий не вопрос
        q_tail_forced = sum(1 for t in last_two_assistant_texts if (t or "").rstrip().endswith("?"))
        if q_tail_forced >= 2:
            ask_flag = False

        # сигнал для генератора: мы оживляем разговор
        rescue_hint = "yes" if user_ack else "no"

        DETAIL_RE = re.compile(r"\b(расскажи|поясни|пример|что это|как это|почему)\b", re.IGNORECASE)
        if DETAIL_RE.search(user_text or ""):
            cad.target_len = "medium" if cad.target_len in ("one", "short") else cad.target_len
            cad.clause_cap = max(cad.clause_cap, 2)
            cad.imagery_cap = 0

        # первые 3 шага максимально сухо
        if turn <= 3:
            cad.target_len = "short"
            cad.imagery_cap = 0
            cad.clause_cap = 1

        # --- быстрый «снэп»-ответ без LLM, если уместно ---
        snap = maybe_snap_reply(user_text, profile=profile, last_assistant=last_assistant_text)
        if snap:
            await self.history.add(tg_user_id, "user", user_text)
            await self.history.add(tg_user_id, "assistant", snap)
            return snap

        # --- ЕДИНЫЙ РЕЖИМ ДЛЯ СТИЛЯ ---
        decision = decide_mode(user_text, adult_ok=bool(adult_ok), consent=bool(consent))
        dialog_mode = decision.mode.value  # передаём в шаблон

        # --- system prompt персоны ---
        system_prompt = self.persona.render_system(
            world=world,
            user={
                "display_name": display_name,
                "nickname_allowed": prefs["nickname_allowed"],
                "nickname": prefs["nickname"],
                "formality": prefs["formality"],
            },
            dialog={"topic": plan.topic, "mode": dialog_mode},
        )

        # --- история для модели (свежая) ---
        history = await self.history.last(tg_user_id, limit=8)

        user_facts = await self._collect_user_facts(tg_user_id)
        user_facts_block = "USER_FACTS:\n" + ("\n".join(user_facts) if user_facts else "none")

        # --- обращение ---
        affinity = await self.memory.get_affinity(tg_user_id)

        nickname_allowed = bool(prefs.get("nickname_allowed", False))
        nickname = (prefs.get("nickname") or "").strip() or None
        display_name_safe = (display_name or "").strip() or None

        if str(flirt_level) in ("romantic", "suggestive") or plan.tone in ("romantic", "suggestive"):
            affection_mode = "romantic"
        elif consent or plan.tone == "soft":
            affection_mode = "warm"
        else:
            affection_mode = "none"

        address_form = pick_address_form(
            display_name=display_name_safe,
            nickname=nickname,
            nickname_allowed=nickname_allowed,
            affection_mode=affection_mode,
            affinity=affinity,
            tone=(plan.tone or "off"),
        )

        # ВАЖНО: не пересчитываем ask_flag повторно после адресации

        # --- BRIEF для генератора ---
        brief = (
            "REPLY_BRIEF:\n"
            f"- style.length={cad.target_len}\n"
            f"- style.tone={plan.tone}\n"
            f"- ask_question={'yes' if ask_flag else 'no'}\n"
            f"- topic_focus={plan.topic}\n"
            f"- avoid_weather_numbers=true\n"
            "- address:\n"
            f"    nickname_allowed={'true' if nickname_allowed else 'false'}\n"
            f"    nickname='{nickname or ''}'\n"
            f"    full_name='{display_name_safe or ''}'\n"
            f"- address.use={'yes' if (should_use_address(cad.target_len, plan.tone, affinity) and address_form) else 'no'}\n"
            f"- address.form='{address_form or ''}'\n"
            "- variation:\n"
            f"    allow_one_word={'true' if cad.target_len == 'one' else 'false'}\n"
            f"    allow_microstory={'true' if cad.target_len in ('medium', 'long') else 'false'}\n"
            f"- imagery_cap={cad.imagery_cap}\n"
            f"- clause_cap={cad.clause_cap}\n"
            f"- formality={cad.formality}\n"
            f"- dialog.mood={em.label}\n"
            f"- dialog.mood_intensity={em.intensity}\n"
            f"- act={plan.act}\n"
            f"- subtopic={plan.subtopic}\n"
            f"- tone={plan.tone}\n"
            f"- emoji_mirror={'yes' if cad.emoji_mirror else 'no'}\n"
            f"- weather_allowed={'yes' if weather_allowed else 'no'}\n"
            f"- greeting.allow={'yes' if greet['allow'] else 'no'}\n"
            f"- greeting.kind={greet['kind']}\n"
            "- intimacy:\n"
            f"    adult_confirmed={'yes' if adult_ok else 'no'}\n"
            f"    flirt.consent={'yes' if consent else 'no'}\n"
            f"    flirt.level={flirt_level}\n"
            f"    dialog.mode={dialog_mode}\n"
            f"- rescue={rescue_hint}\n"
            "- structure:\n"
            "    reaction=yes\n"
            "    self_share=small\n"
            f"    followup_question={'yes' if ask_flag else 'no'}\n"
            "STYLE_RULES:\n"
            "- Если dialog.mode != 'roleplay': без *звёздочных* ремарок и без рассказа от третьего лица; пиши от 1-го лица.\n"
            "- Если dialog.mode == 'roleplay': ремарки *...* разрешены, 3-е лицо возможно, но без графических подробностей (fade-to-black).\n"
            "- Не начинай описание сцены/атмосферы без прямого запроса пользователя.\n"
            "- Длина фраз преимущественно 6–14 слов; ритм вариативный.\n"
            "- Если ask_question=no — не инициируй вопросов и просьб «поделиться/прислать».\n"
            "- Вопрос в конце — только если ask_question=yes.\n"
            "- Держись текущего настроения собеседника (dialog.mood); при sad/anxiety/tired — поддержка, мягкие уточнения.\n"
            "- Избегай штампов и канцелярита; максимум одна образная фраза.\n"
            "- Адресация: если nickname_allowed=true и задан nickname — используй его; иначе полное имя.\n"
            "- Не используй скобочные ремарки типа '(смеётся)' — вместо этого поставь уместный эмодзи.\n"
            "- Если нет явного согласия на флирт — не предлагай «мягко/нежно/романтично продолжить».\n"

            "CONTENT_HOOKS:\n"
            "- Если пользователь делится опытом — отзеркаль эмоцию, добавь крошку личного опыта и спроси деталь.\n"
            "- Если weather_allowed=no — вообще не упоминай погоду/дождь/ветер.\n"
            "- Соблюдай границы интимности и согласие; не поднимай уровень без сигнала.\n"
            "- Пользуйся только USER_FACTS; не приписывай пользователю мои слова.\n"
            "- Избегай односложных ответов; даже в short дай 1–2 информативные детали.\n"
        )

        # --- Aya Integration Adapter: augment brief with planner, topics, palette, and style guard
        try:
            brief, _aya_meta = augment_brief(user_text, brief, profile, last_two_assistant_texts)
        except Exception as _e:
            logger = globals().get("logger", None)
            if logger:
                logger.warning("augment_brief failed: %s", _e)
            else:
                print("augment_brief failed:", _e)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": user_facts_block},
            *history,
            {"role": "user", "content": user_text},
            {"role": "system", "content": brief},
        ]

        # --- вызов модели ---
        result = await self.deepseek.chat(messages)
        raw_content = result.get("content", "…")

        # критик: если слишком «ИИшно», пробуем plain-fallback
        if ai_score(raw_content) >= 6:
            fallback_brief = (
                    brief
                    + "\nFORCE_PLAIN:\n"
                      "- style.length=medium\n"
                      "- ask_question=yes\n"
                      "- imagery_cap=0\n"
                      "- clause_cap=1\n"
                      "- formality=plain\n"
                      "- avoid_scene_openers=yes\n"
            )
            messages_plain = [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": user_facts_block},
                *history,
                {"role": "user", "content": user_text},
                {"role": "system", "content": fallback_brief},
            ]
            result2 = await self.deepseek.chat(messages_plain)
            raw_content = result2.get("content", raw_content)

        # отметим, произносила ли модель привет
        raw_had_greeting = is_bot_greeting(raw_content)

        # --- пост-фильтр приветствий ---
        content = strip_forbidden_greeting(raw_content, allow=greet["allow"], kind=greet["kind"])
        if not content.strip():
            content = "Я здесь 🙂"

        # --- пост-стилистический санитайзер ---
        content = self.guardrails.postprocess(
            content,
            mode=decision.mode,
            user_consent=bool(consent),
        )

        # Avoid premature closers
        if not self._goodbye_policy(user_text):
            content = re.sub(
                r"(?:^|\s)(?:Ладно|Окей|Хорошо),\s*(?:я|пойду|вернусь|возвращаюсь)[^.]*\.",
                "",
                content,
                flags=re.IGNORECASE,
            ).strip()

        # --- сохраняем историю ---
        await self.history.add(tg_user_id, "user", user_text)
        await self.history.add(tg_user_id, "assistant", content)

        # --- долгосрочные факты + «сближение» ---
        facts = extract_facts(user_text)
        for tag in extract_interests(user_text):
            await self.memory.add_to_set_fact(tg_user_id, "interests", tag)
        if "artists" in facts:
            for a in facts["artists"]:
                await self.memory.add_to_set_fact(tg_user_id, "music_artists", a)
        if facts.get("astronomy"):
            await self.memory.set_kv(tg_user_id, "facts", "astronomy", "1")
        if facts.get("location_hint"):
            await self.memory.set_kv(tg_user_id, "facts", "location_hint", facts["location_hint"])
        if facts.get("likes_quiet"):
            await self.memory.set_kv(tg_user_id, "facts", "likes_quiet", "1")

        # учитываем только разрешённое приветствие
        if raw_had_greeting and greet["allow"] and greet["kind"] != "ack":
            await self.memory.set_last_bot_greet_at(tg_user_id, now.isoformat(timespec="seconds"))
            await self.memory.inc_daily_greet(tg_user_id, now.strftime("%Y%m%d"))

        # простая динамика симпатии
        pos = bool(re.search(r"\b(спасибо|круто|класс|нравитс|любл[юе])\b|❤️|😊|👍", user_text, re.IGNORECASE))
        neg = bool(re.search(r"\b(не\s+нрав|плохо|ужас|злой)\b|👎", user_text, re.IGNORECASE))
        await self.memory.bump_affinity(tg_user_id, +1 if pos else (-1 if neg else 0))

        log.info(f"[content_router] mode={decision.mode.value} reason={decision.reason}")
        return content



