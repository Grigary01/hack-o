import type { SearchParams } from '../data/types';

/** Параметры поиска живут в адресе: выдачей можно поделиться, «Назад» работает. */
export function searchToQuery(params: SearchParams): string {
  const query = new URLSearchParams();
  query.set('q', params.text);
  if (params.destination) query.set('dest', params.destination);
  if (params.checkIn) query.set('in', params.checkIn);
  if (params.checkOut) query.set('out', params.checkOut);
  query.set('guests', String(params.guests));
  return query.toString();
}

export function searchFromQuery(query: URLSearchParams, defaults: SearchParams): SearchParams {
  const guests = Number(query.get('guests'));
  return {
    text: query.get('q') ?? defaults.text,
    destination: query.get('dest') ?? defaults.destination,
    checkIn: query.get('in') ?? defaults.checkIn,
    checkOut: query.get('out') ?? defaults.checkOut,
    guests: Number.isInteger(guests) && guests > 0 && guests <= 12 ? guests : defaults.guests,
  };
}

export function hasSearch(query: URLSearchParams): boolean {
  return Boolean(query.get('q')?.trim());
}
