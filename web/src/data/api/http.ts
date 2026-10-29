import { DataError } from '../errors';

const BASE = '/api';

interface FastApiValidationItem {
  loc?: (string | number)[];
  msg?: string;
}

function detailText(detail: unknown): string | null {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return (detail as FastApiValidationItem[])
      .map((item) => item.msg ?? '')
      .filter(Boolean)
      .join('; ');
  }
  if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message: unknown }).message);
  return null;
}

/** Тонкая обёртка над fetch. Ошибку не скрывает и не подменяет моками. */
export async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers: body === undefined ? { Accept: 'application/json' } : { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new DataError(
      'network',
      'Сервис временно недоступен. Проверьте подключение к интернету и попробуйте ещё раз.',
    );
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    // Бэкенд отвечает { code, detail } (app/schemas/errors.py); detail — строка или список ошибок валидации.
    const body = payload && typeof payload === 'object' ? (payload as { code?: string; detail?: unknown }) : null;
    const detail = body && 'detail' in body ? detailText(body.detail) : null;
    if (response.status === 404) throw new DataError('not_found', detail ?? 'Не найдено', 404);
    if (response.status === 409 || body?.code === 'state_conflict') {
      throw new DataError('state_conflict', detail ?? 'Состояние уже изменилось — обновите страницу.', 409);
    }
    // Тексты 5xx — для разработчиков (ключи, модели, порты); гостю показываем понятное
    // сообщение, а техническую причину — в консоль.
    if (response.status >= 500 || body?.code === 'service_unavailable') {
      if (detail) console.warn(`[${method} ${path}] ${response.status}: ${detail}`);
      throw new DataError(
        'network',
        path.startsWith('/search')
          ? 'Не получилось обработать запрос. Попробуйте ещё раз или сформулируйте иначе.'
          : 'Сервис временно недоступен. Попробуйте ещё раз через минуту.',
        response.status,
      );
    }
    throw new DataError('http', detail ?? 'Что-то пошло не так. Попробуйте ещё раз.', response.status);
  }
  return payload as T;
}

export const get = <T>(path: string) => request<T>('GET', path);
export const post = <T>(path: string, body: unknown) => request<T>('POST', path, body);
