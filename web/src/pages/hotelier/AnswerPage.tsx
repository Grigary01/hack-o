import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Notice } from '../../components/ui/Notice';
import { ErrorState, Loading } from '../../components/ui/StateView';
import { errorMessage, useQuestion, useSubmitAnswer } from '../../data';
import { useCabinet } from './cabinetContext';
import c from './cabinet.module.css';
import styles from './AnswerPage.module.css';

interface Draft {
  text: string;
  savedAt: string;
}

const draftKey = (questionId: string) => `ostrovok.draft.${questionId}`;

function readDraft(questionId: string): Draft | null {
  try {
    return JSON.parse(localStorage.getItem(draftKey(questionId)) ?? 'null') as Draft | null;
  } catch {
    return null;
  }
}

export function AnswerPage() {
  const { questionId = '' } = useParams();
  const { base } = useCabinet();
  const question = useQuestion(questionId);

  if (question.isPending) return <Loading label="Загружаем вопрос…" />;
  if (question.isError) {
    return (
      <ErrorState title="Вопрос не найден" error={question.error} onRetry={() => question.refetch()}>
        <Link to={`${base}/questions`}>Ко всем вопросам</Link>
      </ErrorState>
    );
  }
  return <AnswerForm key={question.data.id} questionId={question.data.id} />;
}

function AnswerForm({ questionId }: { questionId: string }) {
  const { base } = useCabinet();
  const question = useQuestion(questionId).data!;
  const navigate = useNavigate();
  const location = useLocation();
  const submit = useSubmitAnswer();
  const fromReview = (location.state as { text?: string } | null)?.text;
  const [text, setText] = useState(() => fromReview ?? readDraft(questionId)?.text ?? '');
  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(() => (fromReview ? null : (readDraft(questionId)?.savedAt ?? null)));
  const [error, setError] = useState<string | null>(null);
  const [photo, setPhoto] = useState<{ name: string; url: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const areaId = useId();
  const hintId = useId();

  useEffect(() => () => (photo ? URL.revokeObjectURL(photo.url) : undefined), [photo]);

  function saveDraft() {
    const draft: Draft = { text, savedAt: new Date().toISOString() };
    localStorage.setItem(draftKey(questionId), JSON.stringify(draft));
    setDraftSavedAt(draft.savedAt);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) {
      setError('Напишите ответ — хотя бы одно предложение.');
      document.getElementById(areaId)?.focus();
      return;
    }
    setError(null);
    submit.mutate(
      { questionId, text: text.trim() },
      {
        onSuccess: (answer) => {
          localStorage.removeItem(draftKey(questionId));
          navigate(`${base}/answers/${encodeURIComponent(answer.id)}/review`);
        },
      },
    );
  }

  const savedTime = draftSavedAt ? new Date(draftSavedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : null;

  return (
    <form className={c.stack} onSubmit={onSubmit} noValidate>
      <Link to={`${base}/questions`} className={c.backLink}>
        ← Все вопросы
      </Link>
      <div className={styles.head}>
        <h1 className={c.pageTitle}>{question.featureLabel}</h1>
        <p className={styles.ask}>{question.ask}</p>
      </div>

      {question.status === 'answered' && (
        <Notice tone="info">Вы уже отвечали на этот вопрос. Новый ответ после проверки заменит сведения в подборе; история сохранится.</Notice>
      )}

      <div className={`${styles.box} ${error ? styles.boxError : ''}`}>
        <label htmlFor={areaId} className={styles.boxLabel}>
          Ваш ответ
        </label>
        <textarea
          id={areaId}
          className={styles.area}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (error) setError(null);
          }}
          placeholder={question.answerPlaceholder}
          maxLength={3000}
          rows={6}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={[hintId, error ? `${areaId}-error` : ''].filter(Boolean).join(' ')}
        />
      </div>
      <p id={hintId} className={`${c.small} ${styles.hint}`}>
        {question.answerHint}
      </p>
      {error && (
        <p id={`${areaId}-error`} className={styles.error} role="alert">
          {error}
        </p>
      )}

      <div className={styles.photoRow}>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="visually-hidden"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) setPhoto({ name: file.name, url: URL.createObjectURL(file) });
            e.target.value = '';
          }}
        />
        <Button variant="secondary" className={styles.photoButton} onClick={() => fileRef.current?.click()}>
          Прикрепить фото
        </Button>
        {photo && (
          <div className={styles.photo}>
            <img src={photo.url} alt="" width={48} height={48} />
            <span>{photo.name}</span>
            <button type="button" className={styles.remove} onClick={() => setPhoto(null)}>
              Убрать<span className="visually-hidden"> фото {photo.name}</span>
            </button>
          </div>
        )}
      </div>
      {photo && (
        <Notice tone="warning" live>
          Фото видно только вам: отправка фотографий не реализована в текущей версии, к ответу оно не прикрепится.
        </Notice>
      )}

      <Card padding="m">
        <h2 className={c.cardTitle}>Вы проверите данные до публикации</h2>
        <p className={c.cardText}>Разложим ответ по характеристикам. Перед сохранением вы сможете всё проверить.</p>
      </Card>

      {submit.isError && (
        <Notice tone="danger" live title="Не удалось отправить ответ">
          {errorMessage(submit.error)}
        </Notice>
      )}

      <div className={c.actions}>
        <Button type="submit" loading={submit.isPending} loadingLabel="Разбираем ответ…">
          Проверить данные
        </Button>
        <Button variant="secondary" onClick={saveDraft} disabled={!text.trim()}>
          Сохранить черновик
        </Button>
      </div>
      <p className={c.small} role="status" aria-live="polite">
        {savedTime ? `Черновик сохранён в этом браузере в ${savedTime}.` : ''}
      </p>
    </form>
  );
}
