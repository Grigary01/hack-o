import { describe, expect, it } from 'vitest';
import type { CriterionDto, FeatureRegistryDto, HotelSearchResultDto, ParsedQueryDto } from './contract';
import { groupClaims, mapHotelResult, mapQuestion, requestChips, valueText } from './mappers';

const registry = {
  walking_distance_to_beach_m: { label: 'Путь до пляжа', description: '', type: 'number', unit: 'm', scope: 'hotel', provider: 'pedestrian_distance', choices: [], question: null, choice_labels: {} },
  quietness_proxy: { label: 'Потенциал тишины снаружи', description: '', type: 'category', unit: null, scope: 'hotel', provider: 'quietness', choices: ['low', 'medium', 'high'], question: null, choice_labels: { low: 'низкий', medium: 'средний', high: 'высокий' } },
  sea_view: { label: 'Вид на море из номера', description: '', type: 'boolean', unit: null, scope: 'room', provider: 'hotelier', choices: [], question: 'В каких конкретно номерах есть или нет вида на море?', choice_labels: {}, model_check: { potential: 'sea_view_potential', none_value: 'none', min_floor: 'sea_view_min_floor' } },
  sea_view_potential: { label: 'Вид на море из окон (расчёт)', description: '', type: 'category', unit: null, scope: 'hotel', provider: 'viewshed', choices: ['none', 'partial', 'wide'], question: null, choice_labels: { wide: 'широкий вид', none: 'моря не видно' } },
} satisfies FeatureRegistryDto;

const parsed: ParsedQueryDto = {
  region: 'Adler',
  hard_constraints: [{ feature_key: 'walking_distance_to_beach_m', operator: '<=', value: 500, unit: 'm', scope: 'hotel' }],
  soft_preferences: [
    { feature_key: 'quietness_proxy', desired: 'high', importance: 0.9, weight_source: 'default', scope: 'hotel', derived_from: null },
    { feature_key: 'sea_view', desired: true, importance: 0.6, weight_source: 'default', scope: 'room', derived_from: null },
    { feature_key: 'sea_view_potential', desired: 'wide', importance: 0.6, weight_source: 'companion', scope: 'hotel', derived_from: 'sea_view' },
  ],
  unknown_or_ambiguous: [],
  clarification_question: null,
  original_text: '',
  ignored_terms: ['blackout'],
};

const criterion = (over: Partial<CriterionDto>): CriterionDto => ({
  feature_key: 'walking_distance_to_beach_m',
  requested: '<= 500',
  actual: 319.8,
  outcome: 'matched',
  status: 'estimated',
  subject_id: 'h1',
  match: null,
  explanation: '',
  evidence: [],
  model_conflicts: [],
  ...over,
});

const result = (criteria: CriterionDto[]): HotelSearchResultDto => ({
  hotel: { id: 'osm:node:1', name: 'Островок', lat: 43.42, lon: 39.91, region: 'Adler', tags: {}, source_url: 'https://osm.org/node/1', collected_at: '' },
  eligible: true,
  recommended_room_id: null,
  score: 0.8,
  coverage: 0.8,
  ranking_score: 0.6,
  uncertainty: 0.2,
  criteria,
  warnings: [],
  pending_hotelier_question_ids: ['q1'],
});

describe('API mappers', () => {
  it('форматирует значения без ложной точности', () => {
    expect(valueText('walking_distance_to_beach_m', 319.8, registry.walking_distance_to_beach_m)).toBe('4 мин пешком · 320\u00a0м');
    expect(valueText('quietness_proxy', 'high', registry.quietness_proxy)).toBe('высокий');
    expect(valueText('sea_view', null, registry.sea_view)).toBe('нет данных');
  });

  it('нет ответа отельера, но есть расчёт по зданию — показываем расчёт, номер не подтверждён', () => {
    const hotel = mapHotelResult(
      result([
        criterion({}),
        criterion({ feature_key: 'quietness_proxy', actual: 'high', outcome: 'preference', match: 1 }),
        criterion({ feature_key: 'sea_view', actual: null, outcome: 'unknown', subject_id: null }),
        criterion({ feature_key: 'sea_view_potential', actual: 'wide', outcome: 'preference', match: 1 }),
      ]),
      'matched',
      parsed,
      registry,
    );
    // Отель у воды с широким расчётным видом не уходит ниже отеля с одним подтверждённым номером.
    expect(hotel.group).toBe('confirmed');
    expect(hotel.price).toBeNull();
    // Расчётный спутник отдельной строкой не показывается, но остаётся в источниках.
    expect(hotel.criteria.map((c) => c.key)).toEqual(['walking_distance_to_beach_m', 'quietness_proxy', 'sea_view']);
    expect(hotel.evidence).toHaveLength(4);
    expect(hotel.criteria[0]).toMatchObject({ required: true, state: 'met' });
    expect(hotel.criteria[2]).toMatchObject({ state: 'met', askable: true, text: 'Вид на море — по расчёту: широкий вид · номер не подтверждён' });
    expect(hotel.pendingQuestion).toBe(true);
  });

  it('нет ни ответа отельера, ни расчёта — «нет данных», отель частичный', () => {
    const hotel = mapHotelResult(
      result([criterion({}), criterion({ feature_key: 'sea_view', actual: null, outcome: 'unknown', subject_id: null })]),
      'matched',
      parsed,
      registry,
    );
    expect(hotel.group).toBe('partial');
    expect(hotel.criteria[1]).toMatchObject({ state: 'unknown', text: 'Вид на море — нет данных' });
  });

  it('по расчёту моря не видно — частичное соответствие, а не «нет данных»', () => {
    const hotel = mapHotelResult(
      result([
        criterion({}),
        criterion({ feature_key: 'sea_view', actual: null, outcome: 'unknown', subject_id: null }),
        criterion({ feature_key: 'sea_view_potential', actual: 'none', outcome: 'preference', match: 0 }),
      ]),
      'matched',
      parsed,
      registry,
    );
    expect(hotel.criteria[1]).toMatchObject({ state: 'weak', text: 'Вид на море — по расчёту: моря не видно · номер не подтверждён' });
  });

  it('matched со всеми известными условиями — подтверждён', () => {
    const hotel = mapHotelResult(
      result([criterion({}), criterion({ feature_key: 'sea_view', actual: true, outcome: 'preference', match: 1, subject_id: 'osm:node:1:room:301' })]),
      'matched',
      parsed,
      registry,
    );
    expect(hotel.group).toBe('confirmed');
    expect(hotel.criteria[1]!.text).toBe('Вид на море — есть в номере 301');
  });

  it('показывает непонятые слова запроса как неучтённые', () => {
    const chips = requestChips(parsed, registry);
    expect(chips).toContainEqual({ label: 'До пляжа ≤ 500\u00a0м · обязательно', kind: 'required' });
    expect(chips).toContainEqual({ label: 'Не распознано: blackout', kind: 'unsupported' });
    expect(chips.some((c) => c.label.includes('расчёт'))).toBe(false);
  });

  it('группирует номера с одинаковым утверждением', () => {
    const claims = groupClaims([
      { room_number: '301', floor: null, feature_key: 'sea_view', value: true, quote: 'В номерах 301-303 есть вид на море' },
      { room_number: '302', floor: null, feature_key: 'sea_view', value: true, quote: 'В номерах 301-303 есть вид на море' },
      { room_number: '303', floor: null, feature_key: 'sea_view', value: true, quote: 'В номерах 301-303 есть вид на море' },
      { room_number: '101', floor: 1, feature_key: 'sea_view', value: false, quote: 'В номере 101 нет вида на море' },
    ]);
    expect(claims.map((c) => [c.subject, c.subjectNote, c.value])).toEqual([
      ['Номера 301–303', null, true],
      ['Номер 101', '1-й этаж', false],
    ]);
  });

  it('строит вопрос отельеру из текста бэкенда', () => {
    const q = mapQuestion(
      {
        id: 'q1',
        hotel_id: 'h',
        feature_key: 'sea_view',
        text: 'В каких конкретно номерах есть или нет вида на море? Укажите номера и этаж, если известен.',
        status: 'open',
        created_at: '',
        updated_at: '',
        context: { reasons: ['pending_answer', 'unparsed_answer'], subject_ids: [], review_answer_id: 'a1' },
      },
      'Островок',
      registry,
    );
    expect(q.title).toBe('Есть ли в номерах вид на море?');
    expect(q.ask).toBe('В каких конкретно номерах есть или нет вида на море?');
    expect(q.prompt).toBe('Укажите номера и этаж, если известен.');
    expect(q.featureShort).toBe('Вид на море');
    // context вопроса: к неподтверждённому разбору можно вернуться, причина видна отельеру.
    expect(q.pendingAnswerId).toBe('a1');
    expect(q.statusNote).toBe('Часть ответа не удалось разобрать');
  });
});

it('технические пояснения расчётов показываются обычным языком', async () => {
  const { humanize, modelSourceName } = await import('./humanize');
  expect(humanize('Оживлённые дороги на пути к пляжу переходить не нужно (по OSM).')).toBe('Оживлённые дороги на пути к пляжу переходить не нужно.');
  expect(humanize('Море: широкий вид из окон стороны ЮЗ (азимут 236°), с 1-го этажа')).toBe('Море: широкий вид из окон стороны ЮЗ, с 1-го этажа');
  expect(humanize('Траектория захода/взлёта по оси ВПП 06/24 (посадочный курс 64°) проходит ≈ в 1070 м')).toBe(
    'Траектория захода/взлёта вдоль взлётной полосы проходит ≈ в 1070 м',
  );
  expect(humanize('У 56 заведений рядом часы в OSM не указаны.')).toBe('У 56 заведений рядом часы на карте не указаны.');
  expect(modelSourceName('OSM здания и coastline + Copernicus DEM GLO-30')).toBe('Расчёт по карте зданий, берега и рельефа');
});
