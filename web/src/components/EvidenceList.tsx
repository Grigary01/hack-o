import type { EvidenceLine } from '../data';
import styles from './EvidenceList.module.css';

export function EvidenceList({ lines, warnings = [] }: { lines: EvidenceLine[]; warnings?: string[] }) {
  if (lines.length === 0 && warnings.length === 0) {
    return <p className={styles.empty}>Источников по вашему запросу пока нет.</p>;
  }
  return (
    <div className={styles.wrap}>
      <ul className={styles.list}>
        {lines.map((line, i) => (
          <li key={`${line.title}-${i}`} className={styles.item}>
            <p>
              <strong className={styles.title}>{line.title}:</strong> {line.text}
            </p>
            {(line.note || line.url) && (
              <p className={styles.note}>
                {line.note}
                {line.url && (
                  <>
                    {line.note ? ' · ' : ''}
                    <a href={line.url} target="_blank" rel="noreferrer">
                      на карте<span className="visually-hidden"> (откроется в новой вкладке)</span>
                    </a>
                  </>
                )}
              </p>
            )}
          </li>
        ))}
      </ul>
      {warnings.length > 0 && (
        <ul className={styles.warnings}>
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
