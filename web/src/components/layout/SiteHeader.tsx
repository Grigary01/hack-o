import { Link } from 'react-router-dom';
import { dataMode } from '../../data';
import styles from './SiteHeader.module.css';

interface Props {
  /** «Батуми · 12–16 июня · 2 взрослых» или «Тихий двор · Представитель отеля». */
  context?: string | null;
  variant?: 'default' | 'hero';
  cabinet?: boolean;
}

export function SiteHeader({ context, variant = 'default', cabinet }: Props) {
  return (
    <header className={`${styles.header} ${styles[variant]}`}>
      <div className={styles.inner}>
        <Link to={cabinet ? '/hotelier' : '/'} className={styles.logo}>
          Островок{cabinet && <span className={styles.logoSuffix}> · Кабинет отельера</span>}
        </Link>
        {dataMode === 'mock' && (
          <span className={styles.demo} title="Демонстрационные отели и цены">
            Демо
          </span>
        )}
        {context && <p className={styles.context}>{context}</p>}
        <nav className={styles.nav} aria-label="Разделы">
          {cabinet ? <Link to="/">Поиск отелей</Link> : <Link to="/hotelier">Кабинет отельера</Link>}
        </nav>
      </div>
    </header>
  );
}
