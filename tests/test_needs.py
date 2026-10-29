"""Поиск по потребностям гостя: весь запрос учтён, расплывчатое — «любой из», уточнение по желанию."""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from app.features.concepts import get_concepts
from app.features.view_robustness import family_risk
from app.main import create_app
from app.ml.multicriteria import aggregate
from app.ml.needs import complete_needs, prepare
from app.ml.query_parser import HybridQueryParser, OfflineQueryParser
from app.ml.rules_parser import RulesQueryParser
from app.schemas.query import ParsedHotelQuery, SoftPreference

TEXT = 'Вид из окна без деревьев'
LATER = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)  # после снимка зданий 25.10 — расчёты вида действуют


@pytest.fixture
def offline(engine, monkeypatch):
    for module in ('app.storage.repository', 'app.features.service', 'app.hotelier.dialogue',
                   'app.agent.feature_agent', 'app.features.view_robustness'):
        monkeypatch.setattr(module + '.now_utc', lambda: LATER)
    with TestClient(create_app(engine=engine, parser=OfflineQueryParser())) as client:
        yield client


def test_concepts_reference_registry_features():
    concept = get_concepts()['window_view']
    assert [o.feature_key for o in concept.options] == ['sea_view_potential', 'mountain_view_potential', 'sunset_view_potential']


def test_rules_mark_every_part_of_the_query_with_quotes():
    parsed = RulesQueryParser().parse(TEXT)
    assert [(n.kind, n.quote) for n in parsed.needs] == [('any_of', 'вид из окна'), ('feature', 'без деревьев')]
    assert not parsed.unknown_or_ambiguous and not parsed.ignored_terms
    cheap = RulesQueryParser().parse('Хочу тихо ночью и дешево')
    assert ('unsupported', 'дешево') in [(n.kind, n.quote) for n in cheap.needs]
    # Названный прямо вид — обычный признак, а не расплывчатое понятие.
    assert all(n.kind != 'any_of' for n in RulesQueryParser().parse('Вид из окна на море').needs)


def test_vague_view_does_not_block_and_answer_follows_guest_words(offline):
    body = offline.post('/api/search', json={'text': TEXT}).json()
    assert body['status'] == 'ok' and body['matched']
    keys = {p['feature_key'] for p in body['parsed']['soft_preferences']}
    assert {'sea_view_potential', 'mountain_view_potential', 'sunset_view_potential', 'view_obstruction_risk'} <= keys
    view = next(n for n in body['parsed']['needs'] if n['kind'] == 'any_of')
    assert [o['key'] for o in view['options']] == ['sea', 'mountains', 'sunset'] and view['chosen'] is None
    top = body['matched'][0]
    rows = {n['quote']: n for n in top['needs']}
    assert rows['вид из окна']['outcome'] == 'matched' and rows['вид из окна']['best_option'] in ('sea', 'mountains', 'sunset')
    assert rows['без деревьев']['outcome'] in ('matched', 'partial') and rows['без деревьев']['detail']
    # Вид в группе «любой из» считается один раз: группа в разбивке одна, а не три.
    assert sum(g['group'].startswith('any:') for g in top['group_scores']) == 1


def test_guest_can_refine_without_reparsing(offline):
    first = offline.post('/api/search', json={'text': TEXT}).json()
    sea = offline.post('/api/search', json={'parsed': first['parsed'], 'choices': {'window_view': 'sea'}}).json()
    keys = {p['feature_key'] for p in sea['parsed']['soft_preferences']}
    assert 'sea_view_potential' in keys and not {'mountain_view_potential', 'sunset_view_potential'} & keys
    assert sea['parser_mode'] == 'structured_input'
    assert all(n['best_option'] in (None, 'sea') for h in sea['matched'] for n in h['needs'] if n['kind'] == 'any_of')
    back = offline.post('/api/search', json={'parsed': sea['parsed'], 'choices': {'window_view': 'any'}}).json()
    assert {'mountain_view_potential', 'sunset_view_potential'} <= {p['feature_key'] for p in back['parsed']['soft_preferences']}
    assert offline.post('/api/search', json={'parsed': first['parsed'], 'choices': {'window_view': 'moon'}}).status_code == 422
    assert offline.post('/api/search', json={'text': 'Хочу тихо', 'choices': {'window_view': 'sea'}}).status_code == 422


def test_unsupported_part_is_answered_as_unchecked(offline):
    body = offline.post('/api/search', json={'text': 'Хочу тихо ночью и дешево'}).json()
    assert body['status'] == 'ok'
    rows = {n['quote']: n for n in body['matched'][0]['needs']}
    assert rows['дешево']['outcome'] == 'unchecked' and 'цена' in rows['дешево']['text']


def test_every_condition_gets_a_need_even_without_parser_markup():
    parsed = ParsedHotelQuery(
        soft_preferences=[SoftPreference(feature_key='quietness_proxy', desired='high')],
        unsupported=['бассейн'])
    completed = complete_needs(parsed)
    assert [(n.kind, n.features or n.topic) for n in completed.needs] == [
        ('feature', ['quietness_proxy']), ('unsupported', 'бассейн')]
    # Идемпотентно: разобранный запрос из ответа можно отправить обратно.
    assert prepare(prepare(parsed)).needs == prepare(parsed).needs


def test_llm_named_feature_without_condition_gets_registry_default():
    parsed = ParsedHotelQuery(needs=[{'quote': 'без деревьев', 'kind': 'feature', 'features': ['view_obstruction_risk']}])
    completed = complete_needs(parsed)
    assert [(p.feature_key, p.desired) for p in completed.soft_preferences] == [('view_obstruction_risk', 'low')]


def test_any_of_group_takes_best_known_option():
    prefs = [SoftPreference(feature_key=k, desired=d) for k, d in
             (('sea_view_potential', 'wide'), ('mountain_view_potential', 'wide'), ('sunset_view_potential', 'year_round'))]
    keys = {p.feature_key for p in prefs}
    summary = aggregate(prefs, {'sea_view_potential': .5, 'mountain_view_potential': 1., 'sunset_view_potential': None},
                        any_of={'window_view': keys}, labels={'window_view': 'Вид из окна'})
    group = summary['groups'][0]
    assert group['label'] == 'Вид из окна' and group['lower'] == 1. and group['coverage'] == 1.
    unknown = aggregate(prefs, {'sea_view_potential': .5, 'mountain_view_potential': None, 'sunset_view_potential': None},
                        any_of={'window_view': keys})['groups'][0]
    assert unknown['lower'] == .5 and unknown['upper'] == 1.


@pytest.mark.parametrize('low,base,high,floors,risk', [
    ('wide', 'wide', 'wide', (2, 3, 3), 'low'),
    ('wide', 'wide', 'wide', (2, 3, 5), 'medium'),   # вид тот же, но нужен этаж заметно выше
    ('wide', 'partial', 'partial', (2, 3, 3), 'medium'),
    ('partial', 'partial', 'none', (3, 3, None), 'high'),
    ('none', 'none', 'none', (None, None, None), None),
])
def test_view_obstruction_risk_from_scenarios(low, base, high, floors, risk):
    scenarios = {name: {'sea_view_potential': value, 'sea_view_min_floor': floor}
                 for name, value, floor in zip(('low', 'base', 'high'), (low, base, high), floors)}
    result = family_risk(scenarios, 'sea_view_potential', 'sea_view_min_floor')
    assert (result[0] if result else None) == risk


def test_obstruction_feature_is_derived_for_all_hotels(offline):
    body = offline.post('/api/search', json={'text': 'Чтобы деревья не закрывали вид'}).json()
    rows = [n for group in ('matched', 'needs_verification') for h in body[group] for n in h['needs']]
    assert rows and all(n['outcome'] != 'unknown' for n in rows if 'view_obstruction_risk' in n['features'])


class FakeLLM:
    client = None

    def __init__(self, answer):
        self.answer = answer

    def parse(self, text):
        return ParsedHotelQuery.model_validate(self.answer | {'original_text': text})


def test_hybrid_keeps_rules_needs_and_adds_llm_concept():
    llm = FakeLLM({'unsupported': ['цена'], 'needs': [
        {'quote': 'чтоб глаз радовался', 'kind': 'any_of', 'concept': 'window_view'},
        {'quote': 'недорого', 'kind': 'unsupported', 'topic': 'цена'}]})
    parsed = HybridQueryParser(llm=llm).parse('Тихо, недорого и чтоб глаз радовался')
    kinds = [(n.kind, n.quote) for n in parsed.needs]
    assert ('any_of', 'чтоб глаз радовался') in kinds and sum(k == 'unsupported' for k, _ in kinds) == 1
    assert ('feature', 'тихо') in kinds
