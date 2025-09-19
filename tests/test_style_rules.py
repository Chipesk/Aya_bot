import pytest
# mypy: ignore-errors


@pytest.mark.asyncio
async def test_style_variation(brain) -> None:
    texts = set()
    for _ in range(5):
        texts.add((await brain.respond(70, "просто поговорим")).text)
    assert len(texts) >= 2
    for text in texts:
        assert "запрещ" not in text.lower()
