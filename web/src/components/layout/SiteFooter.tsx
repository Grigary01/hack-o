import { dataMode } from '../../data';
import styles from './SiteFooter.module.css';

export function SiteFooter({ inset }: { inset?: boolean }) {
  return (
    <footer className={`${styles.footer} ${inset ? styles.inset : ''}`}>
      <p>
        {dataMode === 'mock'
          ? 'Демонстрационные отели, цены и характеристики'
          : 'Текущая версия: отели Адлера, характеристики — по открытым картам OpenStreetMap и нашим расчётам. Цены, бронирование и вход для отелей не реализованы в текущей версии; ответы отелей — тестовые.'}
      </p>
    </footer>
  );
}
