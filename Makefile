.PHONY: venv lint typecheck test run-dev

venv:
python -m venv .venv

lint:
ruff check .

format:
black .
isort .

typecheck:
mypy --strict .

test:
pytest

run-dev:
ENV=dev TELEGRAM_TOKEN="" DIAG=1 python main.py
