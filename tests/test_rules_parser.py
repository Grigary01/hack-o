"""Офлайн-разбор свободного текста. Формулировки свои, не из data/evaluation (held-out не подсматриваем)."""
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from app.core.config import settings
from app.main import create_app
from app.ml.query_parser import OfflineQueryParser, make_parser
from app.ml.rules_parser import RulesQueryParser
from app.storage.db import create_db
from scripts.seed_demo import seed


def parse(text):
    result = RulesQueryParser().parse(text)
    hard = [(h.feature_key, h.operator, h.value) for h in result.hard_constraints]
    soft = {p.feature_key: p for p in result.soft_preferences}
    return result, hard, soft


@pytest.mark.parametrize('text, key, desired', [
    ('Тихий отель у моря', 'quietness_proxy', 'high'),
    ('Тихий отель у моря', 'walking_distance_to_beach_m', 'near'),
    ('Хочу выспаться, подальше от самолётов и баров', 'aircraft_path_distance_m', 'far'),
    ('Хочу выспаться, подальше от самолётов и баров', 'nightlife_distance_m', 'far'),
    ('Не хочу рядом с барами', 'nightlife_distance_m', 'far'),
    ('Шумный район, ночная жизнь рядом', 'quietness_proxy', 'low'),
    ('Шумный район, ночная жизнь рядом', 'nightlife_distance_m', 'near'),
    ('Чтобы не было слышно самолёты', 'aircraft_path_distance_m', 'far'),
    ('Номер без вида на море', 'sea_view', False),
    ('Красивый закат из окна', 'sunset_view', True),
    ('без шумоизоляции не надо', 'soundproofing', True),
])
def test_polarity_and_negation(text, key, desired):
    _, _, soft = parse(text)
    assert soft[key].desired == desired


def test_numbers_operators_ranges_and_walking_minutes():
    assert parse('до моря не дальше 1,5 км')[1] == [('walking_distance_to_beach_m', '<=', 1500)]
    assert parse('пляж от 200 до 600 метров')[1] == [('walking_distance_to_beach_m', '>=', 200),
                                                     ('walking_distance_to_beach_m', '<=', 600)]
    assert parse('бары не ближе полкилометра')[1] == [('nightlife_distance_m', '>=', 500)]
    _, hard, soft = parse('Отель в десяти минутах пешком от пляжа')  # числа словами в косвенном падеже
    assert not hard and soft['walking_distance_to_beach_m'].utility.ideal_max == 800
    assert parse('До моря полтора километра максимум')[1] == [('walking_distance_to_beach_m', '<=', 1500)]
    assert parse('бары 300 м и не ближе')[1] == [('nightlife_distance_m', '>=', 300)]
    _, hard, soft = parse('Отель в 10 минутах пешком от пляжа')
    utility = soft['walking_distance_to_beach_m'].utility
    assert not hard and utility.kind == 'lower' and utility.ideal_max == 800  # 10 мин × 80 м/мин
    result, _, _ = parse('5 минут до моря')
    assert result.unknown_or_ambiguous  # без «пешком» время неоднозначно


def test_hard_soft_weights_and_relative_importance():
    assert parse('Обязательно вид на море')[1] == [('sea_view', '=', True)]
    _, hard, soft = parse('Желательно вид на море')
    assert not hard and soft['sea_view'].desired is True
    _, _, soft = parse('Тишина с весом 0.3')
    assert soft['quietness_proxy'].importance == .3 and soft['quietness_proxy'].weight_source == 'explicit'
    _, _, soft = parse('Закат важнее тишины')
    assert soft['sunset_view'].importance == 1 and soft['quietness_proxy'].importance == .5
    result, hard, soft = parse('Шумоизоляция не важна, хочу тихо')
    assert 'soundproofing' not in soft and soft['quietness_proxy'].desired == 'high'


def test_unsupported_and_other_region_are_not_dropped_silently():
    result, _, soft = parse('Недорогой отель с бассейном у моря')
    assert 'walking_distance_to_beach_m' in soft
    assert {'Пока не поддерживается: цена', 'Пока не поддерживается: бассейн'} <= set(result.unknown_or_ambiguous)
    assert 'бассейн' in result.clarification_question
    other = RulesQueryParser().parse('Отель в Геленджике')
    assert other.region != 'Adler' and other.unknown_or_ambiguous
    assert RulesQueryParser().parse('Хочу что-нибудь эдакое').unknown_or_ambiguous
    assert not RulesQueryParser().parse('Покажи все гостиницы').unknown_or_ambiguous


def test_offline_mode_prefers_fixtures_then_rules():
    parser = make_parser(replace(settings, parser_mode='offline'))
    assert isinstance(parser, OfflineQueryParser) and parser.mode == 'offline'
    demo = parser.examples[0]['text']
    assert parser.parse(demo) == parser.fixture.parse(demo)
    assert parser.parse('Тихий отель у моря без баров').soft_preferences


def test_free_text_search_end_to_end():
    engine = create_db('sqlite://')
    seed(engine)
    with TestClient(create_app(engine=engine, parser=OfflineQueryParser())) as client:
        body = client.post('/api/search', json={'text': 'Тихий отель у моря, не дальше 400 м до пляжа, подальше от самолётов'}).json()
    assert body['status'] == 'ok' and body['parser_mode'] == 'offline'
    assert body['parsed']['hard_constraints'][0]['value'] == 400
    assert body['matched'] and all(
        next(c for c in r['criteria'] if c['feature_key'] == 'walking_distance_to_beach_m')['actual'] <= 400
        for r in body['matched'])
    engine.dispose()


def test_unmatched_content_words_are_reported_not_dropped():
    result = RulesQueryParser().parse('Уютный семейный отель с балконом и видом на горы')
    assert result.ignored_terms == ['уютный', 'семейный', 'балконом']
    assert not result.unknown_or_ambiguous  # не блокирует поиск
    assert RulesQueryParser().parse('Тихий отель у моря, без баров').ignored_terms == []
