# orchestrator/weather_gate.py
from time import time

class WeatherGate:
    def __init__(self):
        self._last_spoke_ts = 0.0
        self._session_flag = False

    def allow(self, user_text: str) -> bool:
        txt = (user_text or "").lower()
        user_mentions = any(w in txt for w in ("погод","дожд","солн","ветер","снег","лив"))
        if not user_mentions:
            return False
        if self._session_flag:
            return False
        self._session_flag = True
        self._last_spoke_ts = time()
        return True

WEATHER_GATE = WeatherGate()
