import type { Criterion } from '../data';
import { Badge } from './ui/Badge';
import styles from './CriteriaList.module.css';

interface Props {
  criteria: Criterion[];
  /** confirmed — зелёные галочки как в макете; muted — известные условия серым. */
  tone: 'confirmed' | 'muted';
  size?: 'm' | 'l';
}

function Icon({ state }: { state: Criterion['state'] }) {
  if (state === 'violated') {
    return (
      <svg className={styles.icon} width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (state === 'weak') {
    return (
      <svg className={styles.icon} width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M3 7h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg className={styles.icon} width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <path d="m2.5 7.4 3 3 6-6.4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const STATE_LABEL: Record<Criterion['state'], string> = {
  met: 'выполнено',
  weak: 'выполнено частично',
  unknown: 'нет данных',
  violated: 'не выполнено',
};

export function CriteriaList({ criteria, tone, size = 'm' }: Props) {
  const known = criteria.filter((c) => c.state !== 'unknown');
  const unknown = criteria.filter((c) => c.state === 'unknown');
  return (
    <div className={`${styles.wrap} ${styles[size]}`}>
      {known.length > 0 && (
        <ul className={styles.list}>
          {known.map((c) => (
            <li key={c.key} className={[styles.item, styles[c.state], tone === 'muted' && c.state === 'met' ? styles.mutedMet : ''].join(' ')}>
              <Icon state={c.state} />
              <span>
                {c.text}
                <span className="visually-hidden">
                  {' '}
                  — {STATE_LABEL[c.state]}
                  {c.required ? ', обязательное условие' : ''}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {unknown.map((c) => (
        <Badge key={c.key} tone="warning" className={styles.unknown}>
          {c.text}
        </Badge>
      ))}
      {criteria.some((c) => c.conflict) && (
        <p className={styles.conflict}>⚠ Источники расходятся — подробности в «Источниках».</p>
      )}
    </div>
  );
}
