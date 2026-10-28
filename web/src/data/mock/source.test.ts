import { beforeEach, describe, expect, it } from 'vitest';
import { createMockSource } from './source';
import { resetState } from './store';
import { DEMO_QUERY } from './fixtures';

const params = { text: DEMO_QUERY, destination: 'Батуми', checkIn: '2027-06-12', checkOut: '2027-06-16', guests: 2 };

describe('mock-сценарий из макета', () => {
  beforeEach(() => resetState());

  it('группирует выдачу как на стр. 1', async () => {
    const source = createMockSource();
    const result = await source.search(params);
    const group = (name: string) => result.hotels.find((h) => h.name === name)?.group;
    expect(result.chips.map((c) => c.label)).toEqual(['Blackout · обязательно', 'Магазин открыт ночью', 'До моря пешком · время не задано']);
    expect(group('Приморский')).toBe('confirmed');
    expect(group('Тихий двор')).toBe('partial');
    expect(group('Старый Батуми')).toBe('excluded');
    expect(result.hotels.every((h) => h.price?.demo)).toBe(true);
  });

  it('ответ отельера после публикации меняет выдачу', async () => {
    const source = createMockSource();
    const [question] = await source.listQuestions('demo-tikhiy-dvor');
    const answer = await source.submitAnswer(
      question!.id,
      'В улучшенных номерах, окнами во двор, есть шторы blackout — они полностью перекрывают дневной свет. В стандартных номерах обычные шторы.',
    );
    expect(answer.claims.map((c) => [c.subject, c.value])).toEqual([
      ['Улучшенный', true],
      ['Стандартный', false],
    ]);
    const published = await source.publishAnswer(answer.id, {});
    expect(published.guestPreview).toBe('Blackout — в улучшенных номерах с окнами во двор');

    const result = await source.search(params);
    expect(result.hotels.find((h) => h.name === 'Тихий двор')?.group).toBe('confirmed');
    expect((await source.listQuestions('demo-tikhiy-dvor')).every((q) => q.status === 'answered')).toBe(true);
  });

  it('правка строки при проверке меняет опубликованное значение', async () => {
    const source = createMockSource();
    const answer = await source.submitAnswer('q-tikhiy-blackout', 'В улучшенных номерах есть blackout. В стандартных номерах обычные шторы.');
    const standard = answer.claims.find((c) => c.subject === 'Стандартный')!;
    const published = await source.publishAnswer(answer.id, { [standard.id]: true });
    expect(published.claims.every((c) => c.value)).toBe(true);
  });

  it('не публикует неразобранный ответ и другое направление даёт пустую выдачу', async () => {
    const source = createMockSource();
    const answer = await source.submitAnswer('q-tikhiy-blackout', 'Возможно, летом повесим.');
    await expect(source.publishAnswer(answer.id, {})).rejects.toThrow('разобран не полностью');
    const empty = await source.search({ ...params, destination: 'Стамбул' });
    expect(empty.hotels).toEqual([]);
    expect(empty.notes[0]).toContain('только Батуми');
  });
});
