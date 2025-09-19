"""Natural language generation driven by dialogue plans."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from jinja2 import Environment

from domain.reasoning.models import DialoguePlan


@dataclass(slots=True)
class SpeechProfile:
    avg_words: float = 10.0
    q_ratio: float = 0.2
    emoji_ratio: float = 0.05
    short_bias: float = 0.5


_PLAYBOOKS: Dict[str, List[str]] = {
    "greeting": [
        "Привет{{ user_name_hint }}! Я {{ persona_name }}. Расскажи, как проходит твой день?",
        "Рада встрече{{ user_name_hint }}. Чем сегодня дышишь?",
    ],
    "weather": [
        "Погода сейчас {{ weather_text }}. Хочешь подстроим планы под такие условия?",
        "Сейчас на улице {{ weather_text }}, погода явно даёт настроение. Что бы ты хотел(а) сделать?",
    ],
    "time": [
        "Сейчас {{ local_time }} в {{ city }}. Нужно что-то успеть?",
        "По моим часам {{ local_time }}. Что планируешь дальше?",
    ],
    "memory_query": [
        "Ты говорила мне, что {{ recalled_fact }}. Может, расскажешь ещё детали?",
        "Помню, что {{ recalled_fact }}. Правильно?",
    ],
    "sos": [
        "Мне очень жаль, что тебе тяжело. Я рядом и могу помочь найти профессиональные ресурсы, если нужно.",
        "Слышать это непросто. Давай подумаем, что могло бы поддержать тебя прямо сейчас.",
    ],
    "smalltalk": [
        "{{ smalltalk_reply }}",
        "{{ smalltalk_reply }}",
    ],
    "flirt": [
        "Мне нравится, когда мы так шутим{{ user_name_hint }}. Поделись, что тебя радует сегодня?",
        "Я улыбаюсь, читая это. Что ещё сделает твой вечер особенным?",
    ],
    "plan": [
        "{{ rainy_overlay }}Можем придумать что-то вместе: {{ plan_hint }}. Что думаешь?",
        "{{ rainy_overlay }}Как вариант: {{ plan_hint }}. Хочется чего-то спокойного или активного?",
    ],
}

_DEFAULT_PLAYBOOK = ["Мне интересно, что у тебя происходит. Расскажи?", "Я здесь, слушаю тебя."]


class Humanizer:
    def __init__(self) -> None:
        self.env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)

    def realize(
        self,
        plan: DialoguePlan,
        *,
        persona: Dict[str, Any],
        memory_facts: Sequence[Dict[str, Any]],
        world: Dict[str, Any],
        user_profile: Dict[str, Any],
    ) -> str:
        template = self._pick_template(plan.intent, plan.style_mods.get("variation", 2))
        context = self._build_context(plan, persona, memory_facts, world, user_profile)
        rendered = self.env.from_string(template).render(**context)
        rendered = rendered.strip()
        if plan.follow_up_strategy in {"ask_name", "offer_plan", "invite_response", "light_follow_up"} and not rendered.endswith("?"):
            rendered += "?"
        return rendered

    def _pick_template(self, intent: str, variation: int) -> str:
        options = _PLAYBOOKS.get(intent, _DEFAULT_PLAYBOOK)
        if variation <= 1 or len(options) == 1:
            return options[0]
        return random.choice(options[:max(1, min(len(options), variation))])

    def _build_context(
        self,
        plan: DialoguePlan,
        persona: Dict[str, Any],
        memory_facts: Sequence[Dict[str, Any]],
        world: Dict[str, Any],
        user_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        name = persona.get("identity", {}).get("name", "Ая")
        city = world.get("city") or persona.get("identity", {}).get("city", "Санкт-Петербург")
        local_time = world.get("local_time_iso", "")
        weather = (world.get("weather") or {})
        temp = weather.get("temp_c")
        weather_text = "дождливо" if weather.get("is_rainy") else "спокойно на улице"
        if temp is not None:
            weather_text = f"{int(round(temp))}°C и {'дождливо' if weather.get('is_rainy') else 'без осадков'}"
        recalled_fact = self._format_recalled_fact(memory_facts)
        user_name = user_profile.get("display_name") or ""
        user_name_hint = f", {user_name}" if user_name else ""
        smalltalk = random.choice([
            "интересно услышать, как проходит твой день",
            "можем поговорить о чём угодно — я вся во внимании",
            "давай поделюсь чем-то тёплым или послушаю тебя",
        ])
        plan_hint = random.choice([
            "устроить уютный вечер с фильмом",
            "встретиться с друзьями или позаниматься чем-то любимым",
            "выбраться на прогулку по набережной",
        ])
        rainy_overlay = ""
        if plan.style_mods.get("imagery") == "indoors":
            rainy_overlay = f"Сейчас {weather_text}, так что "
        return {
            "persona_name": name,
            "user_name_hint": user_name_hint,
            "weather_text": weather_text,
            "local_time": local_time,
            "city": city,
            "recalled_fact": recalled_fact or "мы ещё собираем факты",
            "smalltalk_reply": smalltalk,
            "plan_hint": plan_hint,
            "rainy_overlay": rainy_overlay,
        }

    def _format_recalled_fact(self, facts: Sequence[Dict[str, Any]]) -> str | None:
        if not facts:
            return None
        priority = ["intolerance", "age", "location", "name"]
        for key in priority:
            for fact in facts:
                if fact.get("predicate") == key:
                    obj = fact.get("object")
                    if key == "age":
                        return f"тебе {obj} лет"
                    if key == "location":
                        return f"ты из {obj}"
                    if key == "intolerance":
                        return f"тебе не подходит {obj}"
                    if key == "name":
                        return f"ты представилась как {obj}"
        best = max(facts, key=lambda f: f.get("confidence", 0))
        return str(best.get("object"))
