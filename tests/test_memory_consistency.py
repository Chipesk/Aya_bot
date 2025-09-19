import asyncio
import pytest
# mypy: ignore-errors


@pytest.mark.asyncio
async def test_memory_consistency(memory_stack) -> None:
    memory_repo, chat_history, facts_repo, memory_manager = memory_stack
    await memory_manager.store_user_message(1, "мне 30")
    await asyncio.sleep(0.01)
    await memory_manager.store_user_message(1, "мне 31")
    facts = await memory_manager.recall(1, "age", limit=1)
    assert facts[0].object == "31"
