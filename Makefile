.PHONY: up up-local down logs seed secrets test web-check

# Публичный ключ организаторов хакатона (age): прочитать secrets.env.age могут только они.
AGE_RECIPIENT := age1932fu7f70rwyfhaxflyfszz4gf6avxwc95wc0yjwm6zns9tspycqpgdnc0

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

# Зашифровать .env.jury (отдельный ключ для жюри) → secrets.env.age. Нужен age: brew install age
secrets:
	age -r $(AGE_RECIPIENT) -o secrets.env.age .env.jury

test:
	python -m pytest

web-check:
	cd web && npm ci && npm run check
