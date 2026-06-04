.PHONY: check verify quick ai-check ai-quick ai-context ai-report ai-arch ai-test-target lint lint-fix format format-write type pyright arch test coverage help

help:
	@echo "Iris strict AI-coding verification targets:"
	@echo "  make check        - run full strict repository verification with coverage"
	@echo "  make verify       - alias for make check"
	@echo "  make quick        - run lint, format, mypy, pyright, and architecture checks without coverage"
	@echo "  make ai-check     - run full AI harness gate and keep going after failures"
	@echo "  make ai-quick     - run fast AI harness gate and keep going after failures"
	@echo "  make ai-context   - print AI harness context, workflows, and commands"
	@echo "  make ai-report    - print git-aware completion report skeleton"
	@echo "  make ai-arch      - run architecture guard tests"
	@echo "  make ai-test-target TARGET=tests/path - run focused tests without coverage"
	@echo "  make lint         - run ruff lint with strict ALL-rule config"
	@echo "  make lint-fix     - run ruff lint autofix"
	@echo "  make format       - run ruff format check"
	@echo "  make format-write - apply ruff format"
	@echo "  make type         - run mypy strict across iris/tests/scripts/main.py"
	@echo "  make pyright      - run pyright production-strict and tests/scripts-standard checks"
	@echo "  make arch         - run architecture tests"
	@echo "  make test         - run all tests without coverage"
	@echo "  make coverage     - run coverage gate and HTML report"

check:
	uv run python scripts/verify.py

verify: check

quick:
	uv run python scripts/verify.py --quick

ai-check:
	uv run python scripts/verify.py --keep-going

ai-quick:
	uv run python scripts/verify.py --quick --keep-going

ai-context:
	uv run python scripts/ai_context.py

ai-report:
	uv run python scripts/ai_report.py

ai-arch:
	uv run pytest tests/architecture -q

ai-test-target:
	@test -n "$(TARGET)" || (echo "TARGET is required, e.g. make ai-test-target TARGET=tests/runtime/test_no_action_flow.py" && exit 2)
	uv run pytest $(TARGET) -q

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

format:
	uv run ruff format --check .

format-write:
	uv run ruff format .

type:
	uv run mypy iris tests scripts main.py

pyright:
	uv run pyright .

arch:
	uv run pytest tests/architecture -q

test:
	uv run pytest tests/

coverage:
	uv run pytest tests/ --cov=iris --cov-branch --cov-report=term-missing:skip-covered --cov-report=html --cov-fail-under=90
