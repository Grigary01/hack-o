import type { HTMLAttributes, ReactNode } from 'react';
import styles from './Card.module.css';

interface CardProps extends HTMLAttributes<HTMLElement> {
  as?: 'section' | 'article' | 'div' | 'aside';
  padding?: 's' | 'm' | 'l';
  tone?: 'surface' | 'muted' | 'primary' | 'warning';
  children: ReactNode;
}

export function Card({ as: Tag = 'div', padding = 'm', tone = 'surface', className, children, ...rest }: CardProps) {
  return (
    <Tag className={[styles.card, styles[`pad${padding}`], styles[tone], className].filter(Boolean).join(' ')} {...rest}>
      {children}
    </Tag>
  );
}
