import styles from './SkipLink.module.css';

export function SkipLink() {
  return (
    <a className={styles.skip} href="#main">
      Перейти к содержимому
    </a>
  );
}
