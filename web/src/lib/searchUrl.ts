import { formatDateRange, formatGuests } from './format';
import type { SearchParams } from '../data/types';

/** Параметры поиска живут в адресе: выдачей можно поделиться, «Назад» работает. */
export function searchToQuery(params: SearchParams): string {
  const query = new URLSearchParams();
  query.set('q', params.text);
  if (params.destination) query.set('dest', params.destination);
  if (params.checkIn) query.set('in', params.checkIn);
  if (params.checkOut) query.set('out', params.checkOut);
  query.set('guests', String(params.guests));
  if (params.skipUnclear) query.set('relax', '1');
  const picks = Object.entries(params.choices ?? {}).filter(([, v]) => v && v !== 'any');
  if (picks.length) query.set('pick', picks.map(([k, v]) => `${k}:${v}`).join(','));
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
    skipUnclear: query.get('relax') === '1',
    choices: parsePicks(query.get('pick')),
  };
}

/** «window_view:sea,…» → { window_view: 'sea' }; мусор в адресе игнорируется. */
function parsePicks(raw: string | null): Record<string, string> | undefined {
  if (!raw) return undefined;
  const picks = Object.fromEntries(
    raw
      .split(',')
      .map((pair) => pair.split(':'))
      .filter((p): p is [string, string] => p.length === 2 && /^[a-z_]+$/.test(p[0]!) && /^[a-z_]+$/.test(p[1]!)),
  );
  return Object.keys(picks).length ? picks : undefined;
}

export function hasSearch(query: URLSearchParams): boolean {
  return Boolean(query.get('q')?.trim());
}

/** Строка контекста для шапки: «Батуми · 12–16 июня · 2 взрослых». */
export function describeSearch(params: SearchParams): string {
  return [params.destination, formatDateRange(params.checkIn, params.checkOut), formatGuests(params.guests)].filter(Boolean).join(' · ');
}
