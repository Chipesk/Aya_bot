# dialogue/addressing.py
from random import choice, random

RUS_NAME_VARIANTS = {
    "Алексей": ["Лёша", "Алёша"],
    # сюда можно добавить и другие имена по мере необходимости
}

PETNAMES_SOFT = ["дорогой", "милый"]
PETNAMES_ROMANTIC = ["котик", "зайчик", "родной"]

def generate_name_variants(full_name: str | None) -> list[str]:
    if not full_name:
        return []
    base = full_name.strip()
    return [base] + RUS_NAME_VARIANTS.get(base, [])

def pick_address_form(display_name: str | None, nickname: str | None,
                      nickname_allowed: bool, affection_mode: str,
                      affinity: int, tone: str) -> str | None:
    """
    Возвращает форму обращения на этот ход или None (говорить нейтрально).

    Политика:
    - Если nickname_allowed == True и задан nickname — используем ИМЕННО его (без самовольных вариаций).
    - Если nickname_allowed == False или ник не задан — говорим полным именем (без уменьшительных).
    - Тёплые обращения типа «дорогой» допустимы только при явной романтике и достаточной близости,
      и только когда nickname_allowed == True (как явный сигнал разрешения на «снижение формальности»).

    affection_mode: "none" | "warm" | "romantic"
    affinity: целое, условная «близость» (-5..20+)
    tone: текущий стиль ответа (например, "off"|"soft"|"romantic"|"suggestive"|"roleplay")
    """
    # 1) Если разрешён и задан ник — используем строго его
    if nickname_allowed and nickname:
        pool = [nickname.strip()]
        # Очень деликатное допущение «ласкового» обращения — только при явной романтике и высокой близости
        if affection_mode == "romantic" and affinity >= 12 and tone in ("romantic", "suggestive", "roleplay"):
            # одно «ласковое» слово; держим редким и нейтральным
            pool += [nickname.strip(), "дорогой"]
        return choice(pool)

    # 2) Ник не задан или никнеймы запрещены — только полное имя, без уменьшительных
    base = display_name.strip() if display_name else None
    if not base:
        return None

    # 2.1 эволюция обращения: Alexey -> Лёша/Алёша -> (романтика) нежные слова
    # Стадии:
    # 0 — только полное имя
    # 1 — разрешены короткие варианты (если известны)
    # 2 — при романтическом тоне и согласии допускаются нежные слова
    stage = 0
    # тон + явное согласие дают право поднять стадию
    if tone in ("soft", "romantic", "suggestive", "roleplay"):
        stage = 1
    if tone in ("romantic", "suggestive", "roleplay") and affection_mode == "romantic":
        stage = 2

    # соберём пул кандидатов
    variants = generate_name_variants(base)
    pool = [base] if stage == 0 or not variants else variants

    # нежные — только при stage 2
    if stage >= 2:
        # чем выше близость — тем чаще может «случиться» нежное слово
        p_pet = 0.10 + max(0, min(0.25, 0.02 * max(0, affinity)))
        if random() < p_pet:
            pet_pool = PETNAMES_ROMANTIC if tone in ("romantic", "suggestive", "roleplay") else PETNAMES_SOFT
            pool = pool + pet_pool

    return choice(pool)

    # Без прозвищ и уменьшительных, строго по имени
    return base

def should_use_address(length: str, tone: str, affinity: int = 0) -> bool:
    """
    Вероятность использовать обращение: немного зависящая от длины, тона и близости,
    чтобы речь не выглядела «скриптовой».
    """
    # База по длине
    if length == "one":
        p = 0.15
    elif length == "long":
        p = 0.75
    else:
        p = 0.55  # "short"/"medium"

    # Чуть чаще в романтических режимах
    if tone in ("romantic", "suggestive"):
        p += 0.08
    elif tone == "roleplay":
        p += 0.05

    # Чуть чаще при высокой близости
    if affinity >= 8:
        p += 0.07
    elif affinity <= -2:
        p -= 0.10

    # Жёсткие границы
    p = max(0.05, min(0.90, p))
    return random() < p
