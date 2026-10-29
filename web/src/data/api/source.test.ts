import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { ObservationDto } from './contract';
import { requestChips } from './mappers';

beforeEach(() => vi.resetModules());
afterEach(() => vi.unstubAllGlobals());

it('загружает сохранённый ответ с backend, без sessionStorage', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    id: 'answer', question_id: 'question', text: 'В номере 1 есть вид.',
    extraction: { claims: [], unparsed: [] }, status: 'pending', created_at: '2026-10-29',
  })));
  vi.stubGlobal('fetch', fetcher);
  const { createApiSource } = await import('./source');
  const answer = await createApiSource().getAnswer('answer');
  expect(answer.id).toBe('answer');
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/hotelier/answers/answer');
});

it('ошибку сервера не заменяет локальным ответом или mock', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Нет ответа' }), { status: 404 })));
  const { createApiSource } = await import('./source');
  await expect(createApiSource().getAnswer('missing')).rejects.toMatchObject({ status: 404 });
});

it('в кабинете конфликтные и устаревшие утверждения не становятся действующими фактами', async () => {
  const observation = {
    id: 'old', subject_id: 'h:room:101', subject_type: 'room', feature_key: 'sea_view', value: true,
    collected_at: '2026-10-01', evidence: { source: { type: 'hotelier_simulated', name: 'Демо', ref: '' }, details: {} },
  } as ObservationDto;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(
    url.endsWith('/evidence') ? { current_demo: [{
      subject_id: observation.subject_id, feature_key: 'sea_view', status: 'conflicted', value: null,
      observations: [observation],
    }] } : {},
  ))));
  const { createApiSource } = await import('./source');
  const rooms = await createApiSource().getRooms('h');
  expect(rooms[0]?.facts[0]?.value).toBe('Конфликт — нужна проверка');
});

it('чип сохраняет смысл обязательного отрицания', () => {
  const chips = requestChips({ region: 'Adler', original_text: '', soft_preferences: [],
    hard_constraints: [{ feature_key: 'sea_view', operator: '=', value: false, scope: 'room', unit: null }],
    unknown_or_ambiguous: [], clarification_question: null,
  }, {});
  expect(chips[0]?.label).toContain(': нет');
});

it('просьба уточнить показывает, что именно непонятно, а не регион', async () => {
  const { clarificationText } = await import('./source');
  const base = { region: 'Adler', hard_constraints: [], soft_preferences: [], original_text: '', clarification_question: null };
  expect(clarificationText({ ...base, unknown_or_ambiguous: ['10 минут пешком — нужен темп ходьбы'] })).toBe(
    'Уточните: 10 минут пешком — нужен темп ходьбы',
  );
  expect(clarificationText({ ...base, region: 'Batumi', unknown_or_ambiguous: [] })).toContain('Адлер');
});

it('«Искать без этого условия»: не разбирает текст повторно и помечает пропущенное', async () => {
  const parsed = {
    region: 'Adler', hard_constraints: [], original_text: 'тихо и дешево', ignored_terms: [],
    soft_preferences: [{ feature_key: 'quietness_proxy', desired: 'high', importance: 0.9, weight_source: 'default', scope: 'hotel', derived_from: null }],
    unknown_or_ambiguous: ['«дешево» — цены не поддерживаются'], clarification_question: 'Уберите условие о стоимости.',
  };
  const empty = { matched: [], needs_verification: [], excluded: [], parser_mode: 'groq', include_simulated: true };
  const bodies: Record<string, unknown>[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify({ status: 'ok', demo_mode: true }));
    if (url.endsWith('/features')) return new Response(JSON.stringify({}));
    const body = JSON.parse(String(init?.body));
    bodies.push(body);
    return new Response(JSON.stringify(body.text
      ? { ...empty, status: 'needs_clarification', parsed }
      : { ...empty, status: 'ok', parsed: body.parsed }));
  }));
  const { createApiSource } = await import('./source');
  const source = createApiSource();
  const params = { text: 'тихо и дешево', destination: 'Адлер', checkIn: '', checkOut: '', guests: 2 };
  const first = await source.search(params);
  expect(first.status).toBe('needs_clarification');
  expect(first.canSearchAnyway).toBe(true);
  const relaxed = await source.search({ ...params, skipUnclear: true });
  expect(relaxed.status).toBe('ok');
  expect(relaxed.skipped).toEqual(['«дешево» — цены не поддерживаются']);
  // Второй запрос — уже разобранный: без text, с очищенными непроверяемыми условиями.
  expect(bodies).toHaveLength(2);
  expect(bodies[1]).toMatchObject({ parsed: { unknown_or_ambiguous: [], clarification_question: null } });
  expect(bodies[1]).not.toHaveProperty('text');
});

it('уточнение «Какой вид важнее?» не разбирает текст заново: parsed + choices', async () => {
  const parsed = {
    region: 'Adler', hard_constraints: [], soft_preferences: [], original_text: 'вид из окна', ignored_terms: [],
    unknown_or_ambiguous: [], clarification_question: null,
    needs: [{ quote: 'вид из окна', kind: 'any_of', features: [], concept: 'window_view', topic: null, chosen: null,
      question: 'Какой вид важнее?', options: [{ key: 'sea', label: 'На море', feature_key: 'sea_view_potential' }, { key: 'mountains', label: 'На горы', feature_key: 'mountain_view_potential' }] }],
  };
  const empty = { matched: [], needs_verification: [], excluded: [], parser_mode: 'groq', include_simulated: true, status: 'ok' };
  const bodies: Record<string, unknown>[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify({ status: 'ok', demo_mode: true }));
    if (url.endsWith('/features')) return new Response(JSON.stringify({}));
    const body = JSON.parse(String(init?.body));
    bodies.push(body);
    return new Response(JSON.stringify({ ...empty, parsed: body.parsed ?? parsed }));
  }));
  const { createApiSource } = await import('./source');
  const source = createApiSource();
  const params = { text: 'вид из окна', destination: 'Адлер', checkIn: '', checkOut: '', guests: 2 };
  const first = await source.search(params);
  expect(first.refinements).toEqual([{ concept: 'window_view', quote: 'вид из окна', question: 'Какой вид важнее?',
    options: [{ key: 'sea', label: 'На море' }, { key: 'mountains', label: 'На горы' }], chosen: null }]);
  await source.search({ ...params, choices: { window_view: 'sea', stale_concept: 'x' } });
  expect(bodies).toHaveLength(2);
  expect(bodies[1]).toMatchObject({ parsed: { original_text: 'вид из окна' }, choices: { window_view: 'sea' } });
  expect(bodies[1]).not.toHaveProperty('text');
});
