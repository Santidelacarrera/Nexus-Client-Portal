.PHONY: up down test test-backend test-frontend seed
up:            ## Levanta todo el stack (requiere .env)
	docker compose --env-file .env -f deploy/docker-compose.yml up --build
down:
	docker compose --env-file .env -f deploy/docker-compose.yml down
test: test-backend test-frontend
test-backend:
	cd backend && pytest -q
test-frontend:
	cd frontend && npm test -- --silent && npm run lint && npm run typecheck
seed:
	cd backend && python -m app.db.seed
