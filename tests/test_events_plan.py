import pytest
# mypy: ignore-errors


@pytest.mark.asyncio
async def test_rainy_weather_affects_plan(make_brain) -> None:
    brain = await make_brain({"weather": {"temp_c": 4, "is_rainy": True}})
    reply = await brain.respond(60, "Что делать вечером?")
    assert "rainy_day" in reply.plan.get("applied_rules", [])
    assert "дожд" in reply.text.lower()
