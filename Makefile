.PHONY: check verify quick ai-check ai-quick ai-context ai-report ai-arch ai-test-target e2e lint lint-fix format format-write type pyright arch imports semgrep static-arch test coverage deps doctor ci generate-protos help

DEFAULT_TEST_TARGETS := tests/adapters tests/architecture tests/cognitive tests/contracts tests/core tests/features tests/presentation tests/runtime tests/scripts tests/test_oneturn_flow.py

help:
	@echo "Iris strict AI-coding verification targets:"
	@echo "  make check        - run full strict repository verification with coverage"
	@echo "  make verify       - alias for make check"
	@echo "  make quick        - run lint, format, mypy, pyright, and architecture checks without coverage"
	@echo "  make ai-check     - run full AI harness gate and keep going after failures"
	@echo "  make ai-quick     - run fast AI harness gate and keep going after failures"
	@echo "  make ai-context   - print AI harness context, workflows, checklists, skills, and commands"
	@echo "  make ai-report    - print git-aware completion report skeleton"
	@echo "  make ai-arch      - run architecture guard tests"
	@echo "  make ai-skills    - list available on-demand skills"
	@echo "  make ai-skill SKILL=<name> - display a specific skill (e.g. architecture-review)"
	@echo "  make ai-test-target TARGET=tests/path.py::test_name - run focused tests without coverage"
	@echo "  make lint         - run ruff lint with strict ALL-rule config"
	@echo "  make lint-fix     - run ruff lint autofix after inspecting expected diff"
	@echo "  make format       - run ruff format check"
	@echo "  make format-write - apply ruff format after inspecting target files"
	@echo "  make type         - run mypy with core-max strictness and scoped adapter/test/script policy"
	@echo "  make pyright      - run pyright production-strict and tests/scripts-standard checks"
	@echo "  make arch         - run architecture tests"
	@echo "  make test         - run default non-E2E tests without coverage"
	@echo "  make e2e          - run process-level E2E tests without live LLM provider"
	@echo "  make coverage     - run coverage gate and HTML report"
	@echo "  make generate-protos - regenerate protobuf and gRPC code from proto definitions"
	@echo "  make deps         - sync project dependencies with uv"
	@echo "  make doctor       - print local tool versions"
	@echo "  make ci           - sync dependencies and run make check"

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

ai-skills:
	@echo "Available skills:"
	@for skill_dir in $$(ls .agents/skills/ | sort); do \
		name=$$(basename $$skill_dir); \
		desc=$$(sed -n '2,/^---$$/{s/^description: //p;}' .agents/skills/$$name/SKILL.md 2>/dev/null | head -n 1); \
		printf "  %-24s %s\n" "$$name" "$$desc"; \
	done

ai-skill:
	@test -n "$(SKILL)" || (echo "SKILL is required, e.g. make ai-skill SKILL=architecture-review" && exit 2)
	@test -f .agents/skills/$(SKILL)/SKILL.md || (echo "Skill '$(SKILL)' not found" && exit 2)
	@cat .agents/skills/$(SKILL)/SKILL.md

ai-test-target:
	@test -n "$(TARGET)" || (echo "TARGET is required, e.g. make ai-test-target TARGET=tests/runtime/test_no_action_flow.py::test_no_action_skips_presenter" && exit 2)
	uv run pytest $(TARGET) -q

e2e:
	uv run pytest tests/e2e -m "e2e and not llm_live"

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

imports:
	uv run lint-imports

semgrep:
	uv run semgrep scan --config semgrep.yml --error

static-arch: imports semgrep arch

test:
	uv run pytest $(DEFAULT_TEST_TARGETS)

coverage:
	uv run pytest $(DEFAULT_TEST_TARGETS) --cov=iris --cov-branch --cov-report=term-missing:skip-covered --cov-report=html --cov-fail-under=90

deps:
	uv sync --all-groups

generate-protos:
	uv run python scripts/generate_protos.py

doctor:
	uv --version
	uv run python --version
	uv run ruff --version
	uv run mypy --version
	uv run pyright --version
	uv run pytest --version

ci: deps check
