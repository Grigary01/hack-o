/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Задаётся при сборке в vite.config.ts; другие значения сборка отклоняет. */
  readonly VITE_DATA_MODE: 'mock' | 'api';
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
