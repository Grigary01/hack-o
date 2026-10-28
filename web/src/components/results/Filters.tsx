import { useId } from 'react';
import { Checkbox, TextField } from '../ui/Field';
import { DEFAULT_FILTERS, type FilterState } from './filterState';
import styles from './Filters.module.css';


interface Props {
  value: FilterState;
  onChange: (next: FilterState) => void;
  pricesAvailable: boolean;
  hiddenCount: number;
  onReset: () => void;
}

const digits = (value: string) => value.replace(/\D/g, '').slice(0, 7);
const pretty = (value: string) => (value ? new Intl.NumberFormat('ru-RU').format(Number(value)) : '');

export function Filters({ value, onChange, pricesAvailable, hiddenCount, onReset }: Props) {
  const titleId = useId();
  const changed =
    value.onlyConfirmed || (pricesAvailable && (value.priceFrom !== DEFAULT_FILTERS.priceFrom || value.priceTo !== DEFAULT_FILTERS.priceTo));

  return (
    <section className={styles.filters} aria-labelledby={titleId}>
      <h2 id={titleId} className={styles.title}>
        Фильтры
      </h2>

      <fieldset className={styles.group} disabled={!pricesAvailable}>
        <legend className={styles.legend}>Бюджет за ночь</legend>
        <TextField
          label="От"
          inputMode="numeric"
          value={pricesAvailable ? pretty(value.priceFrom) : ''}
          placeholder={pricesAvailable ? 'Любой' : '—'}
          suffix={pricesAvailable && value.priceFrom ? '₽' : undefined}
          onChange={(e) => onChange({ ...value, priceFrom: digits(e.target.value) })}
        />
        <TextField
          label="До"
          inputMode="numeric"
          value={pricesAvailable ? pretty(value.priceTo) : ''}
          placeholder={pricesAvailable ? 'Любой' : '—'}
          suffix={pricesAvailable && value.priceTo ? '₽' : undefined}
          onChange={(e) => onChange({ ...value, priceTo: digits(e.target.value) })}
        />
        <p className={styles.hint}>{pricesAvailable ? 'Демо-цены: тарифов в API пока нет.' : 'Цены не подключены к API — фильтр недоступен.'}</p>
      </fieldset>

      <Checkbox
        className={styles.check}
        label="Только подтверждённые условия"
        checked={value.onlyConfirmed}
        onChange={(e) => onChange({ ...value, onlyConfirmed: e.target.checked })}
      />

      {(changed || hiddenCount > 0) && (
        <div className={styles.footer} aria-live="polite">
          {hiddenCount > 0 && <p className={styles.hint}>Скрыто фильтрами: {hiddenCount}</p>}
          {changed && (
            <button type="button" className={styles.reset} onClick={onReset}>
              Сбросить фильтры
            </button>
          )}
        </div>
      )}
    </section>
  );
}
