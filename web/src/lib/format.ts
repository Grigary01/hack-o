import type { Money } from '../data/types';

const NBSP = '\u00a0';

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value).replace(/\s/g, NBSP);
}

export function formatMoney(money: Money): string {
  return `${formatNumber(money.amount)}${NBSP}₽`;
}

/** Русское склонение: plural(4, ['ночь', 'ночи', 'ночей']). */
export function plural(n: number, forms: readonly [string, string, string]): string {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

/** Пешком ~80 м в минуту (4,8 км/ч); округляем вверх, минимум 1 минута. */
export function walkMinutes(meters: number): number {
  return Math.max(1, Math.ceil(meters / 80));
}

export function formatMeters(meters: number): string {
  if (meters >= 1000) {
    const km = Math.round(meters / 100) / 10;
    return `${String(km).replace('.', ',')}${NBSP}км`;
  }
  return `${formatNumber(Math.round(meters / 10) * 10)}${NBSP}м`;
}

const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

function parseIsoDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

/** «12–16 июня» или «28 ноября – 2 декабря». */
export function formatDateRange(checkIn: string, checkOut: string): string | null {
  const from = parseIsoDate(checkIn);
  const to = parseIsoDate(checkOut);
  if (!from || !to) return null;
  if (from.getMonth() === to.getMonth() && from.getFullYear() === to.getFullYear()) {
    return `${from.getDate()}–${to.getDate()} ${MONTHS_GEN[to.getMonth()]}`;
  }
  return `${from.getDate()} ${MONTHS_GEN[from.getMonth()]} – ${to.getDate()} ${MONTHS_GEN[to.getMonth()]}`;
}

export function nightsBetween(checkIn: string, checkOut: string): number | null {
  const from = parseIsoDate(checkIn);
  const to = parseIsoDate(checkOut);
  if (!from || !to) return null;
  const nights = Math.round((to.getTime() - from.getTime()) / 86_400_000);
  return nights > 0 ? nights : null;
}

export function formatGuests(guests: number): string {
  return `${guests} ${plural(guests, ['взрослый', 'взрослых', 'взрослых'])}`;
}

/** «сегодня», «вчера» или «12 июня». */
export function formatDay(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diff = Math.round((startOf(now) - startOf(date)) / 86_400_000);
  if (diff === 0) return 'сегодня';
  if (diff === 1) return 'вчера';
  return `${date.getDate()} ${MONTHS_GEN[date.getMonth()]}`;
}

/** «301, 302, 303, 305» → «301–303, 305». */
export function compactNumbers(numbers: string[]): string {
  const sorted = [...new Set(numbers)].map(Number).filter(Number.isFinite).sort((a, b) => a - b);
  const parts: string[] = [];
  let start = sorted[0];
  let prev = sorted[0];
  for (let i = 1; i <= sorted.length; i += 1) {
    const current = sorted[i];
    if (current !== undefined && prev !== undefined && current === prev + 1) {
      prev = current;
      continue;
    }
    if (start !== undefined && prev !== undefined) parts.push(start === prev ? `${start}` : `${start}–${prev}`);
    start = current;
    prev = current;
  }
  return parts.join(', ');
}

export function capitalize(text: string): string {
  return text ? text[0]!.toUpperCase() + text.slice(1) : text;
}
