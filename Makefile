.PHONY: check verify quick lint format type mypy pyright arch test coverage help

help:
	@echo "Iris verification targets:"
	@echo "  make check    - run full repository verification"
	@echo "  make verify   - alias for make check"
	@echo "  make quick    - run lint, format, type, and architecture checks"
	@echo "  make lint     - run ruff lint"
	@echo "  make format   - run ruff format check"
	@echo "  make type     - run mypy and pyright over production code"
	@echo "  make mypy     - run mypy on production code"
	@echo "  make pyright  - run pyright on iris"
	@echo "  make arch     - run architecture tests"
	@echo "  make test     - run all tests"
	@echo "  make coverage - run tests with coverage report"

check:
	uv run python scripts/verify.py

verify: check

quick:
	uv run python scripts/verify.py --quick

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

type: mypy pyright

mypy:
	uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime iris/errors.py

pyright:
	uv run pyright .

arch:
	uv run pytest tests/architecture -q

test:
	uv run pytest tests/ -q

coverage:
	uv run pytest tests/ --cov=iris --cov-report=term-missing --cov-report=html
