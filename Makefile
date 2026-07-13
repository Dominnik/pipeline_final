.PHONY: install run test lint format-check check

install:
	python3 -m pip install -r requirements.txt -r requirements-dev.txt

run:
	uvicorn app.main:app --reload

test:
	pytest

lint:
	ruff check .

format-check:
	ruff format --check .

check: lint format-check test
	python3 -m compileall app
