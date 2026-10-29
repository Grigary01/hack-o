.PHONY: up down logs seed test web-check

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f backend web

seed:
	docker compose exec backend python -m scripts.seed_demo

test:
	python -m pytest

web-check:
	cd web && npm ci && npm run check
