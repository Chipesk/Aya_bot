import pytest
# mypy: ignore-errors


@pytest.mark.asyncio
async def test_memory_roundtrip(brain) -> None:
    await brain.respond(90, "меня зовут Сергей")
    await brain.respond(90, "мне 33")
    await brain.respond(90, "у меня непереносимость лактозы")
    response = await brain.respond(90, "что ты помнишь обо мне?")
    assert "33" in response.text or "лактоз" in response.text.lower()
    metrics = brain.memory_manager.snapshot_metrics()
    assert metrics.facts_stored >= 2
    assert metrics.recall_hit_rate >= 0.0
