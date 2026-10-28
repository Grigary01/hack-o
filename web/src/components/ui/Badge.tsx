import type { ReactNode } from 'react';
import styles from './Badge.module.css';

export type BadgeTone = 'primary' | 'success' | 'warning' | 'danger' | 'neutral';

interface BadgeProps {
  tone?: BadgeTone;
  size?: 's' | 'm';
  children: ReactNode;
  className?: string;
}

/** Плашка статуса/метки. Тон дублируется текстом: смысл не передаётся только цветом. */
export function Badge({ tone = 'primary', size = 's', children, className }: BadgeProps) {
  return <span className={[styles.badge, styles[tone], styles[size], className].filter(Boolean).join(' ')}>{children}</span>;
}
