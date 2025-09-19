import pytest
# mypy: ignore-errors
from datetime import datetime


@pytest.mark.asyncio
async def test_weather_response(make_brain) -> None:
    now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    brain = await make_brain({"weather": {"temp_c": 5, "is_rainy": True}, "local_time_iso": now.isoformat()})
    reply = await brain.respond(7, "Какая погода сегодня?")
    assert "пог" in reply.text.lower()


@pytest.mark.asyncio
async def test_time_response(make_brain) -> None:
    now = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
    brain = await make_brain({"local_time_iso": now.isoformat()})
    reply = await brain.respond(8, "Который час?")
    assert "15" in reply.text or "время" in reply.text.lower()
