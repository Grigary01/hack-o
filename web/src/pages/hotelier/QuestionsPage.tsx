import { Link } from 'react-router-dom';
import { Badge } from '../../components/ui/Badge';
import { ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState, ErrorState, Loading } from '../../components/ui/StateView';
import { useQuestions, type HotelierQuestion } from '../../data';
import { formatDay } from '../../lib/format';
import { useCabinet } from './cabinetContext';
import c from './cabinet.module.css';
import styles from './QuestionsPage.module.css';

function QuestionCard({ question, href }: { question: HotelierQuestion; href: string }) {
  const titleId = `q-${question.id}`;
  return (
    <Card as="article" padding="l" className={styles.card} aria-labelledby={titleId}>
      <Badge tone="warning" className={styles.badge}>
        Нужен ваш ответ
      </Badge>
      <div className={styles.text}>
        <h2 id={titleId} className={styles.title}>
          {question.title}
        </h2>
        <p className={styles.prompt}>{question.prompt}</p>
      </div>
      <div className={styles.why}>
        <h3 className={styles.whyTitle}>Зачем это нужно</h3>
        <p className={styles.whyText}>{question.why}</p>
      </div>
      <dl className={c.meta}>
        <div className={styles.metaRow}>
          <dt>Признак:</dt> <dd>{question.featureLabel.toLowerCase()}</dd>
        </div>
        <div className={styles.metaRow}>
          <dt>Источник запроса:</dt> <dd>{question.requestedBy}</dd>
        </div>
      </dl>
      <div>
        <ButtonLink to={href} className={styles.answer} aria-describedby={titleId}>
          Ответить
        </ButtonLink>
      </div>
    </Card>
  );
}

export function QuestionsPage() {
  const { hotelId, base } = useCabinet();
  const questions = useQuestions(hotelId);

  if (questions.isPending) return <Loading label="Загружаем вопросы…" />;
  if (questions.isError) return <ErrorState title="Вопросы не загрузились" error={questions.error} onRetry={() => questions.refetch()} />;

  const open = questions.data.filter((q) => q.status === 'open');
  const answered = questions.data.filter((q) => q.status === 'answered');

  return (
    <div className={c.stack}>
      <h1 className={c.pageTitle}>Уточните условия проживания</h1>

      {open.length === 0 ? (
        <EmptyState
          title="Открытых вопросов нет"
          action={
            <ButtonLink to={`${base}/facts`} variant="secondary">
              Посмотреть характеристики
            </ButtonLink>
          }
        >
          <p>Вопросы появляются, когда гости ищут то, о чём ещё нет данных. Ожидание ответа не блокирует поиск гостей.</p>
        </EmptyState>
      ) : (
        <>
          <div className={styles.list}>
            {open.map((q) => (
              <QuestionCard key={q.id} question={q} href={`${base}/questions/${encodeURIComponent(q.id)}`} />
            ))}
          </div>
          <p className={`${c.muted} ${styles.footnote}`}>Один ответ будет использован в будущих подборах.</p>
        </>
      )}

      {answered.length > 0 && (
        <section className={styles.answered} aria-labelledby="answered-title">
          <h2 id="answered-title" className={styles.answeredTitle}>
            Отвеченные
          </h2>
          <ul className={styles.answeredList}>
            {answered.map((q) => (
              <li key={q.id} className={styles.answeredItem}>
                <div>
                  <p className={styles.answeredName}>{q.title}</p>
                  <p className={c.small}>
                    {q.featureLabel} · вопрос от {formatDay(q.createdAt)}
                  </p>
                </div>
                <Badge tone="success">Отвечено</Badge>
                <Link to={`${base}/questions/${encodeURIComponent(q.id)}`} className={styles.again}>
                  Ответить заново<span className="visually-hidden">: {q.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
