import { useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Notice } from '../../components/ui/Notice';
import { ErrorState, Loading } from '../../components/ui/StateView';
import { dataSource, errorMessage, useAnswer, usePublishAnswer, useQuestion, useRejectAnswer, type ParsedClaim } from '../../data';
import { useCabinet } from './cabinetContext';
import c from './cabinet.module.css';
import styles from './ReviewPage.module.css';

export function ReviewPage() {
  const { answerId = '' } = useParams();
  const { base } = useCabinet();
  const answer = useAnswer(answerId);

  if (answer.isPending) return <Loading label="Загружаем разбор ответа…" />;
  if (answer.isError) {
    return (
      <ErrorState title="Разбор ответа недоступен" error={answer.error}>
        <Link to={`${base}/questions`}>Вернуться к вопросам</Link>
      </ErrorState>
    );
  }
  if (answer.data.status === 'confirmed') return <Navigate to={`${base}/answers/${encodeURIComponent(answerId)}/published`} replace />;
  return <Review key={answer.data.id} answerId={answer.data.id} />;
}

function ValueToggle({ claim, value, editable, onToggle, featureShort }: { claim: ParsedClaim; value: boolean; editable: boolean; onToggle: () => void; featureShort: string }) {
  const label = value ? 'Есть' : 'Нет';
  if (!editable) {
    return (
      <Badge tone={value ? 'success' : 'primary'} className={styles.value}>
        {label}
      </Badge>
    );
  }
  return (
    <button
      type="button"
      className={`${styles.toggle} ${value ? styles.yes : styles.no}`}
      onClick={onToggle}
      aria-label={`${featureShort} в «${claim.subject}»: ${label.toLowerCase()}. Изменить на «${value ? 'нет' : 'есть'}»`}
    >
      {label} · изменить
    </button>
  );
}

function Review({ answerId }: { answerId: string }) {
  const { base } = useCabinet();
  const navigate = useNavigate();
  const answer = useAnswer(answerId).data!;
  const question = useQuestion(answer.questionId);
  const publish = usePublishAnswer();
  const reject = useRejectAnswer();
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  const caps = dataSource.capabilities;
  const featureShort = question.data?.featureShort ?? 'Значение';
  const featureColumn = caps.roomCategories ? `Шторы ${featureShort.toLowerCase()}` : (question.data?.featureLabel ?? 'Значение');
  const rejected = answer.status === 'rejected';
  const incomplete = answer.claims.length === 0 || answer.unparsed.length > 0;

  function valueOf(claim: ParsedClaim) {
    return overrides[claim.id] ?? claim.value;
  }

  function toggle(claim: ParsedClaim) {
    setOverrides((current) => {
      const next = { ...current };
      const flipped = !valueOf(claim);
      if (flipped === claim.value) delete next[claim.id];
      else next[claim.id] = flipped;
      return next;
    });
  }

  function editAnswer() {
    const goBack = () => navigate(`${base}/questions/${encodeURIComponent(answer.questionId)}`, { state: { text: answer.text } });
    if (rejected) return goBack();
    // Неподтверждённый ответ отклоняем: бэкенд хранит историю и не даёт переиспользовать pending.
    reject.mutate(answerId, { onSuccess: goBack });
  }

  return (
    <div className={c.stack}>
      <h1 className={c.pageTitle}>Проверьте, правильно ли мы поняли</h1>

      <Card padding="m">
        <h2 className={c.cardTitle}>Ваш исходный ответ</h2>
        <p className={c.cardText}>{answer.text}</p>
      </Card>

      {rejected && (
        <Notice tone="warning" title="Этот ответ отклонён">
          Измените формулировку и отправьте ответ заново — история прежних вариантов сохраняется.
        </Notice>
      )}

      {answer.claims.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption className="visually-hidden">Как мы разобрали ответ по {caps.roomCategories ? 'категориям номеров' : 'номерам'}</caption>
            <thead>
              <tr>
                <th scope="col">{caps.roomCategories ? 'Категория номера' : 'Номера'}</th>
                <th scope="col">{featureColumn}</th>
                <th scope="col">Уточнение</th>
              </tr>
            </thead>
            <tbody>
              {answer.claims.map((claim) => (
                <tr key={claim.id}>
                  <th scope="row" className={styles.subject}>
                    {claim.subject}
                    {claim.subjectNote && <span className={styles.subjectNote}>{claim.subjectNote}</span>}
                  </th>
                  <td data-label={featureColumn}>
                    <ValueToggle
                      claim={claim}
                      value={valueOf(claim)}
                      editable={caps.editClaims && !rejected}
                      onToggle={() => toggle(claim)}
                      featureShort={featureShort}
                    />
                    {claim.id in overrides && <span className={styles.changed}>изменено вами</span>}
                  </td>
                  <td data-label="Уточнение" className={styles.detail}>
                    {claim.detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!caps.editClaims && answer.claims.length > 0 && (
        <p className={c.small}>Если строка разобрана неверно, нажмите «Изменить ответ» и переформулируйте — правка отдельных строк не реализована в текущей версии.</p>
      )}

      {answer.unparsed.length > 0 && (
        <Notice tone="warning" title={answer.claims.length ? 'Часть ответа не удалось разобрать' : 'Не удалось разобрать ответ'}>
          <ul className={styles.unparsed}>
            {answer.unparsed.map((u) => (
              <li key={u}>«{u}»</li>
            ))}
          </ul>
          <p>Мы не угадываем непонятное. Измените ответ: одно утверждение на предложение, с {caps.roomCategories ? 'категорией номера' : 'номерами комнат'}.</p>
        </Notice>
      )}

      <Card padding="m">
        <h2 className={c.cardTitle}>Источник: ответ представителя отеля</h2>
        <p className={c.cardText}>
          Сведения сохранятся как заявление отельера, без независимой проверки.
          {dataSource.mode === 'api' && ' В текущей версии такие ответы отмечаются как тестовые.'}
        </p>
      </Card>

      {(publish.isError || reject.isError) && (
        <Notice tone="danger" live title="Не получилось">
          {errorMessage(publish.error ?? reject.error)}
        </Notice>
      )}

      <div className={c.actions}>
        <Button
          className={styles.publish}
          disabled={incomplete || rejected}
          loading={publish.isPending}
          loadingLabel="Публикуем…"
          aria-describedby={incomplete ? 'publish-blocked' : undefined}
          onClick={() =>
            publish.mutate(
              { answerId, overrides },
              { onSuccess: () => navigate(`${base}/answers/${encodeURIComponent(answerId)}/published`) },
            )
          }
        >
          Подтвердить и опубликовать
        </Button>
        <Button variant="secondary" onClick={editAnswer} loading={reject.isPending} loadingLabel="Открываем…">
          Изменить ответ
        </Button>
      </div>
      {incomplete && !rejected && (
        <p id="publish-blocked" className={c.small}>
          Опубликовать можно только полностью разобранный ответ.
        </p>
      )}
    </div>
  );
}
