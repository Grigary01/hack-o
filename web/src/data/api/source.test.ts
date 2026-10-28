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
