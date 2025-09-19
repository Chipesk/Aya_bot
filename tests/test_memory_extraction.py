import pytest
# mypy: ignore-errors


@pytest.mark.asyncio
async def test_memory_extraction(memory_stack) -> None:
    memory_repo, chat_history, facts_repo, memory_manager = memory_stack
    await memory_manager.store_user_message(1, "мне 33 и у меня непереносимость лактозы")
    await memory_manager.store_user_message(1, "живу в калуге")
    stored = await facts_repo.get_all(1, limit=10)
    predicates = {row["predicate"] for row in stored}
    assert {"age", "intolerance", "location"}.issubset(predicates)
    ages = [row for row in stored if row["predicate"] == "age"]
    assert ages[0]["object"] == "33"
