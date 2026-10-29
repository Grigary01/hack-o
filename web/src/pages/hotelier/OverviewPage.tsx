import { Link } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Notice } from '../../components/ui/Notice';
import { ErrorState, Loading } from '../../components/ui/StateView';
import { dataSource, useFacts, useQuestions, useResetDemo, useRooms } from '../../data';
import { plural } from '../../lib/format';
import { useCabinet } from './cabinetContext';
import c from './cabinet.module.css';
import styles from './OverviewPage.module.css';

export function OverviewPage() {
  const { hotelId, hotelName, base } = useCabinet();
  const questions = useQuestions(hotelId);
  const facts = useFacts(hotelId);
  const rooms = useRooms(hotelId);
  const reset = useResetDemo();

  if (questions.isPending || facts.isPending || rooms.isPending) return <Loading label="Собираем обзор…" />;
  const error = questions.error ?? facts.error ?? rooms.error;
  if (error) {
    return (
      <ErrorState
        title="Обзор не загрузился"
        error={error}
        onRetry={() => {
          void questions.refetch();
          void facts.refetch();
          void rooms.refetch();
        }}
      />
    );
  }

  const open = questions.data?.filter((q) => q.status === 'open').length ?? 0;
  const factCount = facts.data?.facts.length ?? 0;
  const unknown = facts.data?.facts.filter((f) => f.status === 'unknown').length ?? 0;
  const roomCount = rooms.data?.length ?? 0;

  const tiles = [
    {
      to: `${base}/questions`,
      value: open,
      label: plural(open, ['открытый вопрос', 'открытых вопроса', 'открытых вопросов']),
      hint: open ? 'Гости ждут уточнений' : 'Все вопросы закрыты',
      accent: open > 0,
    },
    {
      to: `${base}/facts`,
      value: factCount,
      label: plural(factCount, ['характеристика', 'характеристики', 'характеристик']),
      hint: unknown ? `Без данных: ${unknown}` : 'Всё известно',
      accent: false,
    },
    {
      to: `${base}/rooms`,
      value: roomCount,
      label: dataSource.capabilities.roomCategories ? plural(roomCount, ['категория номеров', 'категории номеров', 'категорий номеров']) : plural(roomCount, ['номер со сведениями', 'номера со сведениями', 'номеров со сведениями']),
      hint: 'Из ответов отельера',
      accent: false,
    },
  ];

  return (
    <div className={c.stack}>
      <h1 className={c.pageTitle}>{hotelName || 'Обзор'}</h1>
      <p className={`${c.lead} ${c.muted}`}>Что гости знают о вашем отеле и где не хватает сведений.</p>

      <ul className={styles.tiles}>
        {tiles.map((t) => (
          <li key={t.to}>
            <Link to={t.to} className={`${styles.tile} ${t.accent ? styles.accent : ''}`}>
              <span className={styles.value}>{t.value}</span>
              <span className={styles.label}>{t.label}</span>
              <span className={styles.hint}>{t.hint}</span>
            </Link>
          </li>
        ))}
      </ul>

      <Card padding="m">
        <h2 className={c.cardTitle}>Как это работает</h2>
        <p className={c.cardText}>
          Когда гость ищет то, чего нет в открытых данных, мы задаём вам вопрос. Вы отвечаете своими словами, проверяете разбор — и ответ
          сразу учитывается во всех следующих подборах. Ожидание ответа не блокирует поиск.
        </p>
      </Card>

      {dataSource.mode === 'api' ? (
        <Notice tone="info">
          Вход для отелей не реализован в текущей версии: кабинет любого отеля можно открыть и ответить от его имени. Такие ответы
          отмечаются как тестовые.
        </Notice>
      ) : (
        <Notice tone="info" title="Демо-режим">
          <p>Состояние демо хранится в этой вкладке. Чтобы показать сценарий заново, сбросьте его.</p>
          <p>
            <Button variant="secondary" size="m" loading={reset.isPending} onClick={() => reset.mutate()}>
              Сбросить демо
            </Button>
            {reset.isSuccess && <span className={styles.resetDone}> Демо сброшено.</span>}
          </p>
        </Notice>
      )}
    </div>
  );
}
