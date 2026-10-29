.PHONY: up up-local down logs seed test web-check

# Запуск: модель выбирается в .env (LLM_PROVIDER=cloud|local|off)
up:
	docker compose up --build

# Локальная gemma3:12b в Docker (скачается при первом запуске, ~8 ГБ)
up-local:
	LLM_PROVIDER=local COMPOSE_PROFILES=local-llm docker compose up --build

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
