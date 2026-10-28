import { createMockSource } from './mock/source';
import type { DataMode, DataSource } from './types';

/**
 * Единственная точка выбора источника данных. Режим фиксируется при сборке
 * (VITE_DATA_MODE=mock|api) и не меняется во время работы: при ошибке API
 * приложение показывает ошибку, а не подменяет данные моками.
 */
export const dataMode: DataMode = import.meta.env.VITE_DATA_MODE;

function create(mode: DataMode): DataSource {
  switch (mode) {
    case 'api':
      // Адаптер FastAPI подключается отдельным шагом.
      throw new Error('Режим api ещё не реализован: используйте VITE_DATA_MODE=mock');
    case 'mock':
      return createMockSource();
    default:
      throw new Error(`Неизвестный VITE_DATA_MODE: ${String(mode)}`);
  }
}

export const dataSource: DataSource = create(dataMode);
