import pytest
# mypy: ignore-errors


@pytest.mark.asyncio
async def test_brain_basic_response(brain) -> None:
    reply = await brain.respond(100, "Привет")
    assert reply.text
    assert "applied_rules" in reply.plan
