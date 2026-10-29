# Разбор запросов через Claude (claude-opus-5)

> **Это Claude.** Модель в этих замерах — `claude-opus-5` от Anthropic, облачная, вызывалась
> через OpenAI-совместимый прокси. Это НЕ локальная Gemma/Qwen из `config/models.yaml`
> и не модель по умолчанию: включается только локальным `.env`.

## Как включить

В локальном `.env` (он в `.gitignore`, ключ туда и только туда):

```bash
PARSER_MODE=groq                     # «groq» — исторически имя OpenAI-совместимого режима
CLOUD_LLM_BASE_URL=https://<ваш-прокси>/v1
CLOUD_LLM_MODEL=claude-opus-5
GROQ_API_KEY=<ваш личный ключ>
```

Docker: `compose.yaml` передаёт `PARSER_MODE`, `CLOUD_LLM_BASE_URL`, `CLOUD_LLM_MODEL`, `HYBRID_LLM`
и `GROQ_API_KEY` из `.env` в сервис `backend`; после правки `.env` — `docker compose up -d`.
Проверка: `curl localhost:8080/api/health` → `"parser_mode":"groq"`.

Режим `hybrid` с `HYBRID_LLM=groq` тоже работает, но с сильной моделью хуже: правила
оставляют свои ошибки, а LLM их не переопределяет. Убрать строки из `.env` — возврат к YAML.

## Результаты (requirement F1, 29.10.2026)

| Парсер | dev v2 (59) | тест v3 (60) |
|---|---|---|
| Gemma 3 12B, hybrid (по умолчанию) | 0.864 | 0.886 |
| **Claude opus-5, hybrid** | 0.881 | 0.893 |
| **Claude opus-5, только LLM** | **1.000** | **0.987** |

Ошибок контракта 0; медиана ответа ~2–2.5 с. Полные отчёты с каждым запросом:
[тест v3](examples/parser_claude_opus5_test_v3.json), [dev v2](examples/parser_claude_opus5_dev_v2.json)
(поле `generation_model: claude-opus-5`; `source: groq` — имя режима, не провайдер).

## Ограничения

- Разметку v2/v3 тоже писал Claude (coding assistant). Модель того же семейства легко
  совпадает с соглашениями разметки, поэтому ~0.99 завышено. Нужен тест от людей.
- Облако: текст запроса уходит внешнему провайдеру; нужна сеть и ключ. Для демо без
  сети остаются `hybrid` с локальной моделью и `offline`.
