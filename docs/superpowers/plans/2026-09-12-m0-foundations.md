# CVForge M0 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the CVForge repository end to end — toolchain, quality gates, CI/CD, documentation site, requirements catalogue, Claude Code toolkit, and a running FastAPI + React walking skeleton — so that M1 can be built entirely through the normal issue → branch → PR → green-CI workflow.

**Architecture:** One `uv`-managed Python package (`src/cvforge/`) exposing a FastAPI app under `/api` and serving a built React SPA at `/` from a single uvicorn process. No database, no LLM, no agents in M0 — those are M1. M0's deliverable is the *machinery that will refuse to let M1 regress*: a 90% line+branch coverage gate, a golden-snapshot harness, a security pipeline, and a `.claude` toolkit encoding the project's invariants.

**Tech Stack:** Python 3.13 (`uv`), FastAPI, uvicorn, Pydantic + pydantic-settings, pytest + pytest-cov, ruff, mypy strict, xenon; React 19 + TypeScript + Vite + Tailwind v4 + vitest; MkDocs Material + mkdocstrings; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-12-cvforge-design.md`

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include this section.

- **Python 3.13** pinned via `.python-version`; `requires-python = ">=3.13"`. All tools run through `uv run` or `make`.
- **Ruff** lint + format, **line length 100**, **Google-style docstrings** on public API.
- **`mypy --strict`** must pass over `src`, `tests`, `scripts`.
- **Complexity gate:** `xenon --max-absolute C --max-modules B --max-average A src`. Refactor, never suppress.
- **Coverage: ≥90% line AND branch on `src/`**, enforced by `fail_under = 90` + `branch = true`. Hard CI failure below.
- **No live model calls in unit, integration or golden tests.** Ever.
- **No test may be skipped or xfailed without an issue reference.**
- **Binds `127.0.0.1` only.** No authentication — single-user local tool, by design.
- **`data/`, `*.db`, `cv_out/` are gitignored.** Every fixture is synthetic. Never commit a real CV, job posting, or knowledge-base export.
- **Conventional Commits**, enforced by a commit-msg hook: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`.
- **Every AI-assisted commit ends with:** `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
- **Repo:** public, `SelfishCoconut/cvforge`. **No Kanban board automation** (spec D9) — do not create `board.yml`.
- **No auto-generated UML** in the docs site (spec D7) — do not add pyreverse or `gen_uml.py`.
- Frontend is **React 19 + TypeScript + Vite + Tailwind v4**. **No shadcn/ui** (spec D14).

### Bootstrap exception to the issue-first rule

The project's standing rule is issue-first: no code without a GitHub issue. M0 is
the task that *creates* the issue tracker, so it cannot follow its own rule. M0
commits directly to `main`. Task 2 opens a single `infra` issue covering M0 for
the record; Task 12 enables branch protection, after which the rule binds for
every subsequent change.

---

## File Structure

Files created in M0, and what each owns.

**Toolchain and package**
| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, runtime and dev dependencies, and the configuration for ruff, mypy, pytest and coverage |
| `.python-version` | Pins the interpreter (`3.13`) so local and CI resolve identically |
| `LICENSE` | AGPL-3.0 text |
| `Makefile` | Every command a human or CI job runs — the single place commands are defined |
| `.pre-commit-config.yaml` | Local commit-time gates: whitespace, large files, private keys, ruff, gitleaks, Conventional Commits |
| `.gitignore` | **Already committed** before this plan — verify `data/`, `*.db` and `cv_out/` are the first entries before Task 2 makes the repo public |
| `src/cvforge/__init__.py` | Package version (`__version__`), nothing else |
| `src/cvforge/config.py` | `Settings` — process configuration from env with defaults; no DB yet |
| `src/cvforge/app.py` | `create_app()` factory; mounts the API router and, when built, the SPA |
| `src/cvforge/api/__init__.py` | Marks the router package |
| `src/cvforge/api/health.py` | `/api/health` router — the only endpoint in M0 |
| `scripts/demo/health.py` | Runnable proof of the walking skeleton (the PR template's validation artifact) |

**Tests**
| Path | Responsibility |
|---|---|
| `tests/conftest.py` | `--update-golden` option, the `golden` fixture, the shared `client` fixture |
| `tests/unit/test_version.py` | Package exposes a version |
| `tests/unit/test_config.py` | Settings defaults and env overrides |
| `tests/unit/test_health.py` | `/api/health` contract |
| `tests/unit/test_spa_mount.py` | SPA mount is conditional on a built `index.html` |
| `tests/integration/test_app_wiring.py` | Real app assembled against a real on-disk dist directory |
| `tests/golden/test_openapi_snapshot.py` | OpenAPI schema snapshot — the API contract regression gate |
| `tests/golden/snapshots/openapi.json` | The committed snapshot |

**Frontend**
| Path | Responsibility |
|---|---|
| `frontend/package.json` | Frontend dependencies and scripts (`dev`, `build`, `lint`, `typecheck`, `test`) |
| `frontend/vite.config.ts` | React + Tailwind v4 plugins, `/api` dev proxy, vitest config |
| `frontend/tsconfig.json` | TypeScript strict configuration |
| `frontend/eslint.config.js` | Flat-config ESLint for TS + React |
| `frontend/index.html` | SPA entry document |
| `frontend/src/main.tsx` | React root |
| `frontend/src/index.css` | Tailwind v4 import and design tokens |
| `frontend/src/App.tsx` | Shell: header plus a live backend-health indicator |
| `frontend/src/api.ts` | Typed `fetchHealth()` — the one API call in M0 |
| `frontend/src/App.test.tsx` | Renders the shell and asserts the health state |

**CI/CD and GitHub**
| Path | Responsibility |
|---|---|
| `.github/workflows/ci.yml` | Required-for-merge gates: quality, unit+coverage, integration, golden, demos, docs, frontend |
| `.github/workflows/security.yml` | pip-audit, bandit, gitleaks, CodeQL |
| `.github/workflows/sanity.yml` | Weekly complexity / dead-code / duplication report |
| `.github/dependabot.yml` | Weekly pip, npm and github-actions updates |
| `.github/ISSUE_TEMPLATE/feature.yml` | Requirement-bound work item |
| `.github/ISSUE_TEMPLATE/bug.yml` | Defect report |
| `.github/ISSUE_TEMPLATE/infra.yml` | Tooling/CI work item with no FR |
| `.github/PULL_REQUEST_TEMPLATE.md` | Mandatory "How to validate" + self-review checklist |

**Documentation**
| Path | Responsibility |
|---|---|
| `mkdocs.yml` | Site configuration and navigation |
| `README.md` | What CVForge is, how to run it, the invariants |
| `docs/index.md` | Docs site landing page |
| `docs/requirements/srs.md` | The requirements catalogue — authority on *what* |
| `docs/architecture/overview.md` | C4 context and container diagrams (Mermaid) |
| `docs/architecture/knowledge-model.md` | Entity/edge/provenance diagram and the write-path rule |
| `docs/adr/README.md` | ADR index |
| `docs/adr/0001-sqlite-knowledge-store.md` | Why SQLite with an edge table |
| `docs/adr/0002-single-process-api-and-spa.md` | Why one uvicorn process serves both |
| `docs/adr/0003-changeset-review-pipeline.md` | Why agents propose and never write |
| `docs/reference/api.md` | mkdocstrings-generated API reference |

**Claude Code toolkit** (`.claude/`)
| Path | Responsibility |
|---|---|
| `settings.json` | Enabled plugins and hook registrations |
| `skills/requirements/SKILL.md` | SRS management and FR↔issue traceability (ported) |
| `skills/feature-request/SKILL.md` | Request → labelled issue → branch (ported, de-Kanban'd) |
| `skills/adr/SKILL.md` | MADR authoring (ported) |
| `skills/docs/SKILL.md` | Docs site build and placement rules (ported, UML removed) |
| `skills/progress-report/SKILL.md` | Status write-up from git and gh (ported) |
| `skills/run/SKILL.md` | How to run CVForge locally (rewritten) |
| `skills/kb-schema/SKILL.md` | Changing the knowledge schema without breaking the invariants (new) |
| `skills/llm-agent/SKILL.md` | Adding a Pydantic AI agent (new) |
| `skills/golden-tests/SKILL.md` | Recording, reviewing and updating snapshots (new) |
| `skills/cv-template/SKILL.md` | LaTeX template and rendering conventions (new) |
| `skills/release/SKILL.md` | Milestone close-out (new) |
| `agents/codebase-sanity.md` | Whole-repo longitudinal quality audit (ported) |
| `agents/doc-curator.md` | Per-PR documentation health (ported, UML removed) |
| `agents/regression-guard.md` | Per-PR test-adequacy review (new) |
| `agents/provenance-auditor.md` | Knowledge-base invariant audit (new) |
| `hooks/remind-issue.sh` | Reminds on branch/PR creation that work traces to an issue (ported) |
| `hooks/format-on-edit.sh` | Formats touched Python and TypeScript files (ported, extended) |
| `hooks/guard-private-data.sh` | Blocks writes that would commit personal data (new) |
| `hooks/kb-write-path.sh` | Warns on a DB write added outside `kb/apply.py` (new) |

---

## Task 1: Python toolchain and package skeleton

Creates the project file, pins the interpreter, configures every quality tool, and
proves the package imports. Configuration is not behaviour, so it precedes the
first test; everything after this task is strict TDD.

**Files:**
- Create: `pyproject.toml`, `.python-version`, `LICENSE`, `Makefile`, `.pre-commit-config.yaml`
- Create: `src/cvforge/__init__.py`
- Test: `tests/unit/test_version.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: the package `cvforge` with `__version__: str`; `make lint`, `make format`, `make typecheck`, `make test-unit`, `make test`, `make sanity`, `make clean`.

- [ ] **Step 1: Pin the interpreter**

```bash
cd /home/alvar/repos/cvforge
echo "3.13" > .python-version
```

- [ ] **Step 2: Write `pyproject.toml`**

Runtime dependencies are deliberately minimal — SQLAlchemy, Pydantic AI, Playwright
and the document parsers arrive in the milestone that first uses them, so that
`vulture` and `pip-audit` never report on code that does not exist yet.

```toml
[project]
name = "cvforge"
version = "0.1.0"
description = "Local-first personal professional knowledge system that generates tailored CVs"
readme = "README.md"
license = "AGPL-3.0-or-later"
license-files = ["LICENSE"]
authors = [{ name = "Álvaro Navarro", email = "182025519+SelfishCoconut@users.noreply.github.com" }]
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.115",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "uvicorn>=0.32",
]

[dependency-groups]
dev = [
    "ruff>=0.8",
    "mypy>=1.13",
    "pytest>=8.3",
    "pytest-cov>=6.0",
    # Starlette's TestClient needs httpx as its transport.
    "httpx>=0.27",
    "pre-commit>=4.0",
    # Mechanical quality signals consumed by sanity.yml and the codebase-sanity agent.
    "radon>=6.0",
    "xenon>=0.9",
    "vulture>=2.13",
    "pylint>=3.3",
    # Documentation site.
    "mkdocs-material>=9.5",
    "mkdocstrings[python]>=0.27",
    "mkdocs-mermaid2-plugin>=1.2",
]

[build-system]
requires = ["uv_build>=0.5,<1"]
build-backend = "uv_build"

# ---------------------------------------------------------------- ruff
[tool.ruff]
target-version = "py313"
line-length = 100
src = ["src", "tests", "scripts"]

[tool.ruff.lint]
select = [
    "E", "W",    # pycodestyle
    "F",         # pyflakes
    "I",         # isort
    "B",         # bugbear
    "UP",        # pyupgrade
    "S",         # bandit — this tool fetches untrusted web pages and shells out to LaTeX
    "C90",       # mccabe complexity
    "N",         # naming
    "D",         # pydocstyle — docstrings render into the docs site
    "RUF",
]
ignore = ["D203", "D213"]  # incompatible docstring-style pairs; D211/D212 are used instead

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "D"]  # asserts are the point; docstrings optional in tests

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.mccabe]
max-complexity = 10

# ---------------------------------------------------------------- mypy
[tool.mypy]
python_version = "3.13"
strict = true
# `scripts` is in scope on purpose: scripts/demo/* is the PR template's mandatory
# "How to validate" artifact, so it is load-bearing process infrastructure.
files = ["src", "tests", "scripts"]
pretty = true

# ---------------------------------------------------------------- pytest
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "--strict-markers"
markers = [
    "integration: real component wiring and real I/O (CI: separate job)",
    "golden: snapshot comparison against committed golden files (CI: separate job)",
    "system: full end-to-end against a browser or external service (CI: nightly only)",
]

# ---------------------------------------------------------------- coverage
[tool.coverage.run]
source = ["src/cvforge"]
branch = true

[tool.coverage.report]
fail_under = 90
show_missing = true
exclude_also = ["if TYPE_CHECKING:", "raise NotImplementedError"]
```

- [ ] **Step 3: Fetch the licence text**

```bash
gh api /licenses/agpl-3.0 --jq .body > LICENSE
head -2 LICENSE
```

Expected: the first lines of the GNU AGPL v3.

- [ ] **Step 4: Write the `Makefile`**

Tabs, not spaces, for the recipe lines.

```make
.PHONY: lint format typecheck complexity test test-unit test-integration test-golden \
        update-golden test-demos sanity docs docs-serve build-ui dev-ui ui-install \
        ui-lint ui-test run demo-health clean

# --- python quality ---
lint:
	uv run ruff check src tests scripts
	uv run ruff format --check src tests scripts

format:
	uv run ruff format src tests scripts
	uv run ruff check --fix src tests scripts

typecheck:
	uv run mypy

complexity:
	uv run xenon --max-absolute C --max-modules B --max-average A src

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
```

- [ ] **Step 5: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: check-merge-conflict
      - id: check-yaml
        exclude: ^mkdocs\.yml$  # uses mkdocs-material's python-specific YAML tags
      - id: check-toml
      - id: detect-private-key

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks

  - repo: https://github.com/compilerla/conventional-pre-commit
    rev: v3.6.0
    hooks:
      - id: conventional-pre-commit
        stages: [commit-msg]
```

- [ ] **Step 6: Create the environment**

```bash
uv sync
uv run pre-commit install --install-hooks
uv run pre-commit install --hook-type commit-msg
```

Expected: a `.venv/` with Python 3.13 and `uv.lock` written.

- [ ] **Step 7: Write the failing test**

```python
# tests/unit/test_version.py
"""The package exposes a version string."""

import cvforge


def test_package_exposes_a_semver_version() -> None:
    assert cvforge.__version__.count(".") == 2
    assert all(part.isdigit() for part in cvforge.__version__.split("."))
```

- [ ] **Step 8: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_version.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'cvforge'`.

- [ ] **Step 9: Write the minimal implementation**

```python
# src/cvforge/__init__.py
"""CVForge — a local-first personal professional knowledge system."""

__version__ = "0.1.0"
```

- [ ] **Step 10: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_version.py -v --no-cov`
Expected: PASS.

- [ ] **Step 11: Verify the whole toolchain runs**

```bash
make lint && make typecheck && make complexity
```

Expected: all three clean. If ruff reports a missing docstring, add it — do not
add an ignore.

- [ ] **Step 12: Commit**

```bash
git add pyproject.toml .python-version LICENSE Makefile .pre-commit-config.yaml \
        uv.lock src/cvforge/__init__.py tests/unit/test_version.py
git commit -m "chore: python toolchain, quality gates and package skeleton

uv-managed Python 3.13 package with ruff, mypy --strict, xenon complexity
gate, pytest with branch coverage at a 90% floor, and pre-commit hooks
including Conventional Commits and gitleaks.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Public GitHub repository, labels and milestones

Creates the remote early so every later task can push and watch CI come alive,
and registers the label and milestone vocabulary the `feature-request` skill and
the SRS both depend on.

**Files:** none (remote state only).

**Interfaces:**
- Consumes: the committed `main` branch from Task 1.
- Produces: remote `origin` → `https://github.com/SelfishCoconut/cvforge`; labels `feature`, `bug`, `infra`, `req:nonfunctional`, and `req:FR-01`…`req:FR-40`; milestones `M0`…`M8`; issue #1 covering the M0 bootstrap.

- [ ] **Step 1: Create the public repository and push**

```bash
cd /home/alvar/repos/cvforge
gh repo create cvforge --public \
  --description "Local-first personal professional knowledge system that generates tailored, evidence-backed CVs" \
  --source . --remote origin --push
gh repo view --json nameWithOwner,visibility --jq '.'
```

Expected: `{"nameWithOwner":"SelfishCoconut/cvforge","visibility":"PUBLIC"}`.

- [ ] **Step 2: Create the milestones**

```bash
for m in \
  "M0 Foundations" \
  "M1 Knowledge spine" \
  "M2 Document ingestion" \
  "M3 Job intake" \
  "M4 Match and gaps" \
  "M5 CV generation" \
  "M6 Collaborative mode" \
  "M7 Learning plans" \
  "M8 Form autofill"
do
  gh api repos/:owner/:repo/milestones -f title="$m" --silent || echo "exists: $m"
done
gh api repos/:owner/:repo/milestones --jq '.[].title'
```

Expected: the nine titles listed.

- [ ] **Step 3: Create the labels**

```bash
gh label create feature --color 1d76db --description "Implements part of a requirement" --force
gh label create bug --color d73a4a --description "Something behaves incorrectly" --force
gh label create infra --color 5319e7 --description "Tooling, CI, build, dev environment" --force
gh label create tech-debt --color fbca04 --description "Cleanup surfaced by codebase-sanity" --force
gh label create req:nonfunctional --color 0e8a16 --description "Traces to an NFR" --force
for n in $(seq -w 1 40); do
  gh label create "req:FR-$n" --color c2e0c6 --description "Traces to FR-$n" --force
done
gh label list --limit 60 | head -20
```

Expected: 45 labels exist (`feature`, `bug`, `infra`, `tech-debt`,
`req:nonfunctional`, and `req:FR-01` through `req:FR-40`).

- [ ] **Step 4: Open the bootstrap issue for the record**

```bash
gh issue create --title "infra: M0 foundations bootstrap" --label infra \
  --milestone "M0 Foundations" --body "$(cat <<'BODY'
### Description
Stand up the repository: toolchain, quality gates, CI/CD, security pipeline,
documentation site, requirements catalogue, `.claude` toolkit, and the
FastAPI + React walking skeleton.

Plan: `docs/superpowers/plans/2026-09-12-m0-foundations.md`
Spec: `docs/superpowers/specs/2026-09-12-cvforge-design.md`

### Acceptance criteria
- [ ] `make lint typecheck complexity test` clean locally
- [ ] `make build-ui && make run` serves the SPA at http://127.0.0.1:8000 and `/api/health` returns ok
- [ ] All `ci.yml` jobs green on `main`
- [ ] `security.yml` green
- [ ] `docs/requirements/srs.md` holds FR-01..FR-40 and NFR-01..NFR-10, each with acceptance criteria
- [ ] One GitHub issue exists per FR, labelled and milestoned
- [ ] ADR-0001, ADR-0002 and ADR-0003 written and indexed
- [ ] Branch protection on `main` requires every `ci.yml` context

### Note on the issue-first rule
M0 creates the tracker, so it commits directly to `main`. The issue-first rule
binds from the moment branch protection is enabled in Task 12.
BODY
)"
```

Expected: issue #1 created.

- [ ] **Step 5: Commit nothing, verify remote state**

```bash
git remote -v
git log --oneline -1
```

Expected: `origin` points at the new repo and `main` is pushed.

---
## Task 3: Settings, application factory and the `/api/health` endpoint

The backend walking skeleton. Strict TDD from here on.

**Files:**
- Create: `src/cvforge/config.py`, `src/cvforge/app.py`, `src/cvforge/api/__init__.py`, `src/cvforge/api/health.py`, `scripts/demo/health.py`
- Create: `tests/conftest.py`, `tests/unit/test_config.py`, `tests/unit/test_health.py`, `tests/unit/test_spa_mount.py`, `tests/integration/test_app_wiring.py`

**Interfaces:**
- Consumes: `cvforge.__version__` (Task 1).
- Produces:
  - `cvforge.config.Settings` — pydantic-settings model with fields `host: str`, `port: int`, `data_dir: Path`, `frontend_dist: Path`; env prefix `CVFORGE_`; rejects a non-loopback `host`.
  - `cvforge.app.create_app(settings: Settings | None = None) -> FastAPI`
  - `cvforge.app._mount_spa(app: FastAPI, dist: Path) -> bool`
  - `cvforge.api.health.router: APIRouter` and `cvforge.api.health.Health` (fields `status: str`, `version: str`)
  - `tests/conftest.py` fixture `client` → `fastapi.testclient.TestClient`

- [ ] **Step 1: Write the failing settings test**

```python
# tests/unit/test_config.py
"""Process configuration: defaults, environment overrides, and the loopback rule."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from cvforge.config import Settings


def test_defaults_are_local_only() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.data_dir == Path("data")
    assert settings.frontend_dist == Path("frontend/dist")


def test_environment_overrides_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CVFORGE_PORT", "9100")
    assert Settings().port == 9100


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", ""])
def test_non_loopback_host_is_rejected(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """NFR-02: the tool must never listen on an address reachable off the host."""
    monkeypatch.setenv("CVFORGE_HOST", host)
    with pytest.raises(ValidationError, match="loopback"):
        Settings()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_hosts_are_accepted(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CVFORGE_HOST", host)
    assert Settings().host == host
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_config.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'cvforge.config'`.

- [ ] **Step 3: Implement `Settings`**

```python
# src/cvforge/config.py
"""Process configuration, read from the environment with local-first defaults."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class Settings(BaseSettings):
    """CVForge process configuration.

    Every field is overridable by a `CVFORGE_`-prefixed environment variable or
    an entry in a local `.env` file.

    Attributes:
        host: Address uvicorn binds to. Must be loopback (NFR-02).
        port: TCP port uvicorn binds to.
        data_dir: Directory holding private data — the knowledge base, uploaded
            documents and the browser profile. Never committed.
        frontend_dist: Directory holding the built SPA. The SPA is only served
            when it contains an `index.html`.
    """

    model_config = SettingsConfigDict(env_prefix="CVFORGE_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = Path("data")
    frontend_dist: Path = Path("frontend/dist")

    @field_validator("host")
    @classmethod
    def _reject_non_loopback(cls, value: str) -> str:
        """Reject any bind address reachable from outside this machine.

        Args:
            value: The configured host.

        Returns:
            The host, unchanged, when it is a loopback address.

        Raises:
            ValueError: If the host is not a loopback address (NFR-02).
        """
        if value not in LOOPBACK_HOSTS:
            raise ValueError(
                f"host must be a loopback address (one of {sorted(LOOPBACK_HOSTS)}), got {value!r}"
            )
        return value
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -v --no-cov`
Expected: 8 passed.

- [ ] **Step 5: Write the failing health test and the shared fixture**

```python
# tests/conftest.py
"""Shared fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from cvforge.app import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client over a freshly built application with default settings."""
    with TestClient(create_app()) as test_client:
        yield test_client
```

```python
# tests/unit/test_health.py
"""The /api/health contract."""

from fastapi.testclient import TestClient

import cvforge


def test_health_reports_ok_and_the_running_version(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": cvforge.__version__}


def test_health_is_namespaced_under_api(client: TestClient) -> None:
    """The bare /health path must not exist — every JSON route lives under /api."""
    assert client.get("/health").status_code == 404
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_health.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'cvforge.app'`.

- [ ] **Step 7: Implement the router and the factory**

```python
# src/cvforge/api/__init__.py
"""HTTP routers. Every JSON route is mounted under the /api prefix."""
```

```python
# src/cvforge/api/health.py
"""Liveness endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

import cvforge

router = APIRouter(tags=["system"])


class Health(BaseModel):
    """Liveness payload.

    Attributes:
        status: Always `ok` when the process is serving.
        version: The running `cvforge` package version.
    """

    status: str
    version: str


@router.get("/health")
def health() -> Health:
    """Report that the process is serving, and which version is running.

    Returns:
        The liveness payload.
    """
    return Health(status="ok", version=cvforge.__version__)
```

```python
# src/cvforge/app.py
"""Application factory: one process serving the JSON API and the built SPA (ADR-0002)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import cvforge
from cvforge.api.health import router as health_router
from cvforge.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the CVForge application.

    The JSON API is mounted under `/api`. The built SPA is mounted at `/` only
    when it has been built — without it the API still works and `/` returns 404.

    Args:
        settings: Process configuration. A default `Settings()` is read from the
            environment when omitted.

    Returns:
        The configured application.
    """
    settings = settings or Settings()
    app = FastAPI(title="CVForge", version=cvforge.__version__)
    app.state.settings = settings
    app.include_router(health_router, prefix="/api")
    _mount_spa(app, settings.frontend_dist)
    return app


def _mount_spa(app: FastAPI, dist: Path) -> bool:
    """Mount the built SPA at `/`, if it has been built.

    Mounting happens after the API routes are registered, so `/api/...` always
    wins over the catch-all static mount.

    Args:
        app: The application to mount onto.
        dist: Directory expected to contain the built `index.html`.

    Returns:
        True when the SPA was mounted, False when there is nothing built to serve.
    """
    if not (dist / "index.html").is_file():
        return False
    app.mount("/", StaticFiles(directory=dist, html=True), name="spa")
    return True
```

- [ ] **Step 8: Run it to verify it passes**

Run: `uv run pytest tests/unit/test_health.py -v --no-cov`
Expected: 2 passed.

- [ ] **Step 9: Write the failing SPA-mount tests**

```python
# tests/unit/test_spa_mount.py
"""The SPA is served only when it has actually been built."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cvforge.app import _mount_spa, create_app
from cvforge.config import Settings


def test_mount_is_skipped_when_nothing_is_built(tmp_path: Path) -> None:
    app = FastAPI()
    assert _mount_spa(app, tmp_path) is False


def test_mount_happens_when_index_html_exists(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>CVForge</title>", encoding="utf-8")
    app = FastAPI()
    assert _mount_spa(app, tmp_path) is True


def test_root_returns_404_without_a_build(tmp_path: Path) -> None:
    app = create_app(Settings(frontend_dist=tmp_path))
    with TestClient(app) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/health").status_code == 200
```

- [ ] **Step 10: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_spa_mount.py -v --no-cov`
Expected: 3 passed. (`_mount_spa` already exists, so these pass immediately — they
pin behaviour that Task 5 depends on and that is easy to break later.)

- [ ] **Step 11: Write the integration test**

```python
# tests/integration/test_app_wiring.py
"""The assembled application against a real on-disk dist directory."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.config import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def built_dist(tmp_path: Path) -> Path:
    """A minimal but real built-SPA directory."""
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>CVForge</title><div id='root'></div>", encoding="utf-8"
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('cvforge')", encoding="utf-8")
    return tmp_path


def test_spa_and_api_coexist(built_dist: Path) -> None:
    """The static mount at / must not shadow the JSON API under /api."""
    with TestClient(create_app(Settings(frontend_dist=built_dist))) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "CVForge" in root.text

        asset = client.get("/assets/app.js")
        assert asset.status_code == 200

        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"


def test_openapi_schema_is_served(built_dist: Path) -> None:
    with TestClient(create_app(Settings(frontend_dist=built_dist))) as client:
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/api/health" in schema.json()["paths"]
```

- [ ] **Step 12: Run the integration tests**

Run: `uv run pytest -m integration -v --no-cov`
Expected: 2 passed.

- [ ] **Step 13: Write the demo script**

```python
# scripts/demo/health.py
"""Demo (infra): prove the walking skeleton answers /api/health, fully offline.

Uses the in-process test client rather than a real server so the demo needs no
port, no build and no network — exactly what CI's `demos` job requires.
"""

import json

from fastapi.testclient import TestClient

from cvforge.app import create_app


def main() -> int:
    """Call /api/health through the in-process client and print the result.

    Returns:
        0 when the endpoint answered 200, 1 otherwise.
    """
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
    print(f"GET /api/health -> {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 14: Run the demo and the full unit suite with coverage**

```bash
make demo-health
make test-unit
```

Expected: the demo prints `GET /api/health -> 200`; the unit suite passes and
coverage is **at or above 90%** with branch coverage on. If it is below, the
missing lines are listed — add the test, do not lower the floor.

- [ ] **Step 15: Verify quality gates and commit**

```bash
make lint && make typecheck && make complexity
git add src tests scripts
git commit -m "feat: settings, application factory and /api/health

One uvicorn process serves the JSON API under /api and the built SPA at /
when it exists (ADR-0002). Settings rejects any non-loopback bind address,
which is NFR-02 enforced in code rather than documentation.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
```

---

## Task 4: Golden-snapshot harness and the OpenAPI contract gate

The second regression layer from spec §9. The harness exists before M1 needs it,
and its first subject is the OpenAPI schema — a genuinely useful gate, since an
accidental route or response-model change becomes a reviewable diff instead of a
silent API break.

**Files:**
- Modify: `tests/conftest.py` (add the `--update-golden` option and the `golden` fixture)
- Create: `tests/golden/test_openapi_snapshot.py`, `tests/golden/snapshots/openapi.json`

**Interfaces:**
- Consumes: `create_app` (Task 3), the `client` fixture (Task 3).
- Produces: pytest option `--update-golden`; fixture `golden` with signature `golden(name: str, value: object) -> None` comparing `value` against `tests/golden/snapshots/<name>.json`.

- [ ] **Step 1: Write the failing golden test**

```python
# tests/golden/test_openapi_snapshot.py
"""The published API contract, pinned to a committed snapshot.

Any route added, removed or reshaped changes this snapshot. That is the point:
`pytest -m golden --update-golden` regenerates it, and reviewing the resulting
diff is the gate.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.golden


def test_openapi_schema_matches_snapshot(
    client: TestClient, golden: Callable[[str, object], None]
) -> None:
    schema = client.get("/openapi.json").json()
    # The version travels with the package, so a release bump would otherwise
    # churn the snapshot for no behavioural reason.
    schema["info"].pop("version", None)
    golden("openapi", schema)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -m golden -v --no-cov`
Expected: FAIL — `fixture 'golden' not found`.

- [ ] **Step 3: Add the harness to `tests/conftest.py`**

Append to the existing file from Task 3:

```python
# --- golden-snapshot harness -------------------------------------------------

SNAPSHOT_DIR = Path(__file__).parent / "golden" / "snapshots"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the snapshot-rewriting flag.

    Args:
        parser: The pytest argument parser.
    """
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Rewrite golden snapshots instead of comparing against them.",
    )


@pytest.fixture
def golden(request: pytest.FixtureRequest) -> Callable[[str, object], None]:
    """Compare a value against its committed golden snapshot.

    With `--update-golden` the snapshot is rewritten and the test is reported as
    skipped, so an update run can never be mistaken for a passing comparison.

    Args:
        request: The pytest request, used to read the `--update-golden` flag.

    Returns:
        A callable taking the snapshot name and the value to compare.
    """

    def compare(name: str, value: object) -> None:
        path = SNAPSHOT_DIR / f"{name}.json"
        rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if request.config.getoption("--update-golden"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
            pytest.skip(f"golden snapshot {name!r} rewritten — review the diff")
        if not path.is_file():
            pytest.fail(
                f"missing golden snapshot {path}. Create it with: "
                f"uv run pytest -m golden --no-cov --update-golden"
            )
        assert rendered == path.read_text(encoding="utf-8"), (
            f"golden snapshot {name!r} no longer matches. If this change is "
            f"intended, run `make update-golden` and justify the diff in the PR."
        )

    return compare
```

The file already imports `Iterator` from Task 3. Make the import block at the top
of `tests/conftest.py` read exactly this — do not add a second `Iterator` import:

```python
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cvforge.app import create_app
```

- [ ] **Step 4: Run it to verify it now fails for the right reason**

Run: `uv run pytest -m golden -v --no-cov`
Expected: FAIL — "missing golden snapshot …/openapi.json".

- [ ] **Step 5: Record the snapshot and inspect it**

```bash
make update-golden
cat tests/golden/snapshots/openapi.json
```

Expected: skipped with "rewritten — review the diff", and the file contains the
schema with exactly one path, `/api/health`. **Read it** — recording a snapshot
without reading it defeats the mechanism.

- [ ] **Step 6: Run it to verify it passes**

Run: `uv run pytest -m golden -v --no-cov`
Expected: 1 passed.

- [ ] **Step 7: Prove the gate actually catches drift**

```bash
# Temporarily add a route, confirm the golden test fails, then revert.
python3 - <<'PY'
import pathlib
p = pathlib.Path("src/cvforge/api/health.py")
p.write_text(p.read_text() + '''

@router.get("/ping")
def ping() -> dict[str, str]:
    """Temporary route used to prove the golden gate works."""
    return {"pong": "1"}
''')
PY
uv run pytest -m golden --no-cov
```

Expected: **FAIL** with "golden snapshot 'openapi' no longer matches". Now revert:

```bash
git checkout src/cvforge/api/health.py
uv run pytest -m golden --no-cov
```

Expected: 1 passed. A harness never verified against a real change is not a gate.

- [ ] **Step 8: Commit**

```bash
git add tests/conftest.py tests/golden Makefile
git commit -m "test: golden-snapshot harness with the OpenAPI contract as its first gate

Adds --update-golden and a golden fixture that writes deterministic,
key-sorted JSON. The first snapshot pins the OpenAPI schema, so an
accidental route or response-model change shows up as a reviewable diff
instead of a silent API break. Verified by adding a throwaway route and
confirming the gate fails.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
```

---
## Task 5: React SPA shell served by the backend

The frontend half of the walking skeleton: a built SPA that the Python process
serves, with a live backend-health indicator proving the two halves talk. Visual
design is deliberately restrained here — there is no product surface yet. The real
design work lands in M1 with the chat and review views, using the
`frontend-design` skill.

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/eslint.config.js`, `frontend/index.html`
- Create: `frontend/src/main.tsx`, `frontend/src/index.css`, `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/test-setup.ts`, `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `GET /api/health` → `{status: string, version: string}` (Task 3); `_mount_spa` serving `frontend/dist` (Task 3).
- Produces: `frontend/dist/index.html` after `make build-ui`; npm scripts `dev`, `build`, `lint`, `typecheck`, `test`, `test:coverage`; `fetchHealth(): Promise<Health>` in `frontend/src/api.ts`.

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "cvforge-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:coverage": "vitest run --coverage"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@eslint/js": "^9.17.0",
    "@tailwindcss/vite": "^4.0.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.4",
    "@vitest/coverage-v8": "^2.1.8",
    "eslint": "^9.17.0",
    "eslint-plugin-react-hooks": "^5.1.0",
    "eslint-plugin-react-refresh": "^0.4.16",
    "globals": "^15.14.0",
    "jsdom": "^25.0.1",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.7.2",
    "typescript-eslint": "^8.18.2",
    "vite": "^6.0.5",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 2: Write the Vite, TypeScript and ESLint configuration**

Tailwind v4 is wired through its Vite plugin — there is no `tailwind.config.js`
and no PostCSS step; configuration lives in CSS.

```ts
// frontend/vite.config.ts
/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Dev-server only: relative /api calls reach the Python process same-origin.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/test-setup.ts", "src/**/*.test.tsx"],
      thresholds: { lines: 90, branches: 90, functions: 90, statements: 90 },
    },
  },
});
```

```json
// frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": true,
    "noEmit": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vite.config.ts"]
}
```

```js
// frontend/eslint.config.js
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
);
```

- [ ] **Step 3: Install and verify the toolchain**

```bash
npm --prefix frontend install
npm --prefix frontend run lint
```

Expected: install succeeds and ESLint reports no files to complain about yet.
If `npm install` fails with `ERESOLVE` mentioning `typescript`, that is the known
`typescript-eslint` peer-range problem — Task 7's Dependabot config pins against
it; resolve by keeping TypeScript on the 5.x line.

- [ ] **Step 4: Write the failing component test**

```tsx
// frontend/src/App.test.tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function stubFetch(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response as Response));
}

describe("App", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the product name immediately", () => {
    stubFetch({ ok: true, json: async () => ({ status: "ok", version: "0.1.0" }) });
    render(<App />);
    expect(screen.getByRole("heading", { name: /cvforge/i })).toBeInTheDocument();
  });

  it("reports the backend version once health resolves", async () => {
    stubFetch({ ok: true, json: async () => ({ status: "ok", version: "0.1.0" }) });
    render(<App />);
    expect(await screen.findByText(/backend 0\.1\.0/i)).toBeInTheDocument();
  });

  it("reports a clear failure when the backend is unreachable", async () => {
    stubFetch({ ok: false, status: 503 });
    render(<App />);
    expect(await screen.findByText(/backend unreachable/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Run it to verify it fails**

Run: `npm --prefix frontend run test`
Expected: FAIL — cannot resolve `./App`.

- [ ] **Step 6: Write the implementation**

```ts
// frontend/src/test-setup.ts
import "@testing-library/jest-dom/vitest";
```

```ts
// frontend/src/api.ts
export interface Health {
  status: string;
  version: string;
}

/** Ask the backend whether it is serving, and which version is running. */
export async function fetchHealth(): Promise<Health> {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new Error(`health check failed with status ${response.status}`);
  }
  return (await response.json()) as Health;
}
```

```tsx
// frontend/src/App.tsx
import { useEffect, useState } from "react";
import { fetchHealth, type Health } from "./api";

type BackendState =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; message: string };

export default function App() {
  const [backend, setBackend] = useState<BackendState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((health) => {
        if (!cancelled) setBackend({ kind: "ok", health });
      })
      .catch(() => {
        if (!cancelled) setBackend({ kind: "error", message: "backend unreachable" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-dvh bg-surface text-ink">
      <header className="mx-auto flex max-w-3xl items-baseline justify-between px-6 py-10">
        <h1 className="font-display text-2xl tracking-tight">CVForge</h1>
        <StatusBadge backend={backend} />
      </header>
      <main className="mx-auto max-w-3xl px-6">
        <p className="max-w-prose text-ink-muted">
          A local-first knowledge base of everything you have done professionally — and
          the tailored, evidence-backed CVs it writes.
        </p>
      </main>
    </div>
  );
}

function StatusBadge({ backend }: { backend: BackendState }) {
  if (backend.kind === "loading") {
    return <span className="text-sm text-ink-muted">checking…</span>;
  }
  if (backend.kind === "error") {
    return <span className="text-sm text-danger">backend unreachable</span>;
  }
  return <span className="text-sm text-ink-muted">backend {backend.health.version}</span>;
}
```

```ts
// frontend/src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("missing #root element");
}
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`main.tsx` contains JSX, so rename it exactly as given (`.tsx`) — a `.ts`
extension will fail to compile.

```css
/* frontend/src/index.css */
@import "tailwindcss";

@theme {
  --font-display: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  --color-surface: oklch(98.5% 0.004 260);
  --color-ink: oklch(22% 0.02 260);
  --color-ink-muted: oklch(52% 0.02 260);
  --color-danger: oklch(55% 0.19 25);
}

@media (prefers-color-scheme: dark) {
  @theme {
    --color-surface: oklch(18% 0.012 260);
    --color-ink: oklch(95% 0.006 260);
    --color-ink-muted: oklch(68% 0.014 260);
    --color-danger: oklch(68% 0.17 25);
  }
}
```

```html
<!-- frontend/index.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CVForge</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
npm --prefix frontend run test:coverage
npm --prefix frontend run lint
npm --prefix frontend run typecheck
```

Expected: 3 tests pass; coverage at or above the 90% thresholds; lint and
typecheck clean.

- [ ] **Step 8: Build and serve the real SPA from the Python process**

```bash
make build-ui
make run &
sleep 3
curl -s -o /dev/null -w 'GET /      -> %{http_code}\n' http://127.0.0.1:8000/
curl -s -w '\nGET /api/health -> %{http_code}\n' http://127.0.0.1:8000/api/health
kill %1
```

Expected: `/` returns **200** (the built SPA) and `/api/health` returns **200**
with the JSON payload. This is the M0 acceptance moment: one process, both halves.

- [ ] **Step 9: Commit**

```bash
git add frontend package-lock.json 2>/dev/null; git add frontend
git commit -m "feat: React SPA shell served by the backend process

React 19 + TypeScript + Vite + Tailwind v4 (CSS-first config via the Vite
plugin, no tailwind.config.js). The shell renders a live backend-health
indicator, proving the single-process API + SPA wiring end to end. Vitest
coverage thresholds match the Python floor at 90%.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
```

---

## Task 6: CI workflow

The merge gate. The `docs` job is deliberately **not** added here — `mkdocs.yml`
does not exist until Task 8, and a workflow that fails on `main` teaches everyone
to ignore red. Task 8 adds that job together with the file it needs.

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `make` targets from Task 1; tests from Tasks 3–4; `frontend/` from Task 5.
- Produces: check contexts `Lint & types`, `Unit tests + coverage`, `Integration tests`, `Golden snapshots`, `Offline demos`, `Frontend` — the names Task 12 requires in branch protection.

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  quality:
    name: Lint & types
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --locked
      # `scripts` is included on purpose: scripts/demo/* is the PR template's
      # mandatory validation artifact, so it is load-bearing. Ungated, demos rot.
      - run: uv run ruff check src tests scripts
      - run: uv run ruff format --check src tests scripts
      - run: uv run mypy
      - name: Complexity gate
        run: uv run xenon --max-absolute C --max-modules B --max-average A src

  unit:
    name: Unit tests + coverage
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --locked
      # fail_under=90 with branch coverage lives in pyproject.toml, so the floor
      # is identical locally and here.
      - run: >-
          uv run pytest -m "not integration and not golden and not system"
          --cov --cov-report=xml --cov-report=term
      - uses: actions/upload-artifact@v7
        with:
          name: coverage
          path: coverage.xml

  integration:
    name: Integration tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --locked
      - run: uv run pytest -m integration --no-cov

  golden:
    name: Golden snapshots
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --locked
      # Never pass --update-golden here: in CI the snapshot is the expectation,
      # not an output.
      - run: uv run pytest -m golden --no-cov

  demos:
    name: Offline demos
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --locked
      # Every demo a reviewer is told to run to validate a PR. A broken one voids
      # the Definition of Done, so it must break the build.
      - run: make test-demos

  frontend:
    name: Frontend
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v7
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run build
      - run: npm run test:coverage
```

- [ ] **Step 2: Commit, push and watch the run**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: required merge gates for lint, types, tests, coverage and frontend

Six jobs, each mapping to a branch-protection context: quality (ruff, mypy
strict, xenon), unit with the 90% branch-coverage floor, integration,
golden snapshots, offline demos, and the frontend pipeline.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
gh run watch --exit-status
```

Expected: all six jobs green. If `frontend` fails on `npm ci`, confirm
`frontend/package-lock.json` was committed in Task 5 — `npm ci` requires it.

---

## Task 7: Security pipeline, weekly sanity metrics, Dependabot and templates

**Files:**
- Create: `.github/workflows/security.yml`, `.github/workflows/sanity.yml`, `.github/dependabot.yml`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/feature.yml`, `.github/ISSUE_TEMPLATE/bug.yml`, `.github/ISSUE_TEMPLATE/infra.yml`

**Interfaces:**
- Consumes: the repository from Task 2.
- Produces: check contexts `pip-audit`, `Bandit (SAST)`, `Gitleaks (history scan)`, `CodeQL`; the issue shapes the `feature-request` skill mirrors in Task 10.

- [ ] **Step 1: Write `security.yml`**

```yaml
# .github/workflows/security.yml
name: Security

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "0 6 * * 1" # weekly Monday 06:00 UTC

jobs:
  audit-dependencies:
    name: pip-audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - run: uv sync --locked
      # --all-extras matters: without it the optional extras this project will
      # grow (playwright, document parsers) would never be audited.
      - run: uv export --no-emit-project --locked --all-extras -o requirements-audit.txt
      - run: uv tool run pip-audit -r requirements-audit.txt

  sast:
    name: Bandit (SAST)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - run: uv tool run bandit -r src scripts -ll

  secrets:
    name: Gitleaks (history scan)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v3
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  codeql:
    name: CodeQL
    runs-on: ubuntu-latest
    permissions:
      # `security-events: write` REPLACES the default permission set, so
      # `contents: read` has to be restated or checkout breaks on a private repo.
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v7
      - uses: github/codeql-action/init@v4
        with:
          # Both languages in ONE job on purpose. A build matrix renames the
          # check contexts to "CodeQL (python)" / "CodeQL (javascript-typescript)",
          # and branch protection requiring a context named exactly "CodeQL" would
          # then never be satisfied — every PR sits blocked with all checks green.
          languages: python, javascript-typescript
      - uses: github/codeql-action/analyze@v4
```

- [ ] **Step 2: Write `sanity.yml`**

```yaml
# .github/workflows/sanity.yml
name: Sanity metrics

on:
  schedule:
    - cron: "0 7 * * 1" # weekly Monday 07:00 UTC
  workflow_dispatch:

jobs:
  metrics:
    name: Mechanical quality signals
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --locked
      - name: Collect metrics report
        run: |
          {
            echo "# Sanity metrics — $(date -u +%F)"
            echo; echo "## Cyclomatic complexity (radon)"; echo '```'
            uv run radon cc -s -a src || true
            echo '```'
            echo; echo "## Dead code candidates (vulture)"; echo '```'
            uv run vulture src --min-confidence 80 || true
            echo '```'
            echo; echo "## Duplication (pylint)"; echo '```'
            uv run pylint --disable=all --enable=duplicate-code src || true
            echo '```'
          } > sanity-report.md
          cat sanity-report.md
      - uses: actions/upload-artifact@v7
        with:
          name: sanity-report
          path: sanity-report.md
```

- [ ] **Step 3: Write `dependabot.yml`**

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: uv
    directory: /
    schedule:
      interval: weekly
    groups:
      dev-dependencies:
        dependency-type: development

  - package-ecosystem: npm
    directory: /frontend
    schedule:
      interval: weekly
    groups:
      dev-dependencies:
        dependency-type: development
    ignore:
      # typescript-eslint still caps its peer range below TypeScript 7, so a
      # TS 7 bump fails `npm ci` with ERESOLVE and takes the whole
      # dev-dependencies group down with it. Version-scoped on purpose: DELETE
      # this entry — do not widen it — once typescript-eslint supports TS 7.
      - dependency-name: typescript
        versions: ["7.x"]

  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

- [ ] **Step 4: Write the pull-request template**

```markdown
<!-- .github/PULL_REQUEST_TEMPLATE.md -->
## What & why

Closes #<issue>. <!-- Every PR traces to an issue -->

<one paragraph: what this changes and why>

## How to validate (mandatory)

```sh
# exact commands to run
```

**Expected output / behavior:**

<what Álvaro should see>

**Acceptance criteria** (from the requirement, tick after personally verifying):

- [ ] …

## Self-review checklist

- [ ] I ran the validation steps above myself and the behavior is correct
- [ ] Tests added/updated at the right level (unit / integration / golden / system)
- [ ] Coverage still ≥90% line and branch; no test skipped without an issue reference
- [ ] Golden snapshots unchanged, or changed deliberately and justified below
- [ ] Docstrings on new/changed public symbols; affected docs and diagrams updated
- [ ] No personal data introduced — fixtures are synthetic, `data/` untouched
- [ ] Knowledge-base writes (if any) go only through `kb/apply.py`, and every new
      entity or edge is backed by an assertion
- [ ] Significant decisions recorded as an ADR

## Golden snapshot changes

<if any snapshot under tests/golden/snapshots/ changed, say which and why it is
correct rather than a regression; otherwise write "none">
```

- [ ] **Step 5: Write the issue templates**

```yaml
# .github/ISSUE_TEMPLATE/feature.yml
name: Feature / requirement
description: Work item implementing (part of) a requirement from the SRS
title: "FR-xx: <title>"
labels: ["feature"]
body:
  - type: input
    id: requirement
    attributes:
      label: Requirement ID
      description: FR-xx / NFR-xx from docs/requirements/srs.md
      placeholder: FR-01
    validations:
      required: true
  - type: textarea
    id: description
    attributes:
      label: Description
      description: What must exist when this is done ("The system shall …")
    validations:
      required: true
  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance criteria
      description: Runnable or checkable tests, copied/refined from the SRS entry
      placeholder: |
        - [ ] ...
        - [ ] ...
    validations:
      required: true
  - type: dropdown
    id: priority
    attributes:
      label: MoSCoW priority
      options: [Must, Should, Could, "Won't (this increment)"]
    validations:
      required: true
```

```yaml
# .github/ISSUE_TEMPLATE/bug.yml
name: Bug
description: Something behaves incorrectly
labels: ["bug"]
body:
  - type: textarea
    id: behavior
    attributes:
      label: Observed vs expected behavior
    validations:
      required: true
  - type: textarea
    id: repro
    attributes:
      label: Reproduction steps
      description: Exact commands or inputs — synthetic data only, never a real CV
    validations:
      required: true
  - type: input
    id: requirement
    attributes:
      label: Affected requirement (if known)
      placeholder: FR-03
```

```yaml
# .github/ISSUE_TEMPLATE/infra.yml
name: Infrastructure / tooling
description: CI, build, developer environment or automation work with no requirement
title: "<scope>: <title>"
labels: ["infra"]
body:
  - type: textarea
    id: description
    attributes:
      label: What needs to change, and why
    validations:
      required: true
  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance criteria
      placeholder: |
        - [ ] ...
    validations:
      required: true
```

- [ ] **Step 6: Commit, push and watch the security run**

```bash
git add .github
git commit -m "ci: security pipeline, weekly sanity metrics, Dependabot and templates

pip-audit over all extras, bandit, gitleaks across full history, and CodeQL
for Python and TypeScript in a single job so the required check context keeps
its exact name. Weekly radon/vulture/pylint report feeds the codebase-sanity
agent. PR template makes the validation steps and the knowledge-base
invariants part of review.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
gh run watch --exit-status
```

Expected: `pip-audit`, `Bandit (SAST)`, `Gitleaks (history scan)` and `CodeQL`
all green. A pip-audit finding on a transitive dependency is fixed by adding a
floor to `[tool.uv] constraint-dependencies` in `pyproject.toml`, with a comment
naming the advisory — not by skipping the job.

---
## Task 8: Requirements catalogue and one issue per requirement

The SRS is the authority on *what* the system must do; the design spec is the
authority on *how*. Spec §6 already holds every requirement statement — this task
formalizes them with priorities, milestones and testable acceptance criteria, then
puts each one on the tracker.

**Files:**
- Create: `docs/requirements/srs.md`

**Interfaces:**
- Consumes: spec §6 (the 40 FR + 10 NFR catalogue) and the labels/milestones from Task 2.
- Produces: `docs/requirements/srs.md` with immutable IDs `FR-01`…`FR-40` and `NFR-01`…`NFR-10`, each carrying a `Traces to: issue #N` line; 40 GitHub issues.

- [ ] **Step 1: Write the SRS header and the entry format**

```markdown
# CVForge — Software Requirements Specification

The authority on **what** CVForge must do. The design spec
(`docs/superpowers/specs/2026-09-12-cvforge-design.md`) is the authority on **how**.

**Rules**
- IDs are immutable and never reused. A new requirement takes the next free number.
- Every requirement is testable. If acceptance criteria cannot be phrased as
  something runnable or checkable, the requirement is split or rephrased.
- Every functional requirement maps 1:1 to a GitHub issue labelled `req:FR-xx`.
- Requirement changes are Álvaro's decisions: draft, confirm, then commit. A scope
  change also gets an ADR.

## Format

### FR-nn — <imperative title>
- **Priority**: Must | Should | Could | Won't (MoSCoW)
- **Milestone**: M0–M8
- **Source**: design spec §<n>
- **Description**: The system shall … (one testable behaviour)
- **Acceptance criteria**:
  - [ ] concrete, executable check
- **Traces to**: issue #N, tests `tests/…`
```

- [ ] **Step 2: Write these four entries verbatim — they are the pattern for the rest**

```markdown
## Knowledge base

### FR-01 — Store professional knowledge entities
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.1
- **Description**: The system shall store professional knowledge entities of the
  kinds `skill`, `project`, `organization`, `role`, `education`, `credential`,
  `achievement` and `responsibility`, each carrying a name, a normalized name, a
  summary and a knowledge state.
- **Acceptance criteria**:
  - [ ] One entity of each of the eight kinds round-trips through the database with every common field preserved
  - [ ] A kind outside the closed set is rejected before reaching the database
  - [ ] `normalized_name` is derived deterministically (case-folded, whitespace-collapsed) and is queryable
- **Traces to**: issue #N, tests `tests/unit/test_entity_model.py`

### FR-03 — Bind every fact to its evidence
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.3
- **Description**: The system shall record, for every entity field value and every
  edge, at least one assertion referencing an evidence span within a source, so
  that the origin of any stored fact can be displayed.
- **Acceptance criteria**:
  - [ ] Committing an entity without at least one assertion raises and writes nothing
  - [ ] Committing an edge without at least one assertion raises and writes nothing
  - [ ] Given a stored fact, the API returns its source kind, locator and excerpt
  - [ ] A repository-wide invariant test finds zero entities and zero edges lacking an assertion
- **Traces to**: issue #N, tests `tests/unit/test_provenance.py`, `tests/integration/test_invariants.py`

### FR-24 — Generate a CV from stored facts only
- **Priority**: Must
- **Milestone**: M5
- **Source**: design spec §6, NFR-05
- **Description**: In automatic mode the system shall generate a CV exclusively
  from facts already stored in the knowledge base, inventing no skill, experience,
  responsibility, achievement or other claim.
- **Acceptance criteria**:
  - [ ] Every generated bullet has a `cv_claim` row linking it to an entity and an assertion
  - [ ] Generation against a knowledge base containing no match for a job requirement omits that requirement rather than inventing a claim
  - [ ] A requirement matched only as `undocumented` or `gap` never appears as a CV claim
  - [ ] `cv/validate.py` rejects a CV containing an unsupported claim, and the API refuses to mark it final
- **Traces to**: issue #N, tests `tests/unit/test_cv_validate.py`, `tests/golden/test_cv_generation.py`

## Non-functional requirements

### NFR-03 — Test coverage floor
- **Priority**: Must
- **Milestone**: M0
- **Source**: design spec §9
- **Description**: The test suite shall cover at least 90% of lines and 90% of
  branches in `src/`, enforced automatically.
- **Acceptance criteria**:
  - [ ] `fail_under = 90` and `branch = true` are set in `pyproject.toml`
  - [ ] The CI unit job fails when coverage drops below the floor
  - [ ] No test is skipped or xfailed without an issue reference in the skip reason
- **Traces to**: issue #1, `.github/workflows/ci.yml`
```

- [ ] **Step 3: Write the remaining 46 entries by transcribing spec §6**

Every remaining requirement statement **already exists, written out, in spec §6**
— copy each description from there rather than rewording it. For each, add the
priority and milestone from this table, and derive acceptance criteria by the rule
below.

| Requirement | Priority | Milestone |
|---|---|---|
| FR-01 … FR-06 | Must | M1 |
| FR-07 … FR-12 | Must | M1 |
| FR-13 (streaming) | Should | M1 |
| FR-14, FR-15, FR-16 | Must | M2 |
| FR-17, FR-18, FR-20 | Must | M3 |
| FR-19 (company research) | Should | M3 |
| FR-21, FR-22, FR-23 | Must | M4 |
| FR-24 … FR-29 | Must | M5 |
| FR-30 (discovery questions) | Should | M6 |
| FR-31 (conversational CV editing) | Must | M6 |
| FR-32 (interview mode) | Should | M6 |
| FR-33 (learning plan) | Should | M7 |
| FR-34 (learning progress) | Could | M7 |
| FR-35, FR-36, FR-37 (forms) | Should | M8 |
| FR-38, FR-39, FR-40 (providers) | Must | M1 |
| NFR-01 … NFR-09 | Must | M0 except NFR-05 (M5), NFR-07 (M3) |
| NFR-10 (p95 latency) | Should | M1 |

**Rule for deriving acceptance criteria:** each criterion must name something a
test can execute or a command can check. Write the negative case as well as the
positive one — for every "the system does X", add "and when the precondition is
absent, it refuses rather than guessing". That negative half is what protects the
invariants in spec §1.

- [ ] **Step 4: Verify the catalogue is complete**

```bash
grep -c '^### FR-' docs/requirements/srs.md   # expect 40
grep -c '^### NFR-' docs/requirements/srs.md  # expect 10
# Every FR must have all five fields.
for f in Priority Milestone Source Description 'Acceptance criteria' 'Traces to'; do
  printf '%-20s %s\n' "$f" "$(grep -c "\*\*$f\*\*" docs/requirements/srs.md)"
done
```

Expected: 40 and 10; each field count is 50.

- [ ] **Step 5: Create one GitHub issue per functional requirement**

This reads the SRS you just wrote — it invents nothing.

```bash
python3 - <<'PY'
"""One-shot bootstrap: open a GitHub issue per FR, straight from the SRS."""
import re
import subprocess
from pathlib import Path

MILESTONES = {
    "M0": "M0 Foundations", "M1": "M1 Knowledge spine", "M2": "M2 Document ingestion",
    "M3": "M3 Job intake", "M4": "M4 Match and gaps", "M5": "M5 CV generation",
    "M6": "M6 Collaborative mode", "M7": "M7 Learning plans", "M8": "M8 Form autofill",
}

text = Path("docs/requirements/srs.md").read_text(encoding="utf-8")
# Split on FR headings, keeping each requirement's own body with it.
blocks = re.split(r"\n(?=### FR-)", text)
for block in blocks:
    head = re.match(r"### (FR-\d{2}) — (.+)", block)
    if not head:
        continue
    fr_id, title = head.group(1), head.group(2).strip()
    milestone_key = re.search(r"\*\*Milestone\*\*: (M\d)", block)
    if not milestone_key:
        raise SystemExit(f"{fr_id} has no Milestone field")
    body = block.split("### ", 1)[-1]
    body = body.split("\n", 1)[1].strip()
    body += (
        f"\n\nSRS entry: `docs/requirements/srs.md` → {fr_id}."
        f"\nDesign spec: `docs/superpowers/specs/2026-09-12-cvforge-design.md`."
    )
    cmd = [
        "gh", "issue", "create",
        "--title", f"{fr_id}: {title}",
        "--body", body,
        "--label", "feature",
        "--label", f"req:{fr_id}",
        "--milestone", MILESTONES[milestone_key.group(1)],
    ]
    print(" ".join(cmd[:6]))
    subprocess.run(cmd, check=True)
PY
gh issue list --limit 50 --json number,title --jq '.[] | "\(.number) \(.title)"' | sort -k2
```

Expected: 40 new issues, `FR-01:` … `FR-40:`, each labelled and milestoned.

- [ ] **Step 6: Write the issue numbers back into the SRS**

```bash
python3 - <<'PY'
"""Replace each FR's `Traces to: issue #N` placeholder with the real number."""
import json
import re
import subprocess
from pathlib import Path

raw = subprocess.run(
    ["gh", "issue", "list", "--limit", "100", "--json", "number,title"],
    capture_output=True, text=True, check=True,
).stdout
numbers = {}
for issue in json.loads(raw):
    match = re.match(r"(FR-\d{2}):", issue["title"])
    if match:
        numbers[match.group(1)] = issue["number"]

path = Path("docs/requirements/srs.md")
text = path.read_text(encoding="utf-8")
for fr_id, number in numbers.items():
    text = re.sub(
        rf"(### {fr_id} —[\s\S]*?\*\*Traces to\*\*: issue )#N",
        rf"\g<1>#{number}",
        text,
    )
path.write_text(text, encoding="utf-8")
remaining = text.count("issue #N")
print(f"remaining placeholders: {remaining}")
PY
```

Expected: `remaining placeholders: 0`.

- [ ] **Step 7: Commit**

```bash
git add docs/requirements/srs.md
git commit -m "docs: requirements catalogue (FR-01..FR-40, NFR-01..NFR-10)

Formalizes the design spec's requirement list with MoSCoW priorities,
milestone assignment and testable acceptance criteria, each tracing to its
GitHub issue. Acceptance criteria state the negative case as well as the
positive one, so the invariants protecting the knowledge base are what the
tests actually assert.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
```

---

## Task 9: Documentation site, architecture diagrams and the first ADRs

**Files:**
- Create: `mkdocs.yml`, `README.md`, `docs/index.md`, `docs/architecture/overview.md`, `docs/architecture/knowledge-model.md`, `docs/reference/api.md`
- Create: `docs/adr/README.md`, `docs/adr/0001-sqlite-knowledge-store.md`, `docs/adr/0002-single-process-api-and-spa.md`, `docs/adr/0003-changeset-review-pipeline.md`
- Modify: `.github/workflows/ci.yml` (add the `docs` job)

**Interfaces:**
- Consumes: `docs/requirements/srs.md` (Task 8) — it is in the site navigation, which is why the docs job arrives only now; `cvforge.app` and `cvforge.config` docstrings (Task 3) for the generated API page.
- Produces: `mkdocs build --strict` passing; check context `Docs build`; the ADR index that the `adr` skill appends to.

- [ ] **Step 1: Write `mkdocs.yml`**

The `!!python/name:` tag is why `.pre-commit-config.yaml` excludes this file from
`check-yaml` — it is valid for MkDocs, not for a generic YAML parser.

```yaml
site_name: CVForge
site_description: Local-first personal professional knowledge system that generates tailored, evidence-backed CVs
repo_url: https://github.com/SelfishCoconut/cvforge
edit_uri: ""

theme:
  name: material
  features:
    - navigation.sections
    - navigation.top
    - content.code.copy
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      toggle: { icon: material/weather-night, name: Switch to dark mode }
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      toggle: { icon: material/weather-sunny, name: Switch to light mode }

plugins:
  - search
  - mermaid2
  - mkdocstrings:
      handlers:
        python:
          paths: [src]
          options:
            docstring_style: google
            show_source: false
            show_root_heading: true
            members_order: source

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:mermaid2.fence_mermaid_custom
  - toc:
      permalink: true

nav:
  - Home: index.md
  - Requirements: requirements/srs.md
  - Architecture:
      - Overview: architecture/overview.md
      - Knowledge model: architecture/knowledge-model.md
  - Decisions:
      - Index: adr/README.md
      - 0001 SQLite knowledge store: adr/0001-sqlite-knowledge-store.md
      - 0002 Single process for API and SPA: adr/0002-single-process-api-and-spa.md
      - 0003 Changeset review pipeline: adr/0003-changeset-review-pipeline.md
  - API reference: reference/api.md
```

- [ ] **Step 2: Write `docs/index.md` and `docs/reference/api.md`**

```markdown
<!-- docs/index.md -->
# CVForge

A local-first personal professional knowledge system. It records everything you
know and have done professionally, with the evidence behind each fact, and uses
that knowledge to analyze job openings, generate tailored CVs, find gaps in your
skills, plan how to close them, and prepare you for interviews.

## The five invariants

1. The database is the source of truth, not the LLM.
2. `src/cvforge/kb/apply.py` is the only module that writes entity, edge or
   assertion rows. Agents have no write tools.
3. No entity and no edge exists without at least one assertion bound to an
   evidence span in a source.
4. Nothing reaches the database without review: agents propose, you accept, edit
   or reject each operation, and the commit is atomic.
5. Automatic-mode CV generation never emits a claim without a stored assertion.

## Where to look

- [Requirements](requirements/srs.md) — what the system must do.
- [Architecture overview](architecture/overview.md) — how it is put together.
- [Knowledge model](architecture/knowledge-model.md) — entities, relationships and provenance.
- [Decisions](adr/README.md) — why it is built this way.
```

```markdown
<!-- docs/reference/api.md -->
# API reference

Generated from docstrings. Update the docstring, not this page.

## Application

::: cvforge.app

## Configuration

::: cvforge.config

## Health endpoint

::: cvforge.api.health
```

- [ ] **Step 3: Write the architecture pages**

```markdown
<!-- docs/architecture/overview.md -->
# Architecture overview

## Context

```mermaid
C4Context
  title CVForge — system context
  Person(alvaro, "Álvaro", "Records his professional knowledge and applies for jobs")
  System(cvforge, "CVForge", "Local-first knowledge base, CV generator and application assistant")
  System_Ext(ollama, "Ollama", "Local LLM and embedding endpoint (default)")
  System_Ext(cloud, "Anthropic / OpenAI", "Optional remote model providers")
  System_Ext(boards, "Job boards and company sites", "Untrusted web content")
  Rel(alvaro, cvforge, "Converses, reviews proposals, approves CVs")
  Rel(cvforge, ollama, "Prompts and embeddings", "HTTP, localhost")
  Rel(cvforge, cloud, "Prompts (opt-in only)", "HTTPS")
  Rel(cvforge, boards, "Fetches and reads", "HTTPS")
```

## Containers

```mermaid
C4Container
  title CVForge — containers
  Person(alvaro, "Álvaro")
  Container_Boundary(proc, "Single uvicorn process (ADR-0002)") {
    Container(spa, "React SPA", "React 19, TypeScript, Tailwind v4", "Chat, proposal review, jobs, CV versions, settings")
    Container(api, "FastAPI", "Python 3.13", "JSON API under /api")
    Container(agents, "Agent layer", "Pydantic AI", "Read-only tools, structured output")
    Container(kb, "Knowledge layer", "Python 3.13", "queries.py reads; apply.py is the only writer")
  }
  ContainerDb(db, "cvforge.db", "SQLite + sqlite-vec", "Entities, edges, assertions, proposals, jobs, CVs")
  Rel(alvaro, spa, "Uses", "HTTPS on 127.0.0.1")
  Rel(spa, api, "Calls", "JSON over /api")
  Rel(api, agents, "Requests a proposal or an analysis")
  Rel(agents, kb, "Reads only")
  Rel(api, kb, "Reads, and commits approved proposals")
  Rel(kb, db, "SQL")
```

## Why the agent cannot write

The arrow from the agent layer to the knowledge layer is read-only, and there is
no arrow from the agent layer to the database. An agent's output is a `Proposal`
— plain data. Only `kb/apply.py`, reached from the API after Álvaro approves
operations, writes. See [ADR-0003](../adr/0003-changeset-review-pipeline.md).
```

```markdown
<!-- docs/architecture/knowledge-model.md -->
# Knowledge model

```mermaid
erDiagram
  ENTITY ||--o{ EDGE : "src"
  ENTITY ||--o{ EDGE : "dst"
  SOURCE ||--o{ EVIDENCE : contains
  EVIDENCE ||--o{ ASSERTION : supports
  ASSERTION }o--|| ENTITY : "targets (target_kind=entity)"
  ASSERTION }o--|| EDGE : "targets (target_kind=edge)"
  PROPOSAL ||--o{ OPERATION : contains
  PROPOSAL ||--|| SOURCE : "derived from"

  ENTITY { string id string kind string name string normalized_name string state }
  EDGE { string id string src_id string rel string dst_id float confidence }
  SOURCE { string id string kind string uri string content_hash }
  EVIDENCE { string id string source_id string locator string excerpt }
  ASSERTION { string id string target_kind string target_id string field string evidence_id }
  PROPOSAL { string id string origin string status }
  OPERATION { string id int seq string op_type string classification string status }
```

## Entity kinds

`skill` · `project` · `organization` · `role` · `education` · `credential` ·
`achievement` · `responsibility`. A *technology* is a `skill` with a category; a
*certification* and a *course* are both `credential` with different
`credential_type` values.

## Relationship vocabulary (closed — never invent a value)

`used_in` · `at_organization` · `produced` · `involved` · `demonstrates` ·
`taught_by` · `part_of` · `related_to`

No entity table carries a foreign key to another entity. An education's
institution, a role's employer and a credential's issuer are all
`at_organization` edges, so relationships live in exactly one place and are
evidenced the same way.

## Knowledge state vs match verdict

`entity.state` is `confirmed | learning | gap | archived`. "Something I have but
have not recorded" is deliberately **not** a state — it is a *match verdict*
(`undocumented`), because by definition such a thing is not in the database. The
four verdicts are `satisfied`, `evidenced`, `undocumented` and `gap`;
`undocumented` and `gap` may never produce a CV claim.

## The write path

```mermaid
flowchart LR
  A[Álvaro speaks / uploads / pastes a URL] --> B[Agent]
  B -->|reads only| KB[(cvforge.db)]
  B --> P[Proposal: typed operations<br/>each classified and evidenced]
  P --> R[Review UI: accept / edit / reject<br/>per operation]
  R --> W[kb/apply.py]
  W -->|one transaction| KB
```

Nothing else writes. A database write introduced anywhere outside `kb/apply.py`
is a bug caught by the `provenance-auditor` agent, the `kb-write-path` hook and an
invariant test.
```

- [ ] **Step 4: Write the ADR index and the three ADRs**

```markdown
<!-- docs/adr/README.md -->
# Architecture Decision Records

Decisions are recorded in [MADR](https://adr.github.io/madr/) format, one file
per decision. A decision without an ADR does not exist — these are the durable
record of *why*, and the context that survives a cleared conversation.

Supersede, never rewrite: a changed decision gets a new ADR linking back.

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-sqlite-knowledge-store.md) | SQLite knowledge store with a generic edge table | accepted | 2026-09-12 |
| [0002](0002-single-process-api-and-spa.md) | One uvicorn process serves the API and the SPA | accepted | 2026-09-12 |
| [0003](0003-changeset-review-pipeline.md) | Agents propose changesets; they never write | accepted | 2026-09-12 |
```

```markdown
<!-- docs/adr/0001-sqlite-knowledge-store.md -->
# 0001. SQLite holds the knowledge base, with entity inheritance and a generic edge table

Date: 2026-09-12
Status: accepted

## Context

CVForge stores eight kinds of professional knowledge entity and arbitrary typed
relationships between them ("Python used in project X", "project X for company
Y", "project X produced achievement Z"), plus provenance for every fact. It is a
single-user, local-first tool whose whole premise is that private data stays on
one machine. The store has to support multi-hop traversal, duplicate detection by
meaning rather than string equality, and a backup story simple enough to actually
be used.

## Decision

We will use one SQLite file (`cvforge.db`) with:

- **Joined-table inheritance**: a base `entity` table holding the common columns
  and the `kind` discriminator, and one child table per kind. All entities share a
  single id space.
- **A generic `edge` table** (`src_id`, `rel`, `dst_id`, `confidence`, validity
  dates) with a closed `rel` vocabulary. No entity table holds a foreign key to
  another entity.
- **Provenance in three tables** — `source`, `evidence`, `assertion` — with every
  entity and edge requiring at least one assertion.
- **`sqlite-vec`** for embedding similarity, used for duplicate candidates and
  requirement matching.

## Alternatives considered

- **An embedded property graph (Kùzu) alongside SQLite.** Cypher traversals are
  more pleasant than recursive CTEs, but it means two stores to keep consistent,
  a less settled migration story, and documents/CV versions still needing SQLite.
  The traversals we actually need are two or three hops deep.
- **PostgreSQL with pgvector.** Mature migrations, relational and vector in one
  engine. Rejected because it requires a running service for a single-user local
  tool, and backup stops being "copy one file".
- **A single entity table with a JSON attribute blob.** Cheaper schema evolution,
  but it gives up column constraints and type checking on the data that matters
  most, and the set of entity kinds is known and stable.

## Consequences

- Backup, sync and reset are file operations. There is no service to run.
- Relationship queries are recursive CTEs. Anything deeper than a few hops will
  need a materialized closure table — acceptable, and not needed yet.
- Adding an entity kind means a migration adding a child table, which is a
  deliberate speed bump on a decision that deserves one.
- `sqlite-vec` is a compiled extension; loading it is a startup concern and must
  degrade to exact-match dedup when unavailable.
```

```markdown
<!-- docs/adr/0002-single-process-api-and-spa.md -->
# 0002. One uvicorn process serves both the JSON API and the built SPA

Date: 2026-09-12
Status: accepted

## Context

CVForge has a React front end and a Python back end. A local single-user tool
should be startable with one command, with no reverse proxy, no CORS
configuration, and no second port to remember.

## Decision

We will serve everything from one uvicorn process. FastAPI mounts the JSON API
under `/api`, and the built SPA is mounted at `/` from `frontend/dist` — but only
when `frontend/dist/index.html` exists. The process binds `127.0.0.1` only, and
`Settings` rejects any non-loopback host.

During front-end development a second process (the Vite dev server) proxies
`/api` to the backend, so relative paths work the same in both modes.

## Alternatives considered

- **Two long-running services behind a proxy.** Standard for deployment, and
  entirely unnecessary overhead for a tool that runs on one laptop.
- **Serving the SPA from a separate static server.** Adds CORS configuration and
  a second thing to start, for no benefit.

## Consequences

- `make run` without `make build-ui` gives a working API and a 404 at `/`. This
  is an explicit, tested behaviour rather than a crash, and it is the first thing
  to check when the UI "disappears".
- The static mount is registered after the API routes, so `/api/...` always wins
  over the SPA catch-all. An integration test pins this; reversing the order is a
  silent, total API outage.
- There is no authentication anywhere. That is sound only because the process is
  unreachable from off the machine, which is why the loopback check is code and
  not a comment.
```

```markdown
<!-- docs/adr/0003-changeset-review-pipeline.md -->
# 0003. Agents propose changesets; they never write to the knowledge base

Date: 2026-09-12
Status: accepted

## Context

The knowledge base is meant to be the source of truth about a real career. The
failure mode that would destroy its value is an LLM gradually inventing or
quietly altering facts — a team of five becoming a team of fifteen, a course
becoming a certification, a skill appearing because it fitted a job posting. Any
design that relies on prompt wording to prevent this will eventually fail.

## Decision

We will give agents **no write capability at all**. An agent's only output is a
`Proposal`: an ordered list of typed operations (`create_entity`, `update_field`,
`add_edge`, `attach_evidence`, `merge_duplicate`, `set_state`), each carrying the
evidence span it came from and a classification (`new`, `known`, `duplicate`,
`conflict`). Álvaro accepts, edits or rejects **each operation individually**.
Committing applies the survivors in one transaction through `kb/apply.py`, the
only module in the codebase that writes entity, edge or assertion rows, and
records the commit.

## Alternatives considered

- **Direct agent writes with a journal and undo.** Far less machinery and a
  snappier feel. Rejected: review becomes after-the-fact, duplicate and conflict
  detection lose their natural home, and the system would no longer do the thing
  that was asked for — show what it understood *before* storing anything.
- **A staging schema promoted on accept.** Conceptually tidy, but every read path
  then has to know which store it is reading, and cross-store duplicate detection
  pushes the complexity into the read path, where it is worst.

## Consequences

- One review surface serves conversational ingest, document ingest and interview
  mode: three features, one UI, one audit trail.
- A proposal is plain data, so the entire pipeline is testable with no model
  involved — which is what makes the 90% coverage floor and the golden suite
  achievable.
- Every write costs a round trip through review. For bulk document import that is
  friction by design.
- The rule is only as strong as its enforcement, so it is enforced three ways: an
  invariant test, the `provenance-auditor` agent, and the `kb-write-path` hook.
```

- [ ] **Step 5: Write `README.md`**

```markdown
# CVForge

A local-first personal professional knowledge system: it records everything you
know and have done professionally — with the evidence behind each fact — and uses
that knowledge to analyze job openings, generate tailored CVs, find gaps in your
skills, plan how to close them, and prepare you for interviews.

Not an AI CV generator. The CV is one output of a knowledge base that is the
source of truth.

## Status

M0 (foundations). See `docs/roadmap.md` for current state and the next action.

## Run it

```sh
make build-ui    # build the SPA — without this, / returns 404 and only /api works
make run         # http://127.0.0.1:8000 — SPA and API from one process
```

`make demo-health` proves the skeleton works offline, with no server and no build.

## Develop

```sh
uv sync                      # Python 3.13 environment
uv run pre-commit install    # commit-time gates
make lint typecheck complexity
make test                    # unit + integration + golden
make docs-serve              # documentation site at :8000
```

## The five invariants

1. The database is the source of truth, not the LLM.
2. `src/cvforge/kb/apply.py` is the only module that writes entity, edge or
   assertion rows. Agents have no write tools.
3. No entity and no edge exists without at least one assertion bound to an
   evidence span in a source.
4. Nothing reaches the database without review: agents propose, you accept, edit
   or reject each operation, and the commit is atomic.
5. Automatic-mode CV generation never emits a claim without a stored assertion.

## Privacy

Your knowledge base, documents, CVs and browser profile live in `data/`, which is
gitignored and never leaves the machine. The default model backend is a local
Ollama endpoint; Anthropic, OpenAI and web search are opt-in. Fetched web pages
and uploaded documents are treated as untrusted data — analyzed, never obeyed.

## Licence

AGPL-3.0-or-later.
```

- [ ] **Step 6: Build the site strictly**

```bash
make docs
```

Expected: `mkdocs build --strict` succeeds. Strict mode fails on any broken
internal link or unresolved mkdocstrings reference — fix the link or the
docstring, never relax `--strict`.

- [ ] **Step 7: Add the `docs` job to `ci.yml`**

Append this job to `.github/workflows/ci.yml`:

```yaml
  docs:
    name: Docs build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --locked
      # --strict is the point: a broken link or an unresolved mkdocstrings
      # reference fails the build before merge, not after.
      - run: make docs
```

- [ ] **Step 8: Commit, push and verify**

```bash
git add mkdocs.yml README.md docs/index.md docs/architecture docs/adr docs/reference \
        .github/workflows/ci.yml
git commit -m "docs: documentation site, architecture diagrams and ADR-0001..0003

MkDocs Material with mkdocstrings API pages generated from docstrings and
authored C4/ER/flow diagrams in Mermaid. No generated UML, by decision D7.
ADR-0001 records the SQLite knowledge store, ADR-0002 the single-process
API+SPA, ADR-0003 why agents propose changesets and never write. The docs
build is now a required CI gate.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
gh run watch --exit-status
```

Expected: seven CI jobs green, including `Docs build`.

---
## Task 10: Claude Code settings and the six ported skills

These six are adapted from `/home/alvar/tfg/.claude/skills/` — read each original
for reference, but write the content below, which has the thesis, Kanban-board and
`revalid` specifics removed and CVForge's invariants added.

**Files:**
- Create: `.claude/settings.json`
- Create: `.claude/skills/{requirements,feature-request,adr,docs,progress-report,run}/SKILL.md`

**Interfaces:**
- Consumes: labels and milestones (Task 2), `docs/requirements/srs.md` (Task 8), `docs/adr/README.md` (Task 9), the `Makefile` (Task 1).
- Produces: the enabled-plugin set and four hook registrations the hooks in Task 12 must match by filename.

- [ ] **Step 1: Install the plugins that are not yet present at user scope**

Already installed: `superpowers`, `code-review`, `github`, `frontend-design`,
`pydantic-ai`, `playwright`, `context7`, `commit-commands`, `security-guidance`,
`code-simplifier`, `claude-md-management`, `skill-creator`.

```bash
claude plugin install pyright-lsp@claude-plugins-official
claude plugin install semgrep@claude-plugins-official
claude plugin install pr-review-toolkit@claude-plugins-official
claude plugin install remember@claude-plugins-official
```

- [ ] **Step 2: Write `.claude/settings.json`**

```json
{
  "enabledPlugins": {
    "superpowers@claude-plugins-official": true,
    "code-review@claude-plugins-official": true,
    "pr-review-toolkit@claude-plugins-official": true,
    "code-simplifier@claude-plugins-official": true,
    "github@claude-plugins-official": true,
    "commit-commands@claude-plugins-official": true,
    "frontend-design@claude-plugins-official": true,
    "pydantic-ai@claude-plugins-official": true,
    "playwright@claude-plugins-official": true,
    "context7@claude-plugins-official": true,
    "pyright-lsp@claude-plugins-official": true,
    "semgrep@claude-plugins-official": true,
    "security-guidance@claude-plugins-official": true,
    "claude-md-management@claude-plugins-official": true,
    "skill-creator@claude-plugins-official": true,
    "remember@claude-plugins-official": true
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "sh \"$CLAUDE_PROJECT_DIR/.claude/hooks/remind-issue.sh\""
          }
        ]
      },
      {
        "matcher": "Bash|Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "sh \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard-private-data.sh\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "sh \"$CLAUDE_PROJECT_DIR/.claude/hooks/format-on-edit.sh\""
          },
          {
            "type": "command",
            "command": "sh \"$CLAUDE_PROJECT_DIR/.claude/hooks/kb-write-path.sh\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Write `.claude/skills/requirements/SKILL.md`**

```markdown
---
name: requirements
description: Create, update, or audit requirements in the SRS (docs/requirements/srs.md) and keep them in sync with labeled GitHub issues. Use for "add a requirement", "update FR-xx", "sync requirements to issues", or traceability checks.
---

# Requirements management (SRS ↔ GitHub issues)

`docs/requirements/srs.md` is the single source for requirements. Every functional
requirement maps 1:1 to a GitHub issue labelled `req:FR-xx`.

## Entry format

```markdown
### FR-12 — <imperative title>
- **Priority**: Must | Should | Could | Won't (MoSCoW)
- **Milestone**: M0–M8
- **Source**: design spec §n | elicitation YYYY-MM-DD | ADR-NNNN | change request
- **Description**: The system shall …  (one testable behaviour)
- **Acceptance criteria**:
  - [ ] concrete, executable check
- **Traces to**: issue #N, tests `tests/…`
```

NFRs use `NFR-xx` with a measurable target ("p95 proposal round-trip < 30 s on
qwen3.6:27b", never "fast").

## Rules

- IDs are immutable and never reused. A new requirement takes the next free number.
- A requirement must be testable. If the acceptance criteria cannot be phrased as
  something runnable, split or rephrase it.
- **Every criterion states the negative case too.** For "the system does X", add
  "and when the precondition is absent it refuses rather than guessing". That half
  is what protects the invariants in CLAUDE.md.
- Requirements changes are Álvaro's decisions: draft, confirm, then commit. A scope
  change also gets an ADR.
- Sync: each FR gets an issue titled `FR-xx: <title>` labelled `feature` +
  `req:FR-xx` with the matching milestone. When an FR changes, update its issue body.
- Traceability audit (on request, and before closing a milestone): every FR has an
  issue; every closed FR issue has merged PRs referencing it and tests that
  exercise the behaviour. Report orphans.
```

- [ ] **Step 4: Write `.claude/skills/feature-request/SKILL.md`**

```markdown
---
name: feature-request
description: Turn a plain-language feature request from Álvaro into a labeled GitHub issue (and optionally a feature branch). Use for "add a feature", "new feature request", "I want X", "turn this into an issue", "create a card for X".
---

# Feature request → board-ready issue

Front door for Álvaro's requests: convert an informal ask into a well-formed
GitHub issue, then optionally a branch, so request → issue → PR starts clean.

**No duplication:** requirement text is owned by the `requirements` skill, PR
creation by `commit-commands`. This skill orchestrates and calls those — it never
re-implements them.

## 1. Classify

- **Existing requirement** — already an `FR-xx`/`NFR-xx` in the SRS. Reuse the ID
  and the `req:FR-xx` label. Check `gh issue list --label req:FR-xx` first; most FRs
  already have an issue.
- **New product requirement** — a new behaviour of the system. **Stop and invoke
  the `requirements` skill first** to add it to the SRS (it assigns the next
  immutable ID), then come back. Never open a product-behaviour issue that is not
  in the SRS.
- **Infra / tooling** — CI, build, dev environment. Label `infra`, no FR. Title
  `<scope>: <title>`.
- **Bug** — label `bug`; reference the affected FR when known.

Ambiguous? Ask Álvaro.

## 2. Draft — do not create yet

Mirror `.github/ISSUE_TEMPLATE/feature.yml` so a `gh`-created issue matches a
template-created one:

- **Title**: `FR-xx: <imperative title>` or `<scope>: <title>`.
- **Body**: Requirement ID · Description (what must exist when done) · Acceptance
  criteria as checkboxes lifted from the SRS entry, runnable or checkable · MoSCoW
  priority.
- **Labels**: `feature` + `req:FR-xx` · `req:nonfunctional` · `infra` · `bug`.
- **Milestone**: the matching `M0`–`M8`.

Present the draft. **Nothing is created until Álvaro approves** — Claude never
opens scope-bearing items unilaterally.

## 3. Create on approval

```sh
gh issue create --title "FR-xx: <title>" --body-file <draft.md> \
  --label feature --label req:FR-xx --milestone "M1 Knowledge spine"
```

Then update the FR's `Traces to: issue #N` line via the `requirements` skill.

## 4. Optional — start the branch

```sh
git switch main && git pull
git switch -c feat/fr-xx-<slug>   # prefix = the Conventional-Commit type the work will use
```

The PR comes later, via `commit-commands`, and **must** contain `Closes #<issue>`.

## Definition of a good issue

Traces to a requirement (or is explicitly `infra`/`bug`); acceptance criteria are
runnable; correctly labelled and milestoned.
```

- [ ] **Step 5: Write `.claude/skills/adr/SKILL.md`**

```markdown
---
name: adr
description: Create or update an Architecture Decision Record in docs/adr/ (MADR format). Use whenever a significant design, architecture or scope decision is made, or when the user says "record this decision".
---

# Architecture Decision Records

ADRs are the durable record of *why*. They are what survives a cleared
conversation, so a decision without an ADR effectively does not exist.

## Format (MADR, one file per decision)

File: `docs/adr/NNNN-short-kebab-title.md` — `NNNN` is the next sequential number;
check existing files.

```markdown
# NNNN. <Title — the decision, stated as a fact>

Date: YYYY-MM-DD
Status: accepted | proposed | superseded by [NNNN](link) | deprecated

## Context
What forces are at play; why a decision is needed now.

## Decision
What Álvaro decided. Active voice: "We will…"

## Alternatives considered
Each rejected option and the concrete reason it lost.

## Consequences
What becomes easier, what becomes harder, what debt is accepted.
```

## Rules

- The decision-maker is Álvaro. If he has not explicitly decided, write the ADR
  with status `proposed` and ask — never mark `accepted` on his behalf.
- Update the `docs/adr/README.md` index table (number, title, status, date) **and**
  the `nav` entry in `mkdocs.yml`, or `mkdocs build --strict` fails.
- Also register it in the codebase-memory graph with `manage_adr`, so structural
  queries surface it.
- Supersede, never rewrite history: a changed decision gets a new ADR linking back.
- "Alternatives considered" is not optional. An ADR that lists no rejected option
  is a note, not a decision record.
```

- [ ] **Step 6: Write `.claude/skills/docs/SKILL.md`**

```markdown
---
name: docs
description: Build, serve or extend the CVForge documentation site (MkDocs Material + mkdocstrings). Use for "build the docs", "add a docs page", "the docs build is failing", or docs drift checks.
---

# Documentation site (docs-as-code)

Principle: anything derivable from code is generated at build time. Anything that
expresses intent is authored and reviewed.

## Build

- `make docs` → `mkdocs build --strict`. Strict mode fails on any broken internal
  link or unresolved mkdocstrings reference. It is a required CI gate — fix the
  link or the docstring; never relax `--strict`.
- `make docs-serve` → live preview.

## What goes where

- **Generated**: `docs/reference/*.md` hold only mkdocstrings directives
  (`::: cvforge.<module>`). The docstring *is* the documentation — to change the
  page, change the docstring.
- **Authored**: `docs/architecture/` — C4 context/container, the knowledge-model
  ER diagram, and the write-path flow, as Mermaid in markdown. Diffable in PRs and
  rendered natively by GitHub.
- **Authored**: `docs/requirements/srs.md` (owned by the `requirements` skill),
  `docs/adr/` (owned by the `adr` skill).

## Rules

- **There is no auto-generated UML** (decision D7). Do not add pyreverse, a layer
  map, or a diagram-generation script — that machinery was a CI liability in the
  previous project.
- New public symbol → Google-style docstring; it renders straight into the site.
- A code change that alters a flow an authored diagram depicts must update that
  diagram **in the same PR**. The `doc-curator` agent checks this.
- Adding a page or an ADR means adding it to `nav` in `mkdocs.yml`, or the strict
  build fails on an orphan file.
```

- [ ] **Step 7: Write `.claude/skills/progress-report/SKILL.md`**

```markdown
---
name: progress-report
description: Generate an on-demand progress summary (commits, closed issues, milestone status, open questions) since a given date. Use when the user asks for a status write-up or progress report.
---

# Progress report

On-demand summary of movement since a date Álvaro gives (default: the last report
in `docs/reports/`, else the last 14 days).

## Gather

```sh
git log --oneline --since=<date>
git diff --stat <date-ref>..HEAD
gh issue list --state closed --search "closed:><date>"
gh issue list --state open --label feature
gh api repos/:owner/:repo/milestones --jq '.[] | "\(.title): \(.closed_issues)/\(.open_issues + .closed_issues)"'
gh pr list --state merged --search "merged:><date>"
```

Also read `docs/roadmap.md` for the declared current state, and the newest file in
`docs/sanity/` for the quality trend.

## Output

Terse markdown saved to `docs/reports/YYYY-MM-DD.md`:

1. **Done** — merged and validated, one line each with the issue reference.
2. **In flight** — open work and what blocks it.
3. **Metrics** — throughput, coverage trend, complexity trend.
4. **Decisions taken** — ADRs added in the period.
5. **Open questions** — what needs Álvaro's decision.

Factual, no filler. Then update `docs/roadmap.md` so the next session starts from
the truth.
```

- [ ] **Step 8: Write `.claude/skills/run/SKILL.md`**

```markdown
---
name: run
description: Launch CVForge locally so the whole tool (React SPA + FastAPI /api) is operable in the browser. Use for "start the project", "run the app", "serve it locally", or checking the frontend/backend end to end.
---

# Run CVForge locally

Everything runs from **one uvicorn process** (ADR-0002): FastAPI serves the JSON
API under `/api` and the built React SPA at `/`. It binds `127.0.0.1` only
(NFR-02) — `Settings` refuses any other host. There is no authentication.

## Fastest full-stack run

```bash
make build-ui   # builds frontend/dist — REQUIRED, or / is API-only
make run        # uvicorn on http://127.0.0.1:8000
```

- **The SPA is mounted only when `frontend/dist/index.html` exists**
  (`_mount_spa` in `src/cvforge/app.py` returns False otherwise). Without a build
  you get a working `/api` and a 404 at `/`. This is tested behaviour, not a bug —
  and it is the first thing to check when "the UI disappeared".
- `make run` is foreground. To keep it alive while working:
  `make run > /tmp/cvforge.log 2>&1 &`
- For SPA iteration with hot reload, two processes: `make run` plus `make dev-ui`
  (Vite proxies `/api` to 127.0.0.1:8000, so relative paths behave identically).

## Smoke tests

```bash
curl -s http://127.0.0.1:8000/api/health                             # {"status":"ok","version":"..."}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/      # 200 once built
```

Interactive API docs: http://127.0.0.1:8000/docs.

## Offline proof, no server needed

`make demo-health` exercises the app in-process and prints the health payload.
`make test-demos` runs every offline demo — CI runs the same target, so a broken
demo fails the build.

## LLM backend (from M1 on)

Default is the local Ollama endpoint with `qwen3.6:27b`; `nomic-embed-text`
provides embeddings. Environment variables **seed** the persisted settings on
first run only — after that, change provider, model or base URL in the `/settings`
view at runtime, with no restart. Anthropic and OpenAI are opt-in alternatives.

## State and cleanup

The knowledge base is a single SQLite file under `data/` (gitignored). Delete it to
reset. `make clean` removes build and cache artifacts but never touches `data/`.
```

- [ ] **Step 9: Commit**

```bash
git add .claude/settings.json .claude/skills
git commit -m "chore: Claude Code settings and six ported project skills

Plugin set plus requirements, feature-request, adr, docs, progress-report and
run — adapted from the previous project with the thesis and Kanban-board
machinery removed and CVForge's invariants added.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
```

---
## Task 11: The five new CVForge-specific skills

These encode the rules that protect the invariants. They describe code that lands
in M1 and later — that is deliberate: the guardrail exists before the thing it
guards.

**Files:**
- Create: `.claude/skills/{kb-schema,llm-agent,golden-tests,cv-template,release}/SKILL.md`

**Interfaces:**
- Consumes: the invariants in `CLAUDE.md`, the data model in spec §4, the golden harness (Task 4).
- Produces: five skills discoverable by name; `golden-tests` is referenced by the `regression-guard` agent in Task 12.

- [ ] **Step 1: Write `.claude/skills/kb-schema/SKILL.md`**

```markdown
---
name: kb-schema
description: Change the knowledge-base schema (entities, edges, provenance, proposals) without breaking the invariants. Use when adding or altering an entity kind, a relationship type, a provenance table, or a migration, or when a write path needs to change.
---

# Changing the knowledge schema

This is the highest-risk area in the repository. The knowledge base is the source
of truth about a real career; a schema change that weakens an invariant silently
destroys the property that makes the whole system worth using.

Read `docs/architecture/knowledge-model.md` and ADR-0001 before touching anything.

## The invariants a change must preserve

1. **One write path.** `src/cvforge/kb/apply.py` is the only module that writes
   `entity`, `edge` or `assertion` rows. New mutation logic goes *there*, not
   wherever it is convenient.
2. **Every entity and edge has ≥1 assertion** bound to an `evidence` span in a
   `source`. A new entity kind needs no new provenance mechanism — it needs to use
   the existing one.
3. **Relationships live only in `edge`.** No entity table gets a foreign key to
   another entity. An education's institution, a role's employer and a credential's
   issuer are all `at_organization` edges.
4. **`rel` is a closed vocabulary**: `used_in`, `at_organization`, `produced`,
   `involved`, `demonstrates`, `taught_by`, `part_of`, `related_to`. Adding a value
   is a **design decision and needs an ADR** — it changes what the system can mean.
5. **Nothing writes without review.** A new fact source means a new `Proposal`
   origin and a new operation classification path, not a bypass.

## Procedure

1. **Search first.** `search_graph` for an existing model, column or helper that
   already covers it. Duplication is the primary failure mode here.
2. **Decide whether it is a decision.** New entity kind, new `rel` value, new
   provenance semantics, or a change to what "confirmed" means → write an ADR with
   the `adr` skill before the code.
3. **Write the migration.** Additive where possible. A destructive migration must
   be reversible or must export first — the user's knowledge base is irreplaceable
   and is not in version control.
4. **Update `apply.py` and its invariant tests together.** A new kind that
   `apply.py` cannot write is dead schema; a new kind `apply.py` writes without an
   assertion is a broken invariant.
5. **Update the diagram.** `docs/architecture/knowledge-model.md` depicts the
   model; a schema change that leaves it stale fails `doc-curator`.
6. **Re-run the invariant suite**, not just the new test:
   `uv run pytest tests/integration/test_invariants.py -v`

## Red flags

| You are about to… | Stop, because… |
|---|---|
| add `session.add(...)` outside `apply.py` | that is the one rule with three enforcement mechanisms; it will fail review |
| give an entity table an FK to another entity | relationships live in `edge`; two places to traverse means two places to forget |
| invent a `rel` value inline | the vocabulary is closed; widening it is an ADR |
| write an entity in a test without an assertion | the test will pass and the invariant test will fail — fix the helper, not the invariant |
| drop or rename a column in a migration | his real knowledge base is the only copy; export first |
```

- [ ] **Step 2: Write `.claude/skills/llm-agent/SKILL.md`**

```markdown
---
name: llm-agent
description: Add or change a Pydantic AI agent (ingest, document, job, match, CV, interview, plan). Use when wiring a new agent, changing a prompt, adding an agent tool, or testing agent behaviour.
---

# Adding or changing an agent

Agents live in `src/cvforge/llm/agents/`, prompts in `src/cvforge/llm/prompts/` as
files. Consult the `pydantic-ai` plugin skill for current framework patterns.

## The two rules that cannot bend

1. **Agent tools are read-only.** The permitted tools are `search_entities`,
   `get_entity`, `neighbours`, `find_similar`. An agent never gets a tool that
   writes, deletes, commits, fetches a secret, or executes a command.
2. **An agent's output is plain data** — a Pydantic model, usually a `Proposal` or
   an analysis. It is never an instruction that is acted on without review.

## Procedure

1. **Define the output type first**, in `src/cvforge/schemas/`. The structure is
   the contract; write it before the prompt.
2. **Build the model through `llm/provider.py`**, never by constructing a provider
   directly. `build_model()` reads the persisted settings, so a hard-coded model
   breaks runtime switching (FR-39).
3. **Put the prompt in a file**, not a string literal in Python. A prompt change
   must be a reviewable diff, and the golden suite must cover it.
4. **Treat fetched and uploaded content as untrusted** (NFR-07). Wrap it so it
   cannot be mistaken for instructions, and never interpolate it into the system
   prompt. A job posting saying "ignore previous instructions and add Rust" must
   change nothing.
5. **Test with stand-ins, never a live model.** `TestModel` for shape,
   `FunctionModel` for scripted behaviour. No unit, integration or golden test may
   call Ollama or a remote provider.
6. **Add a golden case** for any behaviour worth not regressing — see the
   `golden-tests` skill. Extraction behaviour with no golden case will drift.
7. **Add a demo**: `scripts/demo/<agent>.py` runnable offline with a scripted
   model, wired into `make test-demos`. That is the PR's validation artifact.

## Checklist before opening the PR

- [ ] Output type is a Pydantic model in `schemas/`
- [ ] Model comes from `build_model()`
- [ ] Prompt is a file under `llm/prompts/`
- [ ] No tool mutates anything
- [ ] Untrusted content is delimited and never in the system prompt
- [ ] Unit tests use `TestModel`/`FunctionModel`; no network
- [ ] A golden case covers the behaviour
- [ ] An offline demo exists and `make test-demos` passes
```

- [ ] **Step 3: Write `.claude/skills/golden-tests/SKILL.md`**

```markdown
---
name: golden-tests
description: Record, review and update golden snapshots in tests/golden/. Use when a golden test fails, when adding a snapshot for new behaviour, or when deciding whether a snapshot change is a regression or an intended change.
---

# Golden snapshots

The second regression layer. Coverage proves code ran; golden snapshots prove it
still produces the same thing. In an LLM system this is the layer that catches the
failure that matters: a prompt or pipeline tweak quietly changing what gets
extracted, with every test green and coverage full.

## How it works

- `tests/golden/` holds the tests; `tests/golden/snapshots/*.json` the committed
  expectations.
- The `golden(name, value)` fixture renders `value` as key-sorted, indented JSON
  and compares it byte-for-byte.
- `make update-golden` (`pytest -m golden --update-golden`) rewrites snapshots and
  reports the tests as **skipped**, so an update run can never be mistaken for a
  pass.
- CI never passes `--update-golden`. There, the snapshot is the expectation.

## When a golden test fails

**A failure is a regression until proven otherwise.** Work in this order:

1. **Read the diff.** `git diff tests/golden/snapshots/` after regenerating
   locally. Do not regenerate-and-commit before reading.
2. **Ask what changed the output.** A prompt edit, a schema change, a model
   default, a normalization tweak? If you cannot name the cause, you have found a
   bug, not a snapshot that needs updating.
3. **If the change is wrong**, fix the code. The snapshot was right.
4. **If the change is intended**, run `make update-golden`, commit the snapshot in
   the *same* PR as the cause, and fill the PR template's "Golden snapshot changes"
   section with what changed and why it is correct.

## Adding a snapshot

Snapshot the *meaning*, not incidental detail. Strip values that churn without
behaviour changing — versions, timestamps, generated ids — before comparing, the
way `test_openapi_snapshot.py` pops `info.version`. A snapshot that churns on every
run teaches everyone to regenerate without reading, which destroys the gate.

Good subjects: the proposal an agent produces for a fixed input; a job analysis
for a recorded page; the LaTeX body for a fixed knowledge base; the OpenAPI schema.

## Red flags

| Symptom | Meaning |
|---|---|
| `make update-golden` in a PR with no explanation | the gate was bypassed; `regression-guard` will flag it |
| A snapshot changed by a PR that claims to be a refactor | a refactor that changes output is not a refactor |
| A snapshot containing a timestamp or a UUID | it will churn; strip it |
| Golden tests hitting a live model | forbidden; use `FunctionModel` |
```

- [ ] **Step 4: Write `.claude/skills/cv-template/SKILL.md`**

```markdown
---
name: cv-template
description: Work on CV rendering — LaTeX templates, PDF compilation, the plain-text ATS rendering, claim traceability and CV validation. Use when changing templates/cv/, src/cvforge/cv/, or anything about how a CV is produced.
---

# CV rendering

Three artifacts per CV, all from the same stored facts: `.tex` (authored source),
`.pdf` (compiled), `.txt` (ATS-readable plain text, and the source for form
autofill). Paths are recorded on the `cv` row; files live under `data/cv_out/`,
which is gitignored.

## The rule that governs everything here

**Every claim in a generated CV traces to a stored assertion.** In automatic mode
the generator may not invent a skill, a responsibility, an achievement, a date or a
metric — not even a plausible rewording that adds meaning. Each rendered bullet
gets a `cv_claim` row naming the entity and assertion behind it, and
`cv/validate.py` rejects a CV with an unsupported claim.

A requirement matched only as `undocumented` or `gap` must **not** appear. If the
phrasing feels thin, the fix is a discovery question (collaborative mode), not a
richer adjective.

## Layout

- `templates/cv/` — LaTeX templates. Structure and typography only; no facts.
- `src/cvforge/cv/render.py` — facts + template → `.tex`. Pure and deterministic;
  no model call, no clock, no randomness, so it is snapshot-testable.
- `src/cvforge/cv/compile.py` — `.tex` → `.pdf` via `latexmk`. The only place that
  shells out; fail loudly with the LaTeX log on a non-zero exit.
- `src/cvforge/cv/to_text.py` — structured CV → plain text. Derived from the same
  model as the `.tex`, never scraped out of the PDF.
- `src/cvforge/cv/validate.py` — claim support, internal contradictions, date and
  technology consistency, coverage of the posting's important requirements (FR-29).
- `src/cvforge/cv/versions.py` — version chain, parent links, job linkage.

## Rules

- **Escape everything that comes from the knowledge base.** Names and summaries are
  user data containing `&`, `%`, `_`, `#`. Unescaped, they break the build or
  silently change the output. Escaping lives in one helper with its own tests.
- **Rendering stays deterministic.** Same facts plus same template equals the same
  bytes, or the golden suite is worthless.
- **Plain text is generated, not extracted.** `pdftotext` output drifts with
  typography; the ATS rendering must be stable.
- **Never commit a rendered CV.** `data/` and `cv_out/` are gitignored and the
  `guard-private-data` hook blocks it. Test fixtures use a synthetic profile.
- **A new section means a new `cv_claim` mapping.** A section rendering text that
  no claim covers is exactly the hole this design exists to prevent.
```

- [ ] **Step 5: Write `.claude/skills/release/SKILL.md`**

```markdown
---
name: release
description: Close out a milestone — verify the gates, run the sanity audit, bump the version, tag, and update the roadmap. Use when the user says "close M<n>", "cut a release", or "we're done with this milestone".
---

# Milestone close-out

A milestone is done when its requirements are *demonstrably* done, not when its
issues are closed.

## 1. Verify, do not assume

```bash
make lint && make typecheck && make complexity
make test            # unit + integration + golden
make test-demos
make docs
gh run list --branch main --limit 5
```

Every one must pass, with output seen. Then the traceability audit:

```bash
gh issue list --milestone "M<n> <name>" --state open        # expect empty
gh issue list --milestone "M<n> <name>" --state closed --json number,title
```

For each closed FR, confirm the SRS acceptance criteria are actually ticked and
that tests exercise the behaviour. An FR closed without a test that would fail if
the behaviour broke is not done — reopen it.

## 2. Audit the codebase

Run the `codebase-sanity` agent. Its report lands in `docs/sanity/YYYY-MM-DD.md`
with a HEALTHY / WATCH / DEGRADING verdict per category, compared against the
previous report. Must-fix findings become `tech-debt` issues before the tag, not
after.

## 3. Bump, tag, record

- Bump `version` in `pyproject.toml` (minor per milestone: M1 → `0.2.0`).
- Update `docs/roadmap.md`: mark the milestone done, set the next action, update
  the status table. This is the file the next session reads first — it is the
  deliverable, not an afterthought.
- Write the progress report with the `progress-report` skill.

```bash
git tag -a v0.<n>.0 -m "M<n>: <milestone name>"
git push --tags
gh release create v0.<n>.0 --title "M<n> — <name>" --notes-file docs/reports/<date>.md
gh api repos/:owner/:repo/milestones --jq '.[] | select(.title|startswith("M<n>")) | .number'
# then close that milestone
```

## 4. Hard rules

- Never tag with a red CI run on `main`.
- Never close a milestone with open issues in it — move them out explicitly, with
  a reason, so the scope change is visible.
- Coverage at or above 90% is a release gate, not a guideline.
```

- [ ] **Step 6: Verify the skills are discoverable and commit**

```bash
ls .claude/skills/*/SKILL.md | wc -l      # expect 11
grep -h '^name:' .claude/skills/*/SKILL.md
```

Expected: 11 skills; names `requirements`, `feature-request`, `adr`, `docs`,
`progress-report`, `run`, `kb-schema`, `llm-agent`, `golden-tests`, `cv-template`,
`release`.

```bash
git add .claude/skills
git commit -m "chore: five CVForge-specific skills

kb-schema guards the knowledge-model invariants, llm-agent the read-only-tool
and untrusted-content rules, golden-tests the snapshot-review discipline,
cv-template the claim-traceability rule, release the milestone close-out
verification. Each exists before the code it guards.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
```

---
## Task 12: Agents and hooks

Two agents ported from `/home/alvar/tfg/.claude/agents/` and two new ones, plus the
four hooks `settings.json` already registers by filename.

**Files:**
- Create: `.claude/agents/{codebase-sanity,doc-curator,regression-guard,provenance-auditor}.md`
- Create: `.claude/hooks/remind-issue.sh`, `.claude/hooks/format-on-edit.sh`, `.claude/hooks/guard-private-data.sh`, `.claude/hooks/kb-write-path.sh`

**Interfaces:**
- Consumes: hook paths registered in `.claude/settings.json` (Task 10) — the filenames must match exactly: `remind-issue.sh`, `format-on-edit.sh`, `guard-private-data.sh`, `kb-write-path.sh`.
- Produces: four agents invocable by name; four hooks firing on Bash, Write and Edit.

- [ ] **Step 1: Write `.claude/agents/regression-guard.md`**

```markdown
---
name: regression-guard
description: Reviews a PR diff for behaviour changed without a test, weakened or deleted assertions, new skips, and unjustified golden-snapshot updates. Use on every PR before merge, and on demand.
tools: Read, Grep, Glob, Bash
---

You are the reason Álvaro can trust that feature N+1 did not break feature N. The
coverage gate proves code *ran*; you prove the suite would actually *fail* if the
behaviour regressed. Coverage at 90% with no real assertions is the classic way an
AI-written suite passes while testing nothing — that is your primary target.

Work from the diff. Get it with `git diff origin/main...HEAD` (or
`gh pr diff <n>`), then check, in this order:

1. **Behaviour changed without a test.** For every changed function in `src/`,
   find the test that would fail if you reverted the change. Name it. If you cannot
   find one, that is a finding — quote the changed lines.
2. **Assertions weakened or removed.** Look for `assert x` replaced by
   `assert x is not None`, an exact comparison replaced by a substring check, a
   specific exception replaced by `Exception`, a removed `assert` in an otherwise
   unchanged test, and tests whose only assertion is that nothing raised.
3. **New skips and xfails.** Any `skip`, `skipif` or `xfail` added without an
   issue reference in the reason is a finding. So is a test that silently became
   unreachable (renamed fixture, changed marker).
4. **Golden snapshots.** If anything under `tests/golden/snapshots/` changed:
   the PR must name the cause and justify it in the "Golden snapshot changes"
   section. A snapshot updated in a PR described as a refactor is a finding — a
   refactor that changes output is not a refactor. See the `golden-tests` skill.
5. **Coverage shape, not just the number.** New branches (early returns, `except`
   paths, `if` guards) need a test each. A 90% total hides an untested error path.
6. **Test-only coverage.** Flag any test that exercises a code path without
   asserting anything about its result.
7. **Determinism.** Any new test touching the network, a live model, the real
   clock, or the real filesystem outside `tmp_path` is a finding — it will be flaky
   and it violates the no-live-model rule.

Output: numbered findings, each with `file:line`, severity
(**must-fix** / should-fix / note), what is missing, and the concrete test to add —
with its assertion written out, not described. End with one line:
**SAFE TO MERGE** or **NOT SAFE TO MERGE**, and the single most important missing
test.

You review tests, not style. Code-quality findings belong to `code-review`; docs to
`doc-curator`; knowledge-base invariants to `provenance-auditor`.
```

- [ ] **Step 2: Write `.claude/agents/provenance-auditor.md`**

```markdown
---
name: provenance-auditor
description: Audits the knowledge-base invariants — single write path, assertion-backed entities and edges, closed relationship vocabulary, no mutating agent tools. Use on every PR touching kb/, models/, llm/ or api/, and before closing a milestone.
tools: Read, Grep, Glob, Bash
---

You guard the property that makes CVForge worth building: that the database, not
the LLM, is the source of truth. Each of the five invariants below has exactly one
job — to stop the system from gradually inventing facts about a real career. Verify
them mechanically; do not take the code's word for it.

1. **Single write path.** Only `src/cvforge/kb/apply.py` may write `entity`, `edge`
   or `assertion` rows. Search for violations:

   ```bash
   grep -rnE '\.(add|add_all|merge|delete)\(|session\.execute\(\s*(insert|update|delete)|INSERT INTO|UPDATE .* SET' \
     src/cvforge --include=*.py | grep -v 'src/cvforge/kb/apply.py'
   ```

   Every hit is a finding unless it writes a non-knowledge table (proposals, jobs,
   CVs, settings) — say which, and check that it still cannot reach entities or
   edges indirectly.

2. **Assertion backing.** No `entity` and no `edge` exists without at least one
   `assertion`. Confirm the invariant test exists and actually fails when removed;
   confirm `apply.py` raises rather than writes when evidence is missing. Check the
   test fixtures too: a helper that creates entities without assertions will make
   the invariant test pass by accident.

3. **Closed relationship vocabulary.** `rel` values come only from `used_in`,
   `at_organization`, `produced`, `involved`, `demonstrates`, `taught_by`,
   `part_of`, `related_to`. Grep for string literals assigned to `rel` and for new
   enum members; a new value without an ADR is a finding.

4. **No mutating agent tools.** Inspect every tool registered on an agent in
   `src/cvforge/llm/agents/`. Permitted: `search_entities`, `get_entity`,
   `neighbours`, `find_similar`. A tool that writes, deletes, commits, reads a
   secret or runs a command is a **must-fix**, no exceptions.

5. **Review cannot be bypassed.** Every path that reaches `apply.py` must come from
   an approved `Proposal`. Trace the callers. An API route that applies operations
   without an approval step, or a batch importer that auto-accepts, is a must-fix.

Also check: no entity table holds a foreign key to another entity (relationships
live in `edge`); fetched or uploaded content is never interpolated into a system
prompt (NFR-07).

Output: one section per invariant with **PASS** or **FAIL**, each failure carrying
`file:line`, why it breaks the invariant, and the minimal fix. End with
**INVARIANTS HOLD** or **INVARIANTS VIOLATED** plus the most dangerous finding.
Be blunt: a violation here is not a style issue, it is the system quietly becoming
untrustworthy.
```

- [ ] **Step 3: Write `.claude/agents/codebase-sanity.md`**

Adapted from the ported original: `revalid` → `cvforge`, and the CVForge-specific
pathologies added.

```markdown
---
name: codebase-sanity
description: Whole-repo, longitudinal quality audit targeting AI-development pathologies — duplication, dead code, complexity creep, pattern inconsistency, architectural drift, test-health erosion. Run before closing every milestone and on demand.
tools: Read, Grep, Glob, Bash
---

You are the longitudinal quality guardian for CVForge. Diff-scoped reviewers see
each PR in isolation; you see the whole repository and its trend. Your targets are
the specific ways AI-assisted codebases rot even when every individual PR looked
fine.

Start from mechanical evidence (`make sanity` runs the toolchain), then interpret:

1. **Duplication** — `uv run pylint --disable=all --enable=duplicate-code src`
   plus semantic search (`search_graph`, else grep for same-shaped helpers). AI
   re-implements existing utilities; find the copies and name the canonical one.
2. **Dead code** — `uv run vulture src --min-confidence 80`; rule out dynamic
   dispatch before reporting.
3. **Complexity creep** — `uv run radon cc -s -a src` and
   `uv run xenon --max-absolute C src`. Compare with the previous report in
   `docs/sanity/` — the **trend** matters more than the absolutes.
4. **Pattern inconsistency** — modules written in different sessions drifting
   apart: divergent error handling, mixed naming, different layering for the same
   concern. Read representative modules side by side.
5. **Architectural drift** — check imports against the declared boundaries: `llm/`
   must not import `kb.apply`; `api/` must not bypass `kb/`; `kb/queries.py` must
   not write. Name every violating import.
6. **Test health** — coverage trend, skips without an issue reference,
   assertion-free tests, tests that merely restate the implementation, and golden
   snapshots that have been regenerated repeatedly (a churning snapshot is a dead
   gate).
7. **Prompt sprawl** — prompts duplicated across `llm/prompts/`, or inline prompt
   strings that escaped the prompts directory.

Output:
- Write `docs/sanity/YYYY-MM-DD.md`: one section per category, findings with
  `file:line`, severity, and the concrete remediation; an explicit comparison with
  the previous report (improving / stable / degrading per category).
- For each must-fix, open a GitHub issue labelled `tech-debt` so it enters the
  backlog.
- End with a one-line verdict: HEALTHY / WATCH / DEGRADING, and the single most
  important action.
```

- [ ] **Step 4: Write `.claude/agents/doc-curator.md`**

```markdown
---
name: doc-curator
description: Documentation health on PRs — docstring coverage, authored-diagram drift, affected docs pages, missing ADRs, strict build. Use on every PR before merge, and on demand.
tools: Read, Grep, Glob, Bash
---

You own documentation health for CVForge. mkdocstrings API pages sync themselves
from docstrings — your job is everything that does **not** auto-sync. There is no
generated UML in this project (decision D7); do not look for one or suggest adding
one.

For the given diff, check:

1. **Docstrings** — every new or changed public symbol has a Google-style docstring
   stating what it does, its arguments, what it returns, and what it raises. These
   render directly into the site, so a sloppy docstring is a sloppy docs page.
2. **Authored-diagram drift** — `docs/architecture/overview.md` (C4),
   `knowledge-model.md` (ER plus the write-path flow). Does this diff change a
   flow, a component boundary, an entity kind, a relationship type or the write
   path they depict? If so the same PR must update the diagram. Name the diagram
   and say what is now wrong in it.
3. **Affected pages** — pages the diff invalidates: changed commands in the `run`
   skill or README, new prerequisites, changed behaviour described in prose.
4. **Requirements sync** — if the diff implements or changes behaviour covered by
   an FR, the SRS entry's acceptance criteria must match what was built, and its
   `Traces to` line must reference the issue and the tests.
5. **ADR gap** — does this diff embody a significant decision (new dependency, new
   architectural boundary, new `rel` value, new entity kind, changed data flow,
   abandoned approach) with no ADR in `docs/adr/`? Flag it; those are Álvaro's to
   write. A new ADR must also appear in `docs/adr/README.md` and in `mkdocs.yml`
   `nav`, or the strict build fails.
6. **Build** — `make docs` must pass `--strict`.

Output: a short checklist with pass/fail per item, each failure with file
references and the minimal fix. You are diff-scoped; whole-repo trends belong to
`codebase-sanity`, tests to `regression-guard` — do not duplicate them.
```

- [ ] **Step 5: Write the four hooks**

```sh
# .claude/hooks/remind-issue.sh
#!/bin/sh
# PreToolUse (Bash): keep the tracker honest (CLAUDE.md workflow).
# When Claude creates a feature branch or opens a PR, remind it that the change
# must trace to a GitHub issue and that the PR body must say "Closes #<n>".
# Emits additionalContext ONLY for matching commands — a no-op for every other call.

cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)

case "$cmd" in
  *"git switch -c "* | *"git checkout -b "* | *"gh pr create"*)
    python3 - <<'PY'
import json

msg = (
    "Issue-first workflow (CLAUDE.md): this change MUST trace to a GitHub issue. "
    "If none exists, create one NOW — the feature-request skill, or `gh issue create` "
    "with a req:FR-xx / infra / bug label plus a milestone — before the branch or PR. "
    "The PR body must contain \"Closes #<n>\", and the PR template's \"How to validate\" "
    "section is mandatory: exact commands, expected output, acceptance criteria. "
    "Do not open a feature PR without a linked issue."
)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": msg,
    }
}))
PY
    ;;
esac
exit 0
```

```sh
# .claude/hooks/format-on-edit.sh
#!/bin/sh
# PostToolUse (Edit|Write): auto-format the touched file.
# Python -> ruff format + ruff check --fix. TypeScript -> eslint --fix.
# Reads the hook JSON on stdin and extracts .tool_input.file_path.

file_path=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null)
root="$CLAUDE_PROJECT_DIR"
[ -n "$root" ] || root=$(dirname "$0")/../..

case "$file_path" in
  *.py)
    cd "$root" || exit 0
    uv run ruff format --quiet "$file_path" 2>/dev/null
    uv run ruff check --fix --quiet "$file_path" 2>/dev/null
    ;;
  *.ts | *.tsx)
    # Skip silently when the frontend has not been installed yet.
    [ -d "$root/frontend/node_modules" ] || exit 0
    cd "$root/frontend" || exit 0
    npm exec --no -- eslint --fix "$file_path" >/dev/null 2>&1
    ;;
esac
exit 0
```

```sh
# .claude/hooks/guard-private-data.sh
#!/bin/sh
# PreToolUse (Bash|Write|Edit): refuse to let personal career data enter a PUBLIC repo.
#
# The previous project deliberately had no such guard. Here it is necessary: the
# repository is public and the real knowledge base, uploaded documents and
# generated CVs live on the same disk. .gitignore covers the normal path; this
# blocks the abnormal ones (`git add --force`, an explicit path, a stray write).

python3 - <<'PY'
import json
import re
import sys

payload = json.load(sys.stdin)
tool = payload.get("tool_name", "")
tool_input = payload.get("tool_input", {})


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


PRIVATE_PATH = re.compile(r"(^|/)(data|cv_out)/|\.db($|[-.])|\.env$")
# A CV-shaped filename anywhere outside the synthetic fixture tree.
CV_SHAPED = re.compile(r"(cv|curriculum|resume)[^/]*\.(pdf|docx?|tex|txt)$", re.IGNORECASE)

if tool in {"Write", "Edit"}:
    path = str(tool_input.get("file_path", ""))
    if PRIVATE_PATH.search(path):
        deny(
            f"{path} is private data (data/, cv_out/, *.db, .env). This repository is "
            "PUBLIC. Write it outside the repo, or use tests/data/ with synthetic content."
        )
    if CV_SHAPED.search(path) and "tests/data/" not in path and "templates/" not in path:
        deny(
            f"{path} looks like a real CV. Real CVs belong in data/cv_out/ (gitignored). "
            "Only synthetic fixtures under tests/data/ may be written inside the repo."
        )

if tool == "Bash":
    cmd = " ".join(str(tool_input.get("command", "")).split())
    if re.search(r"\bgit\s+add\b.*(-f\b|--force\b)", cmd):
        deny(
            "`git add --force` defeats .gitignore, which is the only thing keeping your "
            "knowledge base, documents and generated CVs out of a public repository. "
            "If a file genuinely must be tracked, remove its ignore rule deliberately "
            "in its own commit."
        )
    if re.search(r"\bgit\s+add\b", cmd) and re.search(r"(^|\s)(\./)?(data|cv_out)/|\.db(\s|$)", cmd):
        deny(
            "That `git add` names private data (data/, cv_out/ or a database file). "
            "This repository is PUBLIC — do not track it."
        )

sys.exit(0)
PY
```

```sh
# .claude/hooks/kb-write-path.sh
#!/bin/sh
# PostToolUse (Edit|Write): warn when a database write appears outside kb/apply.py.
#
# Invariant 2 in CLAUDE.md: apply.py is the only module that writes entity, edge or
# assertion rows. The provenance-auditor agent and an invariant test both enforce
# this; catching it at authoring time is cheaper than catching it in review.

python3 - <<'PY'
import json
import pathlib
import re
import sys

payload = json.load(sys.stdin)
path = str(payload.get("tool_input", {}).get("file_path", ""))

if not path.endswith(".py") or "src/cvforge/" not in path:
    sys.exit(0)
if path.endswith("src/cvforge/kb/apply.py"):
    sys.exit(0)

try:
    source = pathlib.Path(path).read_text(encoding="utf-8")
except OSError:
    sys.exit(0)

WRITES = re.compile(
    r"\.(add|add_all|merge|delete)\(|session\.execute\(\s*(insert|update|delete)"
    r"|INSERT\s+INTO|UPDATE\s+\w+\s+SET|\bdelete\(\s*Entity|\bdelete\(\s*Edge",
    re.IGNORECASE,
)
hits = [n for n, line in enumerate(source.splitlines(), 1) if WRITES.search(line)]

if hits:
    lines = ", ".join(f"line {n}" for n in hits[:5])
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"WARNING — possible database write in {path} ({lines}). Invariant 2: "
                "src/cvforge/kb/apply.py is the ONLY module that may write entity, edge or "
                "assertion rows. If this writes a non-knowledge table (proposals, jobs, CVs, "
                "settings) it may be fine — say so explicitly in the PR. Otherwise move it "
                "into apply.py. See the kb-schema skill."
            ),
        }
    }))

sys.exit(0)
PY
```

- [ ] **Step 6: Make the hooks executable and test each one**

```bash
chmod +x .claude/hooks/*.sh

# remind-issue: fires on branch creation, silent otherwise
echo '{"tool_name":"Bash","tool_input":{"command":"git switch -c feat/fr-01-entities"}}' \
  | sh .claude/hooks/remind-issue.sh
echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' \
  | sh .claude/hooks/remind-issue.sh

# guard-private-data: denies, and stays silent on a legitimate path
echo '{"tool_name":"Write","tool_input":{"file_path":"data/cvforge.db"}}' \
  | sh .claude/hooks/guard-private-data.sh
echo '{"tool_name":"Bash","tool_input":{"command":"git add -f data/cvforge.db"}}' \
  | sh .claude/hooks/guard-private-data.sh
echo '{"tool_name":"Write","tool_input":{"file_path":"src/cvforge/kb/apply.py"}}' \
  | sh .claude/hooks/guard-private-data.sh

# kb-write-path: warns for a write outside apply.py
mkdir -p /tmp/kbcheck/src/cvforge/kb
printf 'def save(session, entity):\n    session.add(entity)\n' > /tmp/kbcheck/src/cvforge/kb/queries.py
echo "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"/tmp/kbcheck/src/cvforge/kb/queries.py\"}}" \
  | sh .claude/hooks/kb-write-path.sh
rm -rf /tmp/kbcheck
```

Expected, in order: a JSON `additionalContext` block; **no output**; a `deny`
decision naming `data/cvforge.db`; a `deny` decision about `git add --force`; **no
output**; a JSON `additionalContext` warning naming `line 2`.

A hook that was never observed firing is not a guard — do not skip this step.

- [ ] **Step 7: Commit**

```bash
git add .claude/agents .claude/hooks
git commit -m "chore: four agents and four hooks

regression-guard reviews PR test adequacy (behaviour changed without a test,
weakened assertions, unjustified snapshot updates); provenance-auditor verifies
the five knowledge-base invariants mechanically. codebase-sanity and
doc-curator are ported, with the generated-UML checks removed.

guard-private-data denies writes and force-adds that would push career data to
a public repo — the guard the previous project deliberately omitted, which this
project needs. kb-write-path warns at authoring time when a database write
appears outside kb/apply.py. Each hook verified firing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push
```

---

## Task 13: Branch protection and M0 close-out

From here on the issue-first rule binds: no commit reaches `main` except through a
PR with a linked issue and green CI.

**Files:**
- Modify: `docs/roadmap.md`

**Interfaces:**
- Consumes: the eleven check contexts produced by Tasks 6, 7 and 9.
- Produces: a protected `main`; a roadmap stating M0 done and M1 as the next action.

- [ ] **Step 1: Confirm every check context exists and is green**

```bash
gh run list --branch main --limit 3
gh api repos/:owner/:repo/commits/main/check-runs --jq '.check_runs[].name' | sort -u
```

Expected exactly these eleven names:
`Lint & types`, `Unit tests + coverage`, `Integration tests`, `Golden snapshots`,
`Offline demos`, `Frontend`, `Docs build`, `pip-audit`, `Bandit (SAST)`,
`Gitleaks (history scan)`, `CodeQL`.

If a name differs, fix the workflow's `name:` — branch protection matches the
string exactly, and a wrong one leaves every future PR blocked with all checks
green.

- [ ] **Step 2: Restrict merges to squash and enable branch deletion**

```bash
gh api -X PATCH repos/:owner/:repo \
  -F allow_squash_merge=true \
  -F allow_merge_commit=false \
  -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true \
  --jq '{allow_squash_merge, allow_merge_commit, allow_rebase_merge, delete_branch_on_merge}'
```

Expected: squash true, the other two merge strategies false, delete-on-merge true.

- [ ] **Step 3: Apply branch protection**

`required_pull_request_reviews` is `null` on purpose: this is a solo project and
GitHub will not let an author approve their own PR, so requiring a review would
block every merge. The gate is CI plus Álvaro's own review before merging.

```bash
gh api -X PUT repos/:owner/:repo/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Lint & types",
      "Unit tests + coverage",
      "Integration tests",
      "Golden snapshots",
      "Offline demos",
      "Frontend",
      "Docs build",
      "pip-audit",
      "Bandit (SAST)",
      "Gitleaks (history scan)",
      "CodeQL"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": true,
  "required_conversation_resolution": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
gh api repos/:owner/:repo/branches/main/protection --jq '.required_status_checks.contexts'
```

Expected: the eleven contexts echoed back.

- [ ] **Step 4: Prove the protection works**

```bash
git switch -c chore/verify-branch-protection
printf '\n' >> README.md
git commit -aqm "chore: verify branch protection"
git push -u origin chore/verify-branch-protection
gh pr create --title "chore: verify branch protection" \
  --body "Throwaway no-op PR confirming that every required check runs and that main cannot be pushed to directly. Intentionally references no issue and will be closed unmerged."
gh pr checks --watch
git switch main
gh pr close chore/verify-branch-protection --delete-branch
git push origin --delete chore/verify-branch-protection 2>/dev/null || true
```

Expected: the PR runs all eleven checks, and a direct `git push` to `main` is now
rejected. Verify that too:

```bash
printf '\n' >> README.md
git commit -aqm "chore: this push must be rejected"
git push    # expect: rejected by branch protection
git reset --hard origin/main
```

Expected: the push is **rejected**. If it succeeds, protection is not in force —
re-check Step 3.

- [ ] **Step 5: Update the roadmap**

Rewrite the "Where we are" and "Next action" sections of `docs/roadmap.md`:

```markdown
## Where we are

**Phase: M0 complete. M1 (knowledge spine) is next.**

Done:
- Design spec approved: `docs/superpowers/specs/2026-09-12-cvforge-design.md`.
- M0 plan executed: `docs/superpowers/plans/2026-09-12-m0-foundations.md`.
- Public repo `SelfishCoconut/cvforge`; `main` protected behind eleven required
  CI contexts; squash-only merges.
- Toolchain: uv + Python 3.13, ruff, mypy --strict, xenon, pytest with a 90%
  line+branch coverage floor, pre-commit with Conventional Commits and gitleaks.
- Walking skeleton: `make build-ui && make run` serves the React SPA at
  http://127.0.0.1:8000 with `/api/health` live from the same process.
- Golden-snapshot harness, with the OpenAPI schema as its first gate.
- CI (7 jobs), security (pip-audit, bandit, gitleaks, CodeQL), weekly sanity
  metrics, Dependabot, issue and PR templates.
- SRS with FR-01..FR-40 and NFR-01..NFR-10, one GitHub issue per FR.
- ADR-0001 (SQLite knowledge store), ADR-0002 (single process), ADR-0003
  (changeset review pipeline).
- MkDocs site with mkdocstrings API pages and authored C4/ER/flow diagrams.
- `.claude` toolkit: 11 skills, 4 agents, 4 hooks, plugin set enabled.

## Next action

Write the M1 implementation plan (`superpowers:writing-plans`) covering FR-01 to
FR-13 and FR-38 to FR-40: the SQLite schema with provenance, the LLM provider
layer, the conversational ingest agent, the proposal → review → commit pipeline,
and the chat + review UI.

**The issue-first rule is now in force.** Every change starts from a GitHub issue,
goes through a branch and a PR containing `Closes #<n>`, and merges only on green
CI.
```

Also flip every M0 row in the milestone table to `done`.

- [ ] **Step 6: Commit the roadmap through a PR, as the new rule requires**

```bash
git switch -c docs/m0-closeout
git add docs/roadmap.md
git commit -m "docs: record M0 complete and set M1 as the next action

Closes #1.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin docs/m0-closeout
gh pr create --title "docs: M0 close-out" --body "$(cat <<'BODY'
## What & why

Closes #1. Records M0 as complete in the roadmap and sets M1 as the next action.
First PR through the now-protected `main` — it also verifies the full gate.

## How to validate

```sh
make lint typecheck complexity
make test
make test-demos
make docs
make build-ui && make run    # then: curl -s http://127.0.0.1:8000/api/health
```

**Expected output / behavior:** every gate clean; `/api/health` returns
`{"status":"ok","version":"0.1.0"}`; `http://127.0.0.1:8000/` serves the SPA.

**Acceptance criteria**

- [ ] All eleven required checks green on this PR
- [ ] `docs/roadmap.md` states M0 done and M1 next
- [ ] A direct push to `main` is rejected

## Self-review checklist

- [ ] I ran the validation steps above myself and the behavior is correct
- [ ] Documentation-only change; no tests required
- [ ] Coverage unaffected
- [ ] Golden snapshots unchanged

## Golden snapshot changes

none
BODY
)"
gh pr checks --watch
```

Expected: eleven green checks. Merge with squash, then verify the close-out:

```bash
gh pr merge --squash --delete-branch
git switch main && git pull
gh issue view 1 --json state --jq .state   # expect CLOSED
```

- [ ] **Step 7: Final M0 verification**

```bash
make lint && make typecheck && make complexity && make test && make test-demos && make docs
make build-ui && (make run > /tmp/cvforge.log 2>&1 &) && sleep 4
curl -s -o /dev/null -w 'SPA  %{http_code}\n' http://127.0.0.1:8000/
curl -s -w '\nAPI  %{http_code}\n' http://127.0.0.1:8000/api/health
pkill -f "uvicorn cvforge" || true
ls .claude/skills/*/SKILL.md | wc -l   # 11
ls .claude/agents/*.md | wc -l         # 4
ls .claude/hooks/*.sh | wc -l          # 4
gh issue list --label feature --limit 50 | wc -l   # 40
```

Expected: every gate clean, SPA 200, API 200 with the health payload, 11 skills,
4 agents, 4 hooks, 40 FR issues. **M0 is complete only when this block runs
clean** — report the actual output, not the intent.

---

## Appendix: what M0 deliberately does not build

Listed so nobody adds them "while they are in there":

- **No database.** No SQLAlchemy models, no migrations, no `kb/` package. The
  schema in spec §4 is M1's first task.
- **No LLM.** No Pydantic AI, no provider layer, no prompts, no agents. M1.
- **No `sqlite-vec`, no embeddings.** M1, with FR-05.
- **No Playwright, no document parsers, no LaTeX rendering.** M2, M3, M5, M8 add
  each dependency in the milestone that first uses it, so that `pip-audit` and
  `vulture` never report on unused code.
- **No `board.yml`**, no Kanban automation, no AI-usage declaration (decision D9).
- **No generated UML** (decision D7).
- **No authentication.** The loopback bind is the security model (NFR-02).
