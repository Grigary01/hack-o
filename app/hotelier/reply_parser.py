"""Стык backend/ML: только feature_key + text -> существующий ReplyExtraction."""
import json
from pathlib import Path
from typing import Protocol
from app.core.config import settings
from app.schemas.hotelier import ReplyExtraction
from app.hotelier.rule_reply_parser import parse_hotelier_reply


class ReplyParser(Protocol):
    mode: str

    def parse(self, *, feature_key: str, text: str) -> ReplyExtraction: ...


class BoundedRuleReplyParser:
    mode = 'bounded_rules'

    def parse(self, *, feature_key, text):
        return parse_hotelier_reply(feature_key, text)


class FixtureReplyParser:
    """Явная заглушка ML. Не сопоставляет неизвестный текст с похожим примером."""
    mode = 'fixture'

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else settings.reply_fixture_path
        rows = json.loads(self.path.read_text())
        self.examples = {(row['feature_key'], row['text']): row['extraction'] for row in rows}

    def parse(self, *, feature_key, text):
        raw = self.examples.get((feature_key, text))
        if raw is None:
            return ReplyExtraction(unparsed=[text], parser_mode=self.mode)
        return ReplyExtraction.model_validate(raw)


def make_reply_parser(config=settings) -> ReplyParser:
    if config.reply_parser_mode == 'rules':
        return BoundedRuleReplyParser()
    if config.reply_parser_mode == 'fixture':
        return FixtureReplyParser(config.reply_fixture_path)
    if config.reply_parser_mode in ('ollama', 'groq'):
        from app.ml.reply_parser import OllamaReplyParser, GroqReplyParser
        return {'ollama': OllamaReplyParser, 'groq': GroqReplyParser}[config.reply_parser_mode](config)
    raise ValueError('REPLY_PARSER_MODE должен быть rules, fixture, ollama или groq')
