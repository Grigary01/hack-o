.PHONY: up down logs seed test

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f app api ui

seed:
	docker compose exec api python -m scripts.seed_demo

test:
	python -m pytest
