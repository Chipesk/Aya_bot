# services/world_state.py
import json
import logging
import httpx
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from core.settings import settings

log = logging.getLogger("world")

SPB_LAT, SPB_LON = 59.9386, 30.3141  # Санкт-Петербург
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

class WorldState:
    def __init__(self, db):
        self.db = db

    async def _fetch_weather(self) -> dict:
        params = {
            "latitude": SPB_LAT,
            "longitude": SPB_LON,
            "current_weather": True,
            "hourly": "precipitation,temperature_2m",
            "timezone": settings.AYA_TZ,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            return r.json()

    async def get_context(self) -> dict:
        """
        Возвращает dict с ключами:
        - city, tz, local_time_iso
        - weather: {temp_c, wind, code, is_rainy}
        Кэширует в world_state не дольше 30 минут.
        """
        # попытка взять последнее состояние
        cur = await self.db.conn.execute("SELECT payload, created_at FROM world_state ORDER BY id DESC LIMIT 1")
        row = await cur.fetchone()
        now_utc = datetime.now(timezone.utc)

        if row:
            payload, created_at = row[0], row[1]
            created = datetime.fromisoformat(created_at.replace(" ", "T"))
            age_min = (now_utc - created.replace(tzinfo=timezone.utc)).total_seconds() / 60
            if age_min <= 30:
                return json.loads(payload)

        # иначе — свежий запрос
        js = await self._fetch_weather()
        cw = js.get("current_weather", {}) or {}
        temp_c = cw.get("temperature")
        wind = cw.get("windspeed")
        code = cw.get("weathercode")

        # грубая эвристика осадков
        is_rainy = False
        try:
            hourly = js.get("hourly", {})
            precip = hourly.get("precipitation", [0])
            is_rainy = (precip[0] or 0) > 0
        except Exception:
            pass

        local_time = datetime.now(ZoneInfo(settings.AYA_TZ))
        context = {
            "city": settings.AYA_CITY,
            "tz": settings.AYA_TZ,
            "local_time_iso": local_time.isoformat(timespec="minutes"),
            "weather": {
                "temp_c": temp_c,
                "wind": wind,
                "code": code,
                "is_rainy": bool(is_rainy),
            },
        }

        await self.db.conn.execute(
            "INSERT INTO world_state (city, tz, payload) VALUES (?, ?, ?)",
            (settings.AYA_CITY, settings.AYA_TZ, json.dumps(context)),
        )
        await self.db.conn.commit()
        return context
