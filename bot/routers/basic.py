# bot/routers/basic.py
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dialogue.flirt import detect_flirt_intent, apply_flirt_state
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command

router = Router(name="basic")

# ====== Настройки ======
NICK_STATE_TTL = 180  # сек: окно, пока "да/ок"/одно слово считаются шагом выбора ника

# ====== Регэкспы ======
NAME_DECL_RE = re.compile(
    r"(?:^|\b)меня\s+зовут\s+([A-Za-zА-Яа-яЁё\-]{2,20})(?:\b|$)", re.IGNORECASE
)
ASK_NAME_RE = re.compile(r"\b(как\s+меня\s+зовут|какое\s+у\s+меня\s+имя|как\s+меня\s+называешь)\b", re.IGNORECASE)

ASK_WEATHER_RE = re.compile(r"\b(какая|что\s+по)\s+погод[аеы]\b", re.IGNORECASE)
ASK_DATE_RE = re.compile(r"\b(какая\s+(?:сегодня|сейчас)\s+дата|какое\s+(?:сегодня|сейчас)\s+число|дата\s*(пж|пожалуйста)?)\b", re.IGNORECASE)
ASK_TIME_RE = re.compile(
    r"(?:(?:^|\s)(?:который\s+час|сколько\s+(?:сейчас\s+)?времени)(?:\?|$))"
    r"|^(?:а\s*)?время\?$",
    re.IGNORECASE
)
ASK_DATETIME_BOTH_RE = re.compile(r"\b(врем[яи].*дат[аы]|дат[аы].*врем[яи])\b", re.IGNORECASE)

# Никнеймы / ласковость
NICK_ALLOW_RE = re.compile(r"\b(зови|называй|можешь\s+называть|обращайся)\b.*\b(мило|по[-\s]*доброму|ласково)\b", re.IGNORECASE)
NICK_FORBID_RE = re.compile(r"\b(не\s+зови|не\s+называй|без\s+уменьшительных|не\s+уменьшай)\b", re.IGNORECASE)
NICK_SET_RE = re.compile(r"\b(зови\s+меня|называй\s+меня|можешь\s+звать\s+меня)\s+([A-Za-zА-Яа-яЁё\-]{2,20})\b", re.IGNORECASE)
NICK_INDIRECT_SET_RE = re.compile(r"\b(?:давай|просто)\s+([A-Za-zА-Яа-яЁё\-]{2,20})\b", re.IGNORECASE)
YES_RE = re.compile(r"^(да|ок|ага|конечно|пусть|давай)\b", re.IGNORECASE)
NO_RE  = re.compile(r"^(нет|не)\b", re.IGNORECASE)

AFF_WARM_RE   = re.compile(r"\b(можешь|давай)\b.*\b(ласково|теплее|по[-\s]*доброму)\b", re.IGNORECASE)
AFF_ROM_RE    = re.compile(r"\b(можешь|давай)\b.*\b(романтич|очень\s+ласково|любимый|дорогой)\b", re.IGNORECASE)
AFF_STRICT_RE = re.compile(r"\b(без\s+уменьшительных|строго|официально)\b", re.IGNORECASE)
ASK_REMEMBER_RE = re.compile(
    r"\b(что\s+ты\s+(?:помнишь|запомнила)\s+обо\s+мне|что\s+ты\s+обо\s+мне\s+зна[её]шь|что\s+запомнила\s+про\s+меня)\b",
    re.IGNORECASE
)
# Темы
MUSIC_RE = re.compile(r"\b(музык|песня|трек|альбом|плейлист|radiohead|london\s+grammar|kid\s*a)\b", re.IGNORECASE)

NEG_FREE_TIME_RE = re.compile(r"\bсвободн\w*\s+врем\w*\b", re.IGNORECASE)

def is_time_question(text: str) -> bool:
    if not text:
        return False
    if NEG_FREE_TIME_RE.search(text):
        return False
    if len(text) <= 40 and ASK_TIME_RE.search(text):
        return True
    return bool(re.search(r"^(который\s+час|сколько\s+(?:сейчас\s+)?времени)\b", text.strip(), re.IGNORECASE))

# ====== Хелперы ======
def extract_name(text: str) -> str | None:
    m = NAME_DECL_RE.search(text)
    if not m:
        return None
    cand = m.group(1).strip()
    if cand.lower() in {"запомнила", "запомни", "пожалуйста"}:
        return None
    return cand[:1].upper() + cand[1:]

BAD_FORMS = {"лёха", "леха", "алекс", "алексиус", "саня", "димон", "серёга", "серега"}

def _is_bad_nick(nick: str) -> bool:
    s = (nick or "").strip().lower()
    if not (2 <= len(s) <= 20):
        return True
    if s in BAD_FORMS:
        return True
    return False

def suggest_nick(display_name: str) -> list[str]:
    mapping = {
        "Алексей": ["Лёша", "Алёша"],
        "Александр": ["Саша"],
        "Дмитрий": ["Дима"],
        "Михаил": ["Миша"],
        "Сергей": ["Серёжа"],
        "Евгений": ["Женя"],
        "Павел": ["Паша"],
        "Роман": ["Рома"],
        "Илья": ["Илья"],
        "Владимир": ["Вова"],
        "Тимофей": ["Тима"],
        "Максим": ["Макс"],
        "Анна": ["Аня"],
        "Екатерина": ["Катя"],
        "Мария": ["Маша"],
        "Ольга": ["Оля"],
        "Елена": ["Лена"],
        "Юлия": ["Юля"],
        "Наталья": ["Наташа"],
        "Ирина": ["Ира"],
        "Светлана": ["Света"],
        "Виктория": ["Вика"],
        "Карина": ["Кариша"],
    }
    opts = mapping.get(display_name, [])
    return [o for o in opts if o.strip().lower() not in BAD_FORMS]

def human_weather(world: dict) -> str:
    w = world.get("weather", {}) or {}
    t = w.get("temp_c")
    rainy = bool(w.get("is_rainy"))
    t_str = f"{int(round(t))}°C" if t is not None else "нормально по температуре"
    mood = "дождливо и сыро" if rainy else "сухо"
    return f"{t_str}, {mood}"

# ====== Команды ======
@router.message(Command("me"))
async def me_dump(message: types.Message, memory_repo, tg_user_id: int):
    name = await memory_repo.get_user_display_name(tg_user_id)
    prefs = await memory_repo.get_user_prefs(tg_user_id)
    mode = await memory_repo.get_user_affection_mode(tg_user_id)
    affinity = await memory_repo.get_affinity(tg_user_id)
    artists = await memory_repo.get_set_fact(tg_user_id, "music_artists")
    astro = await memory_repo.get_kv(tg_user_id, "facts", "astronomy")
    loc = await memory_repo.get_kv(tg_user_id, "facts", "location_hint")
    quiet = await memory_repo.get_kv(tg_user_id, "facts", "likes_quiet")
    await message.answer(
        "Я помню:\n"
        f"• имя: {name or '—'}\n"
        f"• ник: {prefs.get('nickname') or '—'} (allowed={prefs.get('nickname_allowed')})\n"
        f"• ласковость: {mode}, affinity={affinity}\n"
        f"• музыка: {', '.join(artists) if artists else '—'}\n"
        f"• астрономия: {'да' if astro=='1' else '—'}\n"
        f"• локация: {loc or '—'}\n"
        f"• любит тишину: {'да' if quiet=='1' else '—'}"
    )

@router.message(Command("reload_persona"))
async def reload_persona(message: types.Message, aya_brain):
    aya_brain.persona.reload()
    await message.answer("Персона перезагружена ✅")

@router.message(Command("reset_name"))
async def reset_name(message: types.Message, memory_repo, tg_user_id: int):
    await memory_repo.set_user_display_name(tg_user_id, "")
    await memory_repo.set_user_nickname(tg_user_id, "")
    await memory_repo.set_user_nickname_allowed(tg_user_id, False)
    await message.answer("Имя и ник сброшены. Скажи: «меня зовут Имя», чтобы я запомнила.")

@router.message(CommandStart())
async def cmd_start(message: types.Message, aya_brain, memory_repo):
    tg_user_id = message.from_user.id

    # Полный сброс состояния (история, тема, ласковость, имя/ник, приветы)
    await aya_brain.reset_user(tg_user_id)

    # Начинаем знакомство одинаково
    text = "Привет! Я Ая. Давай знакомиться. Как тебя зовут?"
    await message.reply(text)

    # Помечаем «привет» и открываем короткое окно для ввода имени одним словом
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    await memory_repo.set_last_bot_greet_at(tg_user_id, now.isoformat(timespec="seconds"))
    await memory_repo.inc_daily_greet(tg_user_id, now.strftime("%Y%m%d"))
    # включаем режим ожидания имени
    await memory_repo.set_dialog_state(tg_user_id, "name_context", "")

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.reply("Я рядом: поболтать, поддержать, придумать планы. Скажи «меня зовут …», чтобы я обращалась по имени.")

@router.message(Command("health"))
async def health(message: types.Message):
    # Проверяем и БД, и LLM (ожидается, что в main.py положены bot['db'] и bot['deepseek'])
    db = message.bot.get("db")
    deepseek = message.bot.get("deepseek")

    ok_db = False
    db_err = None
    if db is not None:
        try:
            cur = await db.conn.execute("SELECT 1")
            await cur.fetchone()
            ok_db = True
        except Exception as e:
            db_err = str(e)

    ok_ai = False
    ai_note = "n/a"
    if deepseek is not None:
        try:
            ok_ai, ai_note = await deepseek.health_check()
        except Exception as e:
            ai_note = f"error: {e}"

    status = "OK" if (ok_db and ok_ai) else ("DEGRADED" if (ok_db or ok_ai) else "FAIL")
    lines = [
        f"status: {status}",
        f"db: {'ok' if ok_db else 'fail'}",
        f"llm: {'ok' if ok_ai else 'fail'} ({ai_note})",
    ]
    if not ok_db and db_err:
        lines.append(f"db_error: {db_err}")
    await message.answer("\n".join(lines))

@router.message(Command("flirt"))
async def flirt_info(message: types.Message, memory_repo, tg_user_id: int):
    consent = await memory_repo.get_flirt_consent(tg_user_id)
    level = await memory_repo.get_flirt_level(tg_user_id)
    await message.answer(f"Флирт: {'вкл' if consent else 'выкл'}, уровень: {level}")

@router.message(Command("flirt_off"))
async def flirt_off(message: types.Message, memory_repo, tg_user_id: int):
    await memory_repo.set_flirt_consent(tg_user_id, False)
    await memory_repo.set_flirt_level(tg_user_id, "off")
    await message.answer("Флирт выключила.")

@router.message(Command("debug_world"))
async def debug_world(message: types.Message, world_state):
    ctx = await world_state.get_context()
    await message.answer(
        f"Город: {ctx.get('city')}\n"
        f"Время: {ctx.get('local_time_iso')}\n"
        f"Погода: {human_weather(ctx)}"
    )

# ====== ЕДИНСТВЕННЫЙ общий хендлер текста ======
@router.message(F.text)
async def free_chat(message: types.Message, tg_user_id: int, aya_brain, memory_repo, world_state, chat_history, facts_repo):
    text = (message.text or "").strip()
    await memory_repo.touch_seen(tg_user_id)

    # Шторка погоды и TTL для состояний name/nick
    intent, payload, ts = await memory_repo.get_dialog_state(tg_user_id)
    if intent == "weather" and not ASK_WEATHER_RE.search(text):
        await memory_repo.clear_dialog_state(tg_user_id)
        intent, payload, ts = "", "", None

    # --- флирт-интенты ---
    fi = detect_flirt_intent(text)
    if fi:
        reply = await apply_flirt_state(memory_repo, tg_user_id, fi)
        if reply:
            await message.answer(reply)
            return

    # свеж ли контекст ника/имени?
    is_fresh = False
    if ts:
        try:
            is_fresh = (datetime.now(ZoneInfo("Europe/Moscow")) - datetime.fromisoformat(ts)) <= timedelta(seconds=NICK_STATE_TTL)
        except Exception:
            is_fresh = False

    # --- «что ты помнишь обо мне?» — отвечаем из памяти, не через LLM
    if ASK_REMEMBER_RE.search(text):
        # топ фактов из универсального хранилища
        top = await facts_repo.top_facts(tg_user_id, limit=12)

        # плюс совместимость со старым KV (имя/ник и т.п.)
        name = await memory_repo.get_user_display_name(tg_user_id)
        prefs = await memory_repo.get_user_prefs(tg_user_id)

        lines = []
        if name:
            lines.append(f"тебя зовут {name}")
        if prefs.get("nickname"):
            lines.append(f"можно звать «{prefs['nickname']}»")

        # человекочитаемая сборка предикатов
        for it in top:
            p = it["predicate"];
            o = it["object"];
            dt = (it.get("dtype") or "str")
            if p == "age" and dt in ("int", "str"):
                lines.append(f"тебе {o}")
            elif p in ("job_title", "role"):
                lines.append(f"роль: {o}")
            elif p in ("company", "employer"):
                lines.append(f"компания: {o}")
            elif p in ("industry", "domain"):
                lines.append(f"сфера: {o}")
            elif p.startswith("favorite_"):
                pretty = p.replace("favorite_", "любимое ").replace("_", " ")
                lines.append(f"{pretty}: {o}")
            elif p in ("city", "location", "district"):
                lines.append(f"локация: {o}")
            elif p in ("hobby", "hobbies"):
                lines.append(f"увлечения: {o}")
            elif p in ("pet", "has_pet", "pet_name"):
                lines.append(f"питомцы: {o}")
            elif p in ("car_model", "bike_model"):
                lines.append(f"транспорт: {o}")
            elif p in ("adult",):
                # не проговариваем явно; можно использовать для фильтров
                continue
            else:
                # дефолтно показываем как «факт: значение»
                pretty = p.replace("_", " ")
                lines.append(f"{pretty}: {o}")

        text_out = (
            "Я запомнила: " + "; ".join(dict.fromkeys(lines)) + "."
            if lines else
            "Пока точно помню твоё имя. Можешь рассказать, чем занимаешься, возраст, увлечения — я сохраню."
        )
        await message.answer(text_out)
        return

    # Имя из фразы «меня зовут …»
    name = extract_name(text)
    if name:
        await memory_repo.set_user_display_name(tg_user_id, name)
        await message.answer(f"Приятно, {name}! Запомнила 😊")
        await memory_repo.clear_dialog_state(tg_user_id)
        return

    # Если мы только что попросили имя (/start → name_context) и пришло одно слово — считаем его именем
    if intent == "name_context" and is_fresh and re.fullmatch(r"[A-Za-zА-Яа-яЁё\-]{2,20}", text):
        await memory_repo.set_user_display_name(tg_user_id, text.strip().title())
        await memory_repo.clear_dialog_state(tg_user_id)
        await message.answer(f"Приятно, {text.strip().title()}! Запомнила 😊")
        return

    # Ласковость
    if AFF_STRICT_RE.search(text):
        await memory_repo.set_user_affection_mode(tg_user_id, "none")
        await message.answer("Хорошо. Буду обращаться строго по имени, без уменьшительных.")
        return
    if AFF_ROM_RE.search(text):
        await memory_repo.set_user_affection_mode(tg_user_id, "romantic")
        await message.answer("Поняла. Буду нежнее — но деликатно.")
        return
    if AFF_WARM_RE.search(text):
        await memory_repo.set_user_affection_mode(tg_user_id, "warm")
        await message.answer("Буду чуть теплее в обращении.")
        return

    # «как меня зовут?»
    if ASK_NAME_RE.search(text):
        known = await memory_repo.get_user_display_name(tg_user_id)
        await memory_repo.set_dialog_state(tg_user_id, "name_context", "")
        await message.answer(f"Тебя зовут {known} 😊" if known else "Пока не знаю. Скажи: «меня зовут Имя», и я запомню.")
        return

    # Ник: разрешение/запрет/установка
    if NICK_ALLOW_RE.search(text):
        await memory_repo.set_user_nickname_allowed(tg_user_id, True)
        display = await memory_repo.get_user_display_name(tg_user_id)
        options = suggest_nick(display or "")
        if options:
            await memory_repo.set_dialog_state(tg_user_id, "nickname_choice", "|".join(options))
            opts_str = " или ".join(options)
            await message.answer(f"Подойдёт «{opts_str}»? Напиши вариант или «давай {options[0]}».")
        else:
            await memory_repo.set_dialog_state(tg_user_id, "nickname_wait", "")
            await message.answer("Напиши, как именно тебе приятно, и я запомню.")
        return

    if NICK_FORBID_RE.search(text):
        await memory_repo.set_user_nickname_allowed(tg_user_id, False)
        await memory_repo.set_user_nickname(tg_user_id, None)
        await memory_repo.clear_dialog_state(tg_user_id)
        await message.answer("Поняла. Буду обращаться строго по имени, без уменьшительных.")
        return

    m_nick = NICK_SET_RE.search(text)
    if m_nick:
        nick = m_nick.group(2).strip()
        if _is_bad_nick(nick):
            await message.answer("Так не очень звучит. Напиши, пожалуйста, как тебе комфортно, например «зови меня Лёша».")
            return
        await memory_repo.set_user_nickname_allowed(tg_user_id, True)
        await memory_repo.set_user_nickname(tg_user_id, nick)
        await memory_repo.clear_dialog_state(tg_user_id)
        await message.answer(f"Хорошо, буду называть тебя «{nick}».")
        return

    # Последующий шаг ника — только в рамках свежего окна
    if intent in {"name_context", "nickname_choice", "nickname_wait"}:
        # если состояние несвежее и сообщение не про имя/ник — сбрасываем и идём дальше
        if not is_fresh and not (NICK_SET_RE.search(text) or NICK_INDIRECT_SET_RE.search(text) or ASK_NAME_RE.search(text)):
            await memory_repo.clear_dialog_state(tg_user_id)
        else:
            m_ind = NICK_INDIRECT_SET_RE.search(text)
            if m_ind:
                nick = m_ind.group(1).strip()
                if _is_bad_nick(nick):
                    await message.answer("Поняла. Лучше что-то нейтральное и без просторечий.")
                    return
                await memory_repo.set_user_nickname_allowed(tg_user_id, True)
                await memory_repo.set_user_nickname(tg_user_id, nick)
                await memory_repo.clear_dialog_state(tg_user_id)
                await message.answer(f"Окей, тогда «{nick}».")
                return

            # короткое «да/ок» — только для nickname_choice/wait и только пока свежо
            if is_fresh and YES_RE.match(text) and intent in {"nickname_choice", "nickname_wait"}:
                if intent == "nickname_choice" and payload:
                    first = payload.split("|")[0]
                    await memory_repo.set_user_nickname_allowed(tg_user_id, True)
                    await memory_repo.set_user_nickname(tg_user_id, first)
                    await memory_repo.clear_dialog_state(tg_user_id)
                    await message.answer(f"Супер! Тогда буду звать «{first}».")
                    return
                await memory_repo.set_dialog_state(tg_user_id, "nickname_wait", "")
                await message.answer("Напиши, как именно тебе приятно, и я запомню.")
                return

            # одно слово — считаем ником (только пока свежо)
            if is_fresh and re.fullmatch(r"[A-Za-zА-Яа-яЁё\-]{2,20}", text):
                candidate = text.strip()
                if _is_bad_nick(candidate):
                    await message.answer("Поняла. Лучше что-то нейтральное и без просторечий.")
                    return
                await memory_repo.set_user_nickname_allowed(tg_user_id, True)
                await memory_repo.set_user_nickname(tg_user_id, candidate)
                await memory_repo.clear_dialog_state(tg_user_id)
                await message.answer(f"Отлично! Тогда «{candidate}».")
                return

            if NO_RE.match(text):
                await memory_repo.clear_dialog_state(tg_user_id)
                await message.answer("Окей, остаюсь при обычном обращении по имени.")
                return

    # Факты (детерминированно)
    if ASK_DATETIME_BOTH_RE.search(text):
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        out = now.strftime("Сейчас %H:%M, сегодня %d.%m.%Y")
        await memory_repo.clear_dialog_state(tg_user_id)
        await chat_history.add(tg_user_id, "user", text)
        await chat_history.add(tg_user_id, "assistant", out)
        await message.answer(out)
        return

    if ASK_DATE_RE.search(text):
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        out = now.strftime("Сегодня %d.%m.%Y")
        await memory_repo.clear_dialog_state(tg_user_id)
        await chat_history.add(tg_user_id, "user", text)
        await chat_history.add(tg_user_id, "assistant", out)
        await message.answer(out)
        return

    if ASK_TIME_RE.search(text):
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        out = now.strftime("Сейчас %H:%M")
        await memory_repo.clear_dialog_state(tg_user_id)
        await chat_history.add(tg_user_id, "user", text)
        await chat_history.add(tg_user_id, "assistant", out)
        await message.answer(out)
        return

    if ASK_WEATHER_RE.search(text):
        ctx = await world_state.get_context()
        out = f"В Питере сейчас {human_weather(ctx)}."
        await memory_repo.set_dialog_state(tg_user_id, "weather", "")
        await chat_history.add(tg_user_id, "user", text)
        await chat_history.add(tg_user_id, "assistant", out)
        await message.answer(out)
        return

    # Темы
    if MUSIC_RE.search(text):
        await memory_repo.set_topic(tg_user_id, "music")

    # LLM
    reply = await aya_brain.reply(tg_user_id, text)
    await message.answer(reply)
