# dialogue/fact_extractor.py
import json
import re
from typing import List, Dict, Any

AGE_RE = re.compile(r"\bмне\s+(?P<age>\d{1,2})\s*(?:год(?:а|ов)?|лет)?\b", re.IGNORECASE)

async def _fallback_rules(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    t = (text or "").strip()
    if not t:
        return out
    m = AGE_RE.search(t)
    if m:
        age = int(m.group("age"))
        if 1 <= age <= 99:
            out.append({"predicate": "age", "object": age, "dtype": "int", "unit": "years", "confidence": 0.98})
            if age >= 18:
                out.append({"predicate": "adult", "object": True, "dtype": "bool", "confidence": 0.95})
    return out

EXTRACT_SYSTEM = (
    "Ты — парсер фактов. Верни ТОЛЬКО JSON-массив без текста. "
    "Каждый элемент: {predicate, object, dtype, unit?, confidence}. "
    "predicate — короткий латинский снейк-кейс (например: age, job_title, company, city, hobby, favorite_flower, car_model). "
    "dtype ∈ {str,int,float,bool,date}. object — значение в этом типе. unit — опционально. "
    "Не придумывай факты. Уверенность от 0 до 1. Без повторов."
)

EXTRACT_USER_TMPL = (
    "Извлеки факты из реплики пользователя:\n"
    "TEXT: ```{text}```\n"
    "Если фактов нет — верни пустой массив []."
)

async def extract_facts_generic(text: str, llm_client) -> List[Dict[str, Any]]:
    """
    Универсальное извлечение через LLM, с фолбэком на регулярки.
    """
    facts = await _fallback_rules(text)
    # попытка LLM
    try:
        messages = [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": EXTRACT_USER_TMPL.format(text=text)},
        ]
        r = await llm_client.chat(messages)
        content = r.get("content", "").strip()
        # допускаем, что модель обернула кодблоком — снимем
        if content.startswith("```"):
            content = content.strip("` \n")
            # могли оставить язык после ```
            content = re.sub(r"^json\s*", "", content)
        parsed = json.loads(content)
        if isinstance(parsed, list):
            # лёгкая нормализация
            norm = []
            for it in parsed:
                if not isinstance(it, dict) or "predicate" not in it or "object" not in it:
                    continue
                pr = str(it["predicate"]).strip().lower().replace(" ", "_")
                obj = it["object"]
                dt = it.get("dtype")
                unit = it.get("unit")
                conf = float(it.get("confidence", 0.7))
                # auto dtype if missing
                if dt is None:
                    if isinstance(obj, bool): dt = "bool"
                    elif isinstance(obj, int): dt = "int"
                    elif isinstance(obj, float): dt = "float"
                    else: dt = "str"
                norm.append({"predicate": pr, "object": obj, "dtype": dt, "unit": unit, "confidence": conf})
            facts.extend(norm)
    except Exception:
        pass
    # дедуп по (predicate, object)
    seen = set()
    uniq = []
    for f in facts:
        key = (f["predicate"], json.dumps(f["object"], ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)
    return uniq
