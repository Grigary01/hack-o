import { dataMode } from '../../data';
import styles from './SiteFooter.module.css';

export function SiteFooter({ inset }: { inset?: boolean }) {
  return (
    <footer className={`${styles.footer} ${inset ? styles.inset : ''}`}>
      <p>
        {dataMode === 'mock'
          ? 'Демонстрационные отели, цены и характеристики'
          : 'Отели и характеристики — из API (OpenStreetMap и расчёты). Цены и бронирование не подключены.'}
      </p>
    </footer>
  );
}
