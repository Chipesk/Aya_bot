# dialogue/summarizer.py
import json
from typing import List, Dict

SYSTEM = (
    "Ты — суммаризатор диалога. Сделай краткую выжимку эпизода и выдели факты."
    "Верни ТОЛЬКО JSON: {title, summary, facts}."
    "facts — массив объектов {predicate, object, dtype, confidence} как в извлечении фактов."
    "Не придумывай."
)

USER_TMPL = (
    "Ниже последовательность сообщений user/assistant. Сожми их в один эпизод (2-4 предложения) с названием и извлеки факты пользователя.\n"
    "DIALOG:\n{dialog}\n"
)

def _format_dialog(history: List[Dict[str, str]]) -> str:
    lines = []
    for m in history:
        role = m.get("role", "user")
        text = (m.get("content") or "").replace("\n", " ").strip()
        lines.append(f"{role}: {text}")
    return "\n".join(lines)

async def summarize_episode(history: List[Dict[str, str]], llm_client):
    dialog = _format_dialog(history)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER_TMPL.format(dialog=dialog)},
    ]
    try:
        r = await llm_client.chat(messages)
        content = (r.get("content", "") or "").strip().strip("` ")
        if content.lower().startswith("json"):
            content = content[4:].lstrip()
        obj = json.loads(content)
        # минимальные дефолты
        return {
            "title": obj.get("title") or "Эпизод",
            "summary": obj.get("summary") or "",
            "facts": obj.get("facts") or [],
        }
    except Exception:
        # фолбэк — пустая «шапка»
        return {"title": "Эпизод", "summary": "", "facts": []}
