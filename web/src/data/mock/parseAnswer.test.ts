import { describe, expect, it } from 'vitest';
import { parseBlackoutAnswer } from './parseAnswer';

describe('parseBlackoutAnswer', () => {
  it('разбирает ответ из макета на две категории', () => {
    const result = parseBlackoutAnswer(
      'В улучшенных номерах, окнами во двор, есть шторы blackout — они полностью перекрывают дневной свет. В стандартных номерах обычные шторы.',
    );
    expect(result.unparsed).toEqual([]);
    expect(result.claims).toEqual([
      expect.objectContaining({ category: 'Улучшенный', note: 'Окна во двор', value: true, detail: 'Полностью перекрывают дневной свет' }),
      expect.objectContaining({ category: 'Стандартный', note: null, value: false, detail: 'Обычные шторы' }),
    ]);
  });

  it('относит уточнение без категории к предыдущему утверждению', () => {
    const result = parseBlackoutAnswer('В люксах есть blackout. Они полностью перекрывают свет.');
    expect(result.claims).toHaveLength(1);
    expect(result.claims[0]).toMatchObject({ category: 'Люкс', value: true, detail: 'Полностью перекрывают дневной свет' });
  });

  it('не угадывает условные формулировки', () => {
    const result = parseBlackoutAnswer('Возможно, летом повесим blackout в стандартных номерах.');
    expect(result.claims).toEqual([]);
    expect(result.unparsed).toHaveLength(1);
  });

  it('распознаёт «нет» и «без» как отрицание, несмотря на кириллицу', () => {
    const result = parseBlackoutAnswer('В номерах эконом нет штор blackout. В семейных номерах без blackout.');
    expect(result.claims.map((c) => [c.category, c.value])).toEqual([
      ['Эконом', false],
      ['Семейный', false],
    ]);
  });

  it('отличает делюкс от люкса', () => {
    const result = parseBlackoutAnswer('В номерах делюкс есть шторы blackout.');
    expect(result.claims.map((c) => c.category)).toEqual(['Делюкс']);
  });

  it('помечает противоречие внутри ответа', () => {
    const result = parseBlackoutAnswer('В стандартных номерах есть blackout. В стандартных номерах обычные шторы.');
    expect(result.unparsed.some((u) => u.startsWith('Противоречие'))).toBe(true);
  });
});
