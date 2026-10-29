import { useNavigate } from 'react-router-dom';
import type { Refinement, SearchParams } from '../../data';
import { searchToQuery } from '../../lib/searchUrl';
import styles from './RefinementBar.module.css';

interface Props {
  refinements: Refinement[];
  params: SearchParams;
  busy?: boolean;
}

/**
 * «Какой вид важнее? [Любой] [На море] [На горы] [Закат]».
 * Сначала гость видит выдачу по всем вариантам; уточнение — по желанию, одним нажатием,
 * без повторного разбора текста (меняется только ?pick= в адресе).
 */
export function RefinementBar({ refinements, params, busy }: Props) {
  const navigate = useNavigate();
  if (!refinements.length) return null;

  function choose(concept: string, key: string | null) {
    const choices = { ...(params.choices ?? {}) };
    if (key) choices[concept] = key;
    else delete choices[concept];
    navigate(`/search?${searchToQuery({ ...params, choices })}`, { replace: true });
  }

  return (
    <div className={styles.bar} aria-busy={busy || undefined}>
      {refinements.map((r) => {
        const options = [{ key: null as string | null, label: 'Любой' }, ...r.options];
        return (
          <div key={r.concept} className={styles.row} role="group" aria-label={`${r.question} («${r.quote}»)`}>
            <p className={styles.question}>
              <span className={styles.quote}>«{r.quote}»</span> {r.question}
            </p>
            <div className={styles.options}>
              {options.map((o) => {
                const active = (r.chosen ?? null) === o.key;
                return (
                  <button
                    key={o.key ?? 'any'}
                    type="button"
                    className={`${styles.option} ${active ? styles.active : ''}`}
                    aria-pressed={active}
                    onClick={() => !active && choose(r.concept, o.key)}
                  >
                    {o.label}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
