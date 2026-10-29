"""Единая конфигурация. Импорт не запускает сеть и не создаёт базу."""
from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv
from app.core.model_config import load_model_config

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
MODEL_CONFIG = load_model_config(ROOT / 'config/models.yaml')

# Один переключатель модели для запуска (жюри, демо): LLM_PROVIDER=cloud|local|off.
#   cloud — полный разбор облачной моделью через OpenAI-совместимое API (CLOUD_LLM_*, LLM_API_KEY);
#           если она недоступна, запрос разбирают правила и гость видит пометку;
#   local — правила + локальная модель (gemma3:12b через Ollama) на том, что правила не поняли;
#   off   — только правила, без модели.
# Пусто — режимы из config/models.yaml. Явные PARSER_MODE/HYBRID_LLM сильнее переключателя.
PROVIDERS = {'cloud': ('groq', 'groq'), 'local': ('hybrid', 'ollama'), 'off': ('offline', None)}
LLM_PROVIDER = (os.getenv('LLM_PROVIDER') or '').strip().lower()
if LLM_PROVIDER and LLM_PROVIDER not in PROVIDERS:
    raise ValueError('LLM_PROVIDER должен быть cloud, local или off')
_PRESET = PROVIDERS.get(LLM_PROVIDER, (None, None))

# Операционное переопределение ML-режима: участник frontend может
# запустить PARSER_MODE=offline без загрузки весов и без правки общего YAML.
# Параметры генерации берутся только из версионируемого YAML.
PARSER_MODE = (os.getenv('PARSER_MODE') or _PRESET[0] or MODEL_CONFIG.parser_mode)
if PARSER_MODE not in ('ollama', 'groq', 'offline', 'fixture', 'hybrid'):
    raise ValueError('PARSER_MODE должен быть ollama, groq, offline, fixture или hybrid')


@dataclass(frozen=True)
class Settings:
    database_url: str = (os.getenv('DATABASE_URL') or f'sqlite:///{ROOT / "runtime/adler.db"}')
    parser_mode: str = PARSER_MODE
    llm_provider: str = LLM_PROVIDER
    # Облачный режим из переключателя не роняет поиск при недоступной модели (см. CloudWithRulesFallback).
    cloud_rules_fallback: bool = LLM_PROVIDER == 'cloud' and not os.getenv('PARSER_MODE')
    # Локальная модель: по умолчанию из YAML (gemma3:12b); LOCAL_LLM_MODEL — для своей Ollama.
    model_name: str = (os.getenv('LOCAL_LLM_MODEL') or MODEL_CONFIG.model_name)
    reply_parser_mode: str = (os.getenv('REPLY_PARSER_MODE') or MODEL_CONFIG.reply_parser_mode)
    ollama_url: str = (os.getenv('OLLAMA_URL') or 'http://127.0.0.1:11434')
    demo_mode: bool = (os.getenv('DEMO_MODE') or 'true').lower() == 'true'
    overpass_url: str = (os.getenv('OVERPASS_URL') or 'https://overpass-api.de/api/interpreter')
    openaq_api_key: str = os.getenv('OPENAQ_API_KEY', '')
    noisemodelling_home: str = os.getenv('NOISEMODELLING_HOME', '')
    noise_java_home: str = os.getenv('NOISE_JAVA_HOME', '')
    # LLM_API_KEY — ключ OpenAI-совместимого API; GROQ_API_KEY — прежнее имя, тоже работает.
    groq_api_key: str = (os.getenv('LLM_API_KEY') or os.getenv('GROQ_API_KEY', ''))
    # Любой OpenAI-совместимый провайдер вместо Groq: адрес и модель — локальное
    # переопределение из .env (ключ — в GROQ_API_KEY). По умолчанию — Groq и YAML.
    cloud_base_url: str = (os.getenv('CLOUD_LLM_BASE_URL') or 'https://api.groq.com/openai/v1').rstrip('/')
    groq_model: str = (os.getenv('CLOUD_LLM_MODEL') or MODEL_CONFIG.groq_model)
    parser_timeout_seconds: float = MODEL_CONFIG.parser_timeout_seconds
    ollama_num_ctx: int = MODEL_CONFIG.ollama_num_ctx
    ollama_think: bool | None = MODEL_CONFIG.ollama_think
    ollama_keep_alive: str = MODEL_CONFIG.ollama_keep_alive
    temperature: float = MODEL_CONFIG.temperature
    max_output_tokens: int = MODEL_CONFIG.max_output_tokens
    groq_reasoning_effort: str = MODEL_CONFIG.groq_reasoning_effort
    hybrid_llm: str = (os.getenv('HYBRID_LLM') or _PRESET[1] or MODEL_CONFIG.hybrid_llm)
    demo_dir: Path = ROOT / 'data/demo'
    environment_dir: Path = ROOT / 'data/environment'
    registry_path: Path = ROOT / 'app/features/registry.yaml'
    reply_fixture_path: Path = ROOT / 'data/demo/hotelier_reply_fixtures.json'
    max_tool_calls: int = 100


settings = Settings()
