import type { ReactNode } from 'react';
import { errorMessage } from '../../data';
import { Button } from './Button';
import { Spinner } from './Spinner';
import styles from './StateView.module.css';

export function Loading({ label = 'Загружаем…', compact }: { label?: string; compact?: boolean }) {
  return (
    <div className={`${styles.state} ${compact ? styles.compact : ''}`} role="status" aria-live="polite">
      <Spinner size={28} />
      <p className={styles.muted}>{label}</p>
    </div>
  );
}

export function ErrorState({ error, onRetry, title = 'Не удалось загрузить данные', children }: { error: unknown; onRetry?: () => void; title?: string; children?: ReactNode }) {
  return (
    <div className={`${styles.state} ${styles.error}`} role="alert">
      <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
        <circle cx="20" cy="20" r="18" fill="var(--c-danger-soft)" />
        <path d="M20 11v11" stroke="var(--c-danger)" strokeWidth="3" strokeLinecap="round" />
        <circle cx="20" cy="28" r="2" fill="var(--c-danger)" />
      </svg>
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.muted}>{errorMessage(error)}</p>
      {children}
      {onRetry && (
        <Button variant="secondary" size="m" onClick={onRetry}>
          Повторить
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className={styles.state}>
      <svg width="56" height="56" viewBox="0 0 56 56" aria-hidden="true">
        <rect x="6" y="10" width="44" height="36" rx="8" fill="var(--c-primary-soft)" />
        <circle cx="25" cy="27" r="8" fill="none" stroke="var(--c-primary)" strokeWidth="3" />
        <path d="M31 33l6 6" stroke="var(--c-primary)" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <h2 className={styles.title}>{title}</h2>
      {children && <div className={styles.muted}>{children}</div>}
      {action}
    </div>
  );
}
