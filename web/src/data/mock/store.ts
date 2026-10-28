import { DataError } from '../errors';
import { initialState, type MockState } from './fixtures';

const KEY = 'ostrovok.mock.state.v1';

/** Состояние демо живёт в sessionStorage: сценарий переживает перезагрузку, но не утекает между вкладками. */
let memory: MockState | null = null;

function storage(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage;
  } catch {
    return null;
  }
}

export function readState(): MockState {
  if (memory) return memory;
  const raw = storage()?.getItem(KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as MockState;
      if (parsed.version === 1) {
        memory = parsed;
        return parsed;
      }
    } catch {
      /* повреждённое состояние — начинаем заново */
    }
  }
  memory = initialState();
  return memory;
}

export function writeState(update: (draft: MockState) => void): MockState {
  const next = structuredClone(readState());
  update(next);
  memory = next;
  storage()?.setItem(KEY, JSON.stringify(next));
  return next;
}

export function resetState() {
  memory = initialState();
  storage()?.removeItem(KEY);
}

/** Задержка, чтобы в демо были видны состояния загрузки. */
export function latency(ms = 450): Promise<void> {
  const jitter = Math.round(Math.random() * 250);
  return new Promise((resolve) => setTimeout(resolve, ms + jitter));
}

/**
 * Явная имитация сбоя для показа экранов ошибок: ?mockFail=search|hotel|cabinet|publish|all.
 * Только в mock-режиме; в API-режиме ошибки настоящие.
 */
export function maybeFail(operation: 'search' | 'hotel' | 'cabinet' | 'publish') {
  if (typeof location === 'undefined') return;
  const fail = new URLSearchParams(location.search).get('mockFail');
  if (fail === operation || fail === 'all') {
    throw new DataError('network', `Демо: имитация недоступного сервиса (mockFail=${fail}). Уберите параметр из адреса, чтобы продолжить.`);
  }
}
