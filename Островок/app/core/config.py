"""Единая конфигурация. Импорт не запускает сеть и не создаёт базу."""
from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "runtime/adler.db"}')
    parser_mode: str = os.getenv('PARSER_MODE', 'fixture')
    model_name: str = os.getenv('MODEL_NAME', 'gemma3:12b')
    ollama_url: str = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434')
    demo_mode: bool = os.getenv('DEMO_MODE', 'true').lower() == 'true'
    overpass_url: str = os.getenv('OVERPASS_URL', 'https://overpass-api.de/api/interpreter')
    openaq_api_key: str = os.getenv('OPENAQ_API_KEY', '')
    noisemodelling_home: str = os.getenv('NOISEMODELLING_HOME', '')
    noise_java_home: str = os.getenv('NOISE_JAVA_HOME', '')
    demo_dir: Path = ROOT / 'data/demo'
    registry_path: Path = ROOT / 'app/features/registry.yaml'
    max_tool_calls: int = 100


settings = Settings()
