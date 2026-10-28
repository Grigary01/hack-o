import type { ReactNode } from 'react';
import styles from './Notice.module.css';

interface NoticeProps {
  tone?: 'info' | 'success' | 'warning' | 'danger';
  title?: string;
  children?: ReactNode;
  /** polite — для сообщений после действия (сохранено, отправлено). */
  live?: boolean;
  className?: string;
}

export function Notice({ tone = 'info', title, children, live, className }: NoticeProps) {
  return (
    <div
      className={[styles.notice, styles[tone], className].filter(Boolean).join(' ')}
      role={live ? (tone === 'danger' ? 'alert' : 'status') : undefined}
      aria-live={live ? (tone === 'danger' ? 'assertive' : 'polite') : undefined}
    >
      {title && <p className={styles.title}>{title}</p>}
      {children && <div className={styles.body}>{children}</div>}
    </div>
  );
}
