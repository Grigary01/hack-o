import styles from './Spinner.module.css';

export function Spinner({ size = 20, tone = 'primary' }: { size?: number; tone?: 'primary' | 'inverse' }) {
  return (
    <svg className={`${styles.spinner} ${styles[tone]}`} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle className={styles.track} cx="12" cy="12" r="9" fill="none" strokeWidth="3" />
      <path className={styles.arc} d="M21 12a9 9 0 0 0-9-9" fill="none" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
