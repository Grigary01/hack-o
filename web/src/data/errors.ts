export type DataErrorKind = 'network' | 'http' | 'not_found' | 'unsupported' | 'invalid' | 'state_conflict';

/** Ошибка слоя данных с понятным пользователю текстом. Моки и API бросают один и тот же тип. */
export class DataError extends Error {
  readonly kind: DataErrorKind;
  readonly status: number | null;

  constructor(kind: DataErrorKind, message: string, status: number | null = null) {
    super(message);
    this.name = 'DataError';
    this.kind = kind;
    this.status = status;
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof DataError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Неизвестная ошибка';
}
