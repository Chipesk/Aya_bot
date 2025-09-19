"""Primary router wiring Telegram updates to AyaBrain."""
from __future__ import annotations

from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart

from orchestrator.aya_brain import AyaBrain
from memory.repo import MemoryRepo

router = Router(name="basic")


@router.message(CommandStart())
async def cmd_start(message: types.Message, aya_brain: AyaBrain, memory_repo: MemoryRepo) -> None:
    user = message.from_user
    if user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    tg_user_id = user.id
    await aya_brain.reset_user(tg_user_id)
    await memory_repo.set_dialog_state(tg_user_id, "greeting", "")
    await message.answer("Привет! Я Ая. Расскажи, как тебя зовут или что у тебя на уме.")


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer("Я рядом, чтобы обсудить настроение, планы, погоду или просто поболтать.")


@router.message(Command("me"))
async def cmd_me(message: types.Message, memory_repo: MemoryRepo, tg_user_id: int) -> None:
    name = await memory_repo.get_user_display_name(tg_user_id)
    prefs = await memory_repo.get_user_prefs(tg_user_id)
    affinity = await memory_repo.get_affinity(tg_user_id)
    lines = [
        f"имя: {name or '—'}",
        f"ник: {prefs.get('nickname') or '—'} (allowed={prefs.get('nickname_allowed')})",
        f"affinity: {affinity}",
    ]
    await message.answer("\n".join(lines))


@router.message(Command("aya_diag"))
async def cmd_diag(message: types.Message, aya_brain: AyaBrain, tg_user_id: int) -> None:
    diag = await aya_brain.diagnostics(tg_user_id)
    lines = ["Диагностика:"]
    metrics = diag.get("metrics", {})
    lines.append(
        "метрики: "
        + ", ".join(f"{k}={v}" for k, v in metrics.items())
    )
    persona_traits = ", ".join(diag.get("persona_traits", []))
    lines.append(f"persona_traits: {persona_traits}")
    llm = diag.get("llm", {})
    lines.append(f"llm: ok={llm.get('ok')} note={llm.get('note')}")
    await message.answer("\n".join(lines))


@router.message(Command("health"))
async def cmd_health(message: types.Message, aya_brain: AyaBrain, tg_user_id: int) -> None:
    diag = await aya_brain.diagnostics(tg_user_id)
    metrics = diag.get("metrics", {})
    await message.answer(
        "status: OK\n"
        f"facts_stored: {metrics.get('facts_stored')}\n"
        f"recall_hit_rate: {metrics.get('recall_hit_rate')}"
    )


@router.message(F.text)
async def all_text(message: types.Message, aya_brain: AyaBrain, tg_user_id: int) -> None:
    user_text = message.text or ""
    response = await aya_brain.respond(tg_user_id, user_text)
    await message.answer(response.text)
