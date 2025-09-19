"""Wrapper for world state access."""
# mypy: ignore-errors
from __future__ import annotations

from typing import Dict

from services.world_state import WorldState as _WorldState


class WorldStateService:
    def __init__(self, backend: _WorldState) -> None:
        self._backend = backend

    async def snapshot(self) -> Dict[str, object]:
        return await self._backend.get_context()

    async def weather_condition(self) -> str:
        world = await self.snapshot()
        weather = (world or {}).get("weather") or {}
        if weather.get("is_rainy"):
            return "rainy"
        if weather.get("temp_c") is not None and weather.get("temp_c") <= 0:
            return "cold"
        return "clear"
