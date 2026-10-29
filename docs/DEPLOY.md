# Развёртывание на сервере (https://o.devneli.ru)

Сервер: Ubuntu 26.04, 2 CPU, 2 GB RAM (+2 GB swap), Docker 29 + Compose v5. Код — в `/opt/ostrovok`.
Снаружи открыты только 22, 80 и 443 (ufw). Caddy принимает 80/443, сам получает и продлевает
сертификат Let's Encrypt и проксирует на приложение; порт 8080 слушается только на localhost.

Файлы: [`deploy/docker-compose.vps.yml`](../deploy/docker-compose.vps.yml) (Caddy поверх основного compose),
[`deploy/Caddyfile`](../deploy/Caddyfile), [`deploy/env.vps.example`](../deploy/env.vps.example) — шаблон `.env` сервера.
В `.env` сервера `COMPOSE_FILE=docker-compose.yml:deploy/docker-compose.vps.yml`, поэтому там работают
обычные команды `docker compose …`.

## Ключ модели

```bash
ssh root@159.194.237.30
nano /opt/ostrovok/.env          # впишите LLM_API_KEY=…
cd /opt/ostrovok && docker compose up -d   # пересоздаст backend с новым ключом
curl -s https://o.devneli.ru/api/health    # поле llm — какая модель используется
```

Пока ключ пустой, запросы разбирают правила, а в выдаче есть пометка «Языковая модель сейчас недоступна».
Сайт публичный, поэтому каждый поиск расходует квоту ключа: для сервера лучше отдельный ключ с лимитом.

## Обновление кода

С машины разработчика, из корня репозитория (выкладываются только файлы из git, `.env` сервера не трогается):

```bash
git archive --format=tar HEAD | ssh root@159.194.237.30 'tar -x -C /opt/ostrovok'
ssh root@159.194.237.30 'cd /opt/ostrovok && docker compose up -d --build'
```

`tar` не удаляет файлы, удалённые из git, — при переименованиях удалите старые вручную.
База (ответы отельеров) хранится в томе `ostrovok_adler-data` и переживает обновления.

## Первичная установка (уже выполнена)

Docker из официального репозитория, swap 2 GB, `ufw allow 80/tcp`, `ufw allow 443/tcp`, затем:

```bash
mkdir -p /opt/ostrovok   # + выкладка кода, как в «Обновлении»
cd /opt/ostrovok && cp deploy/env.vps.example .env && chmod 600 .env
docker compose up -d --build
```

Логи: `docker compose logs -f backend` (строка «Разбор запросов: …» — какая модель), `docker compose logs caddy`.
