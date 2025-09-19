import pytest
# mypy: ignore-errors


@pytest.mark.asyncio
async def test_flirt_requires_adult(brain) -> None:
    reply = await brain.respond(50, "Давай пофлиртуем")
    assert any("no_flirt_without_consent" in rule for rule in reply.plan.get("applied_rules", []))


@pytest.mark.asyncio
async def test_flirt_after_consent(brain) -> None:
    await brain.memory_repo.set_adult_confirmed(51, True)
    await brain.memory_repo.set_affinity(51, 5)
    reply = await brain.respond(51, "добавь романтики")
    assert "flirt_soften" in reply.plan.get("applied_rules", [])
