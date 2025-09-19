# orchestrator/weather_gate.py
from time import time

from time import time


class WeatherGate:
    def __init__(self, ttl: int = 900):
        self._last_spoke_ts = 0.0
        self._session_flag = False
        self._ttl = ttl

    def allow(self, user_text: str) -> bool:
        now = time()
        if self._session_flag and (now - self._last_spoke_ts) > self._ttl:
            self._session_flag = False
        txt = (user_text or "").lower()
        user_mentions = any(w in txt for w in ("погод", "дожд", "солн", "ветер", "снег", "лив"))
        if not user_mentions:
            return False
        if self._session_flag:
            return False
        self._session_flag = True
        self._last_spoke_ts = now
        return True


WEATHER_GATE = WeatherGate()
