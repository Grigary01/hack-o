/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const MODES = ['mock', 'api'] as const;

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // `vite --mode mock|api` задаёт режим данных напрямую; иначе берём VITE_DATA_MODE из .env*.
  // Юнит-тесты (mode=test) не зависят от бэкенда.
  const dataMode = (MODES as readonly string[]).includes(mode)
    ? mode
    : mode === 'test'
      ? env.VITE_DATA_MODE || 'mock'
      : env.VITE_DATA_MODE;
  if (!dataMode || !(MODES as readonly string[]).includes(dataMode)) {
    throw new Error(`VITE_DATA_MODE должен быть "mock" или "api", получено: ${String(dataMode)}`);
  }
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000';

  return {
    plugins: [react()],
    define: {
      // Режим фиксируется при сборке; во время работы приложение его не меняет.
      'import.meta.env.VITE_DATA_MODE': JSON.stringify(dataMode),
    },
    server: {
      port: Number(env.WEB_PORT || 5173),
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
        '/health': { target: apiTarget, changeOrigin: true },
      },
    },
    preview: {
      port: 4173,
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
      },
    },
    css: {
      modules: { localsConvention: 'camelCaseOnly' },
    },
    // Воркер карты MapLibre — ES-модуль (import внутри); собираем его тоже как ES.
    worker: { format: 'es' },
    test: {
      environment: 'node',
      include: ['src/**/*.test.ts'],
    },
  };
});
