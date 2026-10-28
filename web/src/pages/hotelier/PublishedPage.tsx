import { Link, useParams } from 'react-router-dom';
import { Badge } from '../../components/ui/Badge';
import { ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Notice } from '../../components/ui/Notice';
import { ErrorState, Loading } from '../../components/ui/StateView';
import { dataSource, usePublishResult } from '../../data';
import { formatDay } from '../../lib/format';
import { searchToQuery } from '../../lib/searchUrl';
import { useCabinet } from './cabinetContext';
import c from './cabinet.module.css';
import styles from './PublishedPage.module.css';

export function PublishedPage() {
  const { answerId = '' } = useParams();
  const { base } = useCabinet();
  const result = usePublishResult(answerId);

  if (result.isPending) return <Loading label="Загружаем опубликованные сведения…" />;
  if (result.isError) {
    return (
      <ErrorState title="Сведения не найдены" error={result.error}>
        <Link to={`${base}/questions`}>Вернуться к вопросам</Link>
      </ErrorState>
    );
  }

  const r = result.data;
  const guestSearch = `/search?${searchToQuery(dataSource.getDefaultSearch())}`;

  return (
    <div className={c.stack}>
      <div role="status" className={styles.status}>
        <Badge tone="success" className={styles.badge}>
          Характеристики обновлены
        </Badge>
      </div>
      <h1 className={`${c.pageTitle} ${styles.title}`}>{r.featureLabel}</h1>

      <ul className={styles.grid}>
        {r.claims.map((claim) => (
          <li key={claim.id}>
            <Card as="article" padding="m" className={styles.card}>
              <h2 className={styles.cardTitle}>
                {claim.subject}
                {claim.subjectNote ? ` · ${claim.subjectNote.toLowerCase()}` : ''}
              </h2>
              <Badge tone={claim.value ? 'success' : 'primary'} className={styles.value}>
                {r.featureShort} {claim.value ? 'есть' : 'нет'}
              </Badge>
              <p className={c.muted}>{claim.detail}</p>
            </Card>
          </li>
        ))}
      </ul>

      <dl className={c.meta}>
        <div>
          <dt className="visually-hidden">Источник</dt>
          <dd>Источник: {r.sourceLabel}</dd>
        </div>
        <div>
          <dt className="visually-hidden">Дата</dt>
          <dd>Подтверждено {formatDay(r.publishedAt)}</dd>
        </div>
        <div>
          <dt className="visually-hidden">Статус</dt>
          <dd>Статус: {r.statusLabel}</dd>
        </div>
      </dl>

      {r.conflicts.length > 0 && (
        <Notice tone="warning" title="Расходится с расчётом по зданию">
          <ul className={styles.conflicts}>
            {r.conflicts.map((x) => (
              <li key={x.subject + x.reason}>
                <strong>{x.subject}:</strong> {x.reason}
              </li>
            ))}
          </ul>
          <p>Ваш ответ сохранён и виден гостям с пометкой; расхождение разберёт оператор.</p>
        </Notice>
      )}

      <section className={styles.preview} aria-labelledby="preview-title">
        <h2 id="preview-title" className={styles.previewLabel}>
          Как увидит гость
        </h2>
        <p className={styles.previewText}>{r.guestPreview}</p>
        <p className={c.muted}>
          В подборе учитывается {dataSource.capabilities.roomCategories ? 'конкретная категория номера' : 'конкретный номер'}.
        </p>
      </section>

      <div className={c.actions}>
        <ButtonLink to={`${base}/questions/${encodeURIComponent(r.questionId)}`} variant="secondary">
          Изменить сведения
        </ButtonLink>
        <ButtonLink to={`${base}/facts`} className={styles.primary}>
          Ко всем характеристикам
        </ButtonLink>
      </div>

      <div className={styles.footnote}>
        <p>Данные доступны для следующих поисковых запросов.</p>
        <p>Ожидание ответа не блокирует поиск гостей.</p>
        <p>
          <Link to={guestSearch}>Открыть выдачу как гость</Link>
        </p>
      </div>
    </div>
  );
}
