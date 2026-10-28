import { Badge, type BadgeTone } from '../../components/ui/Badge';
import { Notice } from '../../components/ui/Notice';
import { EmptyState, ErrorState, Loading } from '../../components/ui/StateView';
import { useFacts, type HotelFact } from '../../data';
import { useCabinet } from './cabinetContext';
import c from './cabinet.module.css';
import styles from './FactsPage.module.css';

const STATUS: Record<HotelFact['status'], { label: string; tone: BadgeTone }> = {
  verified: { label: 'Проверено', tone: 'success' },
  estimated: { label: 'Расчёт', tone: 'primary' },
  hotelier: { label: 'Заявление отельера', tone: 'success' },
  unknown: { label: 'Нет данных', tone: 'warning' },
  conflicted: { label: 'Расхождение', tone: 'danger' },
  stale: { label: 'Устарело', tone: 'neutral' },
};

const CONFIDENCE: Record<HotelFact['confidence'], string> = {
  high: 'высокая',
  medium: 'средняя',
  low: 'низкая',
  unknown: '—',
};

export function FactsPage() {
  const { hotelId, hotelName } = useCabinet();
  const facts = useFacts(hotelId);

  if (facts.isPending) return <Loading label="Загружаем характеристики…" />;
  if (facts.isError) return <ErrorState title="Характеристики не загрузились" error={facts.error} onRetry={() => facts.refetch()} />;

  return (
    <div className={c.stack}>
      <h1 className={c.pageTitle}>Характеристики отеля</h1>
      <p className={`${c.lead} ${c.muted}`}>
        Что знают о {hotelName ? `«${hotelName}»` : 'отеле'} гости при подборе. Расчёты по открытым данным не перезаписываются вашими ответами — расхождения разбирает оператор.
      </p>
      {facts.data.conflicts > 0 && (
        <Notice tone="warning">Есть расхождения источников: {facts.data.conflicts}. Пока оператор не решит, поиск не использует спорные значения.</Notice>
      )}
      {facts.data.facts.length === 0 ? (
        <EmptyState title="Характеристик пока нет">
          <p>Они появятся после расчёта по открытым данным или вашего ответа на вопрос.</p>
        </EmptyState>
      ) : (
        <ul className={styles.list}>
          {facts.data.facts.map((fact) => {
            const status = STATUS[fact.status];
            return (
              <li key={fact.key} className={styles.item}>
                <div className={styles.main}>
                  <h2 className={styles.label}>{fact.label}</h2>
                  <p className={styles.value}>{fact.value}</p>
                  <p className={c.small}>{fact.explanation}</p>
                </div>
                <div className={styles.side}>
                  <Badge tone={status.tone}>{status.label}</Badge>
                  <p className={c.small}>
                    {fact.source}
                    <br />
                    Уверенность: {CONFIDENCE[fact.confidence]}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
