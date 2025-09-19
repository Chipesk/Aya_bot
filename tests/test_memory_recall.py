import pytest
# mypy: ignore-errors


@pytest.mark.asyncio
async def test_memory_recall(memory_stack) -> None:
    memory_repo, chat_history, facts_repo, memory_manager = memory_stack
    await memory_manager.store_user_message(42, "меня зовут Алексей")
    await memory_manager.store_user_message(42, "мне 31")
    await memory_manager.store_user_message(42, "у меня непереносимость арахиса")
    facts = await memory_manager.recall(42, "identity", limit=2)
    assert any(f.predicate == "name" for f in facts)
    facts_health = await memory_manager.recall(42, "health", limit=1)
    assert facts_health[0].predicate == "intolerance"
