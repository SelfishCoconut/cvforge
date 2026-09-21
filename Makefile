.PHONY: lint format typecheck complexity test test-unit test-integration test-golden \
        update-golden test-demos sanity docs docs-serve build-ui dev-ui ui-install \
        ui-lint ui-test run demo-health clean

# --- python quality ---
lint:
	uv run ruff check src tests scripts .claude/hooks
	uv run ruff format --check src tests scripts .claude/hooks

format:
	uv run ruff format src tests scripts .claude/hooks
	uv run ruff check --fix src tests scripts .claude/hooks

typecheck:
	uv run mypy

complexity:
	uv run xenon --max-absolute C --max-modules B --max-average A src .claude/hooks

# --- tests ---
test-unit:
	uv run pytest -m "not integration and not golden and not system" --cov --cov-report=term-missing

test-integration:
	uv run pytest -m integration --no-cov

test-golden:
	uv run pytest -m golden --no-cov

test: test-unit test-integration test-golden

# Regenerate golden snapshots, then REVIEW THE DIFF — that review is the gate.
update-golden:
	uv run pytest -m golden --no-cov --update-golden

# --- runnable proof of each feature (PR template's "How to validate") ---
demo-health:
	uv run python scripts/demo/health.py

test-demos: demo-health
	@echo "all offline demos ran clean"

# --- mechanical quality signals ---
sanity:
	-uv run radon cc -s -a src
	-uv run vulture src --min-confidence 80
	-uv run pylint --disable=all --enable=duplicate-code src

# --- docs ---
docs:
	uv run mkdocs build --strict

docs-serve:
	uv run mkdocs serve

# --- frontend ---
ui-install:
	npm --prefix frontend ci

ui-lint:
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck

ui-test:
	npm --prefix frontend run test:coverage

build-ui:
	npm --prefix frontend ci
	npm --prefix frontend run build

dev-ui:
	npm --prefix frontend run dev

# --- run ---
run:
	uv run uvicorn --factory cvforge.app:create_app --host 127.0.0.1 --port 8000

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov site coverage.xml .coverage
	rm -rf frontend/dist frontend/node_modules
