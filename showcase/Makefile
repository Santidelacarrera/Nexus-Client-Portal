.PHONY: install build run test lint security db-roles
PY ?= python

install:
	$(PY) -m pip install -r requirements-dev.txt
	npm ci

build:
	npm run build

run:
	$(PY) -m uvicorn --factory src.main:app_factory --no-server-header --host 127.0.0.1 --port 8000

test:
	$(PY) -m pytest -q          # requiere TEST_ADMIN_DSN (PostgreSQL 16)
	npx jest

lint:
	npm run lint

security:
	bandit --ini .bandit -r src
	pip-audit -r requirements.txt
	npm audit --omit=dev --audit-level=high
	semgrep --config p/owasp-top-ten src   # desde .venv-semgrep; requiere acceso a semgrep.dev

db-roles:
	./scripts/db_roles.sh
