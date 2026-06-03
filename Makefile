.PHONY: check verify quick lint format type arch test help

help:
	@echo "Iris verification targets:"
	@echo "  make check   - run full repository verification"
	@echo "  make verify  - alias for make check"
	@echo "  make quick   - run lint, format, type, and architecture checks"
	@echo "  make lint    - run ruff lint"
	@echo "  make format  - run ruff format check"
	@echo "  make type    - run mypy on production packages"
	@echo "  make arch    - run architecture tests"
	@echo "  make test    - run all tests"

check:
	uv run python scripts/verify.py

verify: check

quick:
	uv run python scripts/verify.py --quick

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

type:
	uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime

arch:
	uv run pytest tests/architecture -q

test:
	uv run pytest tests/ -q
