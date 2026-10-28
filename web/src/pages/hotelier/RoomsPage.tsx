import { ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState, ErrorState, Loading } from '../../components/ui/StateView';
import { dataSource, useRooms } from '../../data';
import { useCabinet } from './cabinetContext';
import c from './cabinet.module.css';
import styles from './RoomsPage.module.css';

export function RoomsPage() {
  const { hotelId, base } = useCabinet();
  const rooms = useRooms(hotelId);
  const byCategory = dataSource.capabilities.roomCategories;

  if (rooms.isPending) return <Loading label="Загружаем номера…" />;
  if (rooms.isError) return <ErrorState title="Номера не загрузились" error={rooms.error} onRetry={() => rooms.refetch()} />;

  return (
    <div className={c.stack}>
      <h1 className={c.pageTitle}>{byCategory ? 'Категории номеров' : 'Номера'}</h1>
      <p className={`${c.lead} ${c.muted}`}>
        {byCategory
          ? 'Сведения по категориям номеров (демо): API пока не хранит категории.'
          : 'Номера появляются здесь после подтверждённых ответов на вопросы. Список категорий API пока не хранит.'}
      </p>
      {rooms.data.length === 0 ? (
        <EmptyState
          title="Сведений о номерах пока нет"
          action={
            <ButtonLink to={`${base}/questions`} variant="secondary">
              К вопросам
            </ButtonLink>
          }
        >
          <p>Ответьте на вопрос о конкретных номерах — и гости увидят, в каких из них есть нужное.</p>
        </EmptyState>
      ) : (
        <ul className={styles.grid}>
          {rooms.data.map((room) => (
            <li key={room.id}>
              <Card as="article" padding="m" className={styles.card}>
                <h2 className={styles.title}>
                  {room.title}
                  {room.note && <span className={styles.note}> · {room.note.toLowerCase()}</span>}
                </h2>
                <dl className={styles.facts}>
                  {room.facts.map((fact) => (
                    <div key={fact.label + fact.source} className={styles.fact}>
                      <dt className={c.small}>{fact.label}</dt>
                      <dd className={styles.value}>{fact.value}</dd>
                      <dd className={c.small}>{fact.source}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
