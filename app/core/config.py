"""Единая конфигурация. Импорт не запускает сеть и не создаёт базу."""
from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv
from app.core.model_config import load_model_config

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
MODEL_CONFIG = load_model_config(ROOT / 'config/models.yaml')

# Единственное операционное переопределение ML-режима: участник frontend может
# запустить PARSER_MODE=offline без загрузки весов и без правки общего YAML.
# Названия моделей и параметры генерации берутся только из версионируемого YAML.
PARSER_MODE = os.getenv('PARSER_MODE', MODEL_CONFIG.parser_mode)
if PARSER_MODE not in ('ollama', 'groq', 'offline', 'fixture', 'hybrid'):
    raise ValueError('PARSER_MODE должен быть ollama, groq, offline, fixture или hybrid')


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "runtime/adler.db"}')
    parser_mode: str = PARSER_MODE
    model_name: str = MODEL_CONFIG.model_name
    ollama_url: str = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434')
    demo_mode: bool = os.getenv('DEMO_MODE', 'true').lower() == 'true'
    overpass_url: str = os.getenv('OVERPASS_URL', 'https://overpass-api.de/api/interpreter')
    openaq_api_key: str = os.getenv('OPENAQ_API_KEY', '')
    noisemodelling_home: str = os.getenv('NOISEMODELLING_HOME', '')
    noise_java_home: str = os.getenv('NOISE_JAVA_HOME', '')
    groq_api_key: str = os.getenv('GROQ_API_KEY', '')
    groq_model: str = MODEL_CONFIG.groq_model
    parser_timeout_seconds: float = MODEL_CONFIG.parser_timeout_seconds
    ollama_num_ctx: int = MODEL_CONFIG.ollama_num_ctx
    temperature: float = MODEL_CONFIG.temperature
    max_output_tokens: int = MODEL_CONFIG.max_output_tokens
    groq_reasoning_effort: str = MODEL_CONFIG.groq_reasoning_effort
    hybrid_llm: str = MODEL_CONFIG.hybrid_llm
    demo_dir: Path = ROOT / 'data/demo'
    environment_dir: Path = ROOT / 'data/environment'
    registry_path: Path = ROOT / 'app/features/registry.yaml'
    max_tool_calls: int = 100


settings = Settings()
