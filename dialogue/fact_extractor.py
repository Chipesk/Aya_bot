# dialogue/fact_extractor.py
import json
import re
from typing import List, Dict, Any, Optional

# --------- быстрые офлайн-правила (работают и без LLM) ---------

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
            out.append({"predicate": "age", "object": age, "dtype": "int", "confidence": 0.98})
            if age >= 18:
                out.append({"predicate": "adult", "object": True, "dtype": "bool", "confidence": 0.95})
    return out


# --------- нормализация ключей/значений ---------

# минимальная транслитерация кириллицы -> латиница (достаточно для snake_case)
_CYR2LAT = str.maketrans({
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z",
    "и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r",
    "с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch",
    "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
    "А":"a","Б":"b","В":"v","Г":"g","Д":"d","Е":"e","Ё":"e","Ж":"zh","З":"z",
    "И":"i","Й":"y","К":"k","Л":"l","М":"m","Н":"n","О":"o","П":"p","Р":"r",
    "С":"s","Т":"t","У":"u","Ф":"f","Х":"h","Ц":"c","Ч":"ch","Ш":"sh","Щ":"sch",
    "Ъ":"","Ы":"y","Ь":"","Э":"e","Ю":"yu","Я":"ya",
})

def _to_snake_latin(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return s
    s = s.translate(_CYR2LAT)
    s = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE)  # всё, что не буква/цифра/_, -> _
    s = re.sub(r"_+", "_", s).strip("_").lower()
    if not s:
        s = "fact"
    # ограничим длину
    return s[:64]

def _coerce_dtype_and_object(dtype: Optional[str], obj: Any) -> (str, Any):
    # авто-определение при отсутствии dtype
    if dtype is None:
        if isinstance(obj, bool): dtype = "bool"
        elif isinstance(obj, int): dtype = "int"
        elif isinstance(obj, float): dtype = "float"
        else: dtype = "str"
    dtype = dtype.lower()

    if dtype == "bool":
        if isinstance(obj, bool):
            return "bool", obj
        if isinstance(obj, (int, float)):
            return "bool", (obj != 0)
        s = str(obj).strip().lower()
        return "bool", s in {"true", "yes", "1", "да", "верно", "ага"}
    if dtype == "int":
        try:
            return "int", int(obj)
        except Exception:
            # мягкий даунгрейд
            try:
                return "int", int(float(obj))
            except Exception:
                return "str", str(obj)
    if dtype == "float":
        try:
            return "float", float(obj)
        except Exception:
            return "str", str(obj)
    if dtype == "date":
        # не парсим формат сейчас; оставляем строкой, но dtype сохраняем
        return "date", str(obj)
    # default: str
    return "str", str(obj)

def _clamp_conf(x: Any, default: float = 0.7) -> float:
    try:
        v = float(x)
    except Exception:
        v = default
    if v != v:  # NaN
        v = default
    return max(0.0, min(1.0, v))


def normalize_fact(f: Dict[str, Any]) -> Dict[str, Any]:
    pred = _to_snake_latin(str(f.get("predicate", "")))
    dtype = f.get("dtype")
    dtype, obj = _coerce_dtype_and_object(dtype, f.get("object"))
    conf = _clamp_conf(f.get("confidence", 0.7))
    unit = f.get("unit")
    # ограничители размеров
    if isinstance(obj, str):
        obj = obj[:2048]
    return {
        "predicate": pred[:64],
        "object": obj,
        "dtype": dtype,
        "unit": unit[:32] if isinstance(unit, str) else unit,
        "confidence": conf,
    }


# --------- парсинг JSON из ответа модели ---------

def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        # убираем ```json ... ```
        s = s[3:]
        s = re.sub(r"^\s*json", "", s, flags=re.IGNORECASE)
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()

_JSON_ARRAY_RE = re.compile(r"\[\s*{", re.DOTALL)

def _extract_first_json_array(s: str) -> Optional[str]:
    """
    Находит первый JSON-массив (начинается с '[') и возвращает подсроку с корректными скобками.
    """
    s = s.strip()
    m = _JSON_ARRAY_RE.search(s)
    if not m:
        return None
    start = m.start()
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(s[start:], start=start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return s[start:i+1]
    return None


# --------- основной API ---------

EXTRACT_SYSTEM = (
    "Ты — извлекатель фактов. Верни ТОЛЬКО JSON-массив.\n"
    "Элемент: {predicate, object, dtype, unit?, confidence}.\n"
    "predicate: краткий латинский snake_case (например: age, job_title, company, city, hobby, favorite_flower, pet_name, lactose_intolerance).\n"
    "dtype ∈ {str,int,float,bool,date}. object должен соответствовать dtype. Не придумывай, только явно сказанное. confidence в диапазоне 0..1."
)

EXTRACT_USER_TMPL = (
    "Извлеки факты из реплики пользователя.\n"
    "TEXT:\n```{text}```\n"
    "Если фактов нет — верни []"
)

async def extract_facts_generic(text: str, llm_client) -> List[Dict[str, Any]]:
    """
    Возвращает list[dict] со схемой:
      {predicate:str, object:Any, dtype:str, unit?:str, confidence:float}
    Никаких whitelist'ов. Устойчив к мусору в ответе модели.
    """
    facts: List[Dict[str, Any]] = []
    # 1) офлайн-правила
    facts.extend(await _fallback_rules(text))

    # 2) LLM
    try:
        messages = [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": EXTRACT_USER_TMPL.format(text=text)},
        ]
        r = await llm_client.chat(messages)

        # поддержка разных клиентов:
        # a) { "content": "...json..." }
        # b) { "choices":[{"message":{"content":"...json..."}}], ...}
        content = None
        if isinstance(r, dict):
            if "content" in r:
                content = r.get("content")
            elif "choices" in r and r["choices"]:
                content = r["choices"][0].get("message", {}).get("content")
        if content is None:
            content = ""

        raw = _strip_code_fences(str(content))
        json_str = _extract_first_json_array(raw) or raw  # попробуем вытащить первый массив

        parsed = json.loads(json_str)
        if isinstance(parsed, list):
            for it in parsed:
                if not isinstance(it, dict):
                    continue
                if "predicate" not in it or "object" not in it:
                    continue
                norm = normalize_fact(it)
                # мягкая фильтрация мусора
                if not norm["predicate"]:
                    continue
                if norm["dtype"] == "str" and len(str(norm["object"]).strip()) == 0:
                    continue
                facts.append(norm)
    except Exception:
        # глушим любые ошибки парсинга/клиента — остаётся офлайн-набор
        pass

    # 3) дедуп по (predicate, object as JSON)
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for f in facts:
        key = (f["predicate"], json.dumps(f["object"], ensure_ascii=False, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)

    # 4) ограничитель на совсем «разговорчивые» ответы
    if len(uniq) > 50:
        uniq = uniq[:50]
    return uniq
