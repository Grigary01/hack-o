import { useId, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { SiteFooter } from '../components/layout/SiteFooter';
import { SiteHeader } from '../components/layout/SiteHeader';
import { SkipLink } from '../components/layout/SkipLink';
import { Button } from '../components/ui/Button';
import { SelectField, TextArea, TextField } from '../components/ui/Field';
import { dataSource, useSuggestions } from '../data';
import { plural } from '../lib/format';
import { searchFromQuery, searchToQuery } from '../lib/searchUrl';
import styles from './HomePage.module.css';

const STEPS = [
  { title: 'Опишите поездку своими словами', text: '«Прилетаем поздно, нужен тёмный номер и магазин рядом» — без фильтров и галочек.' },
  { title: 'Проверяем по данным', text: 'Маршруты и заведения из OpenStreetMap, расчёты и ответы отельеров — с источником у каждого факта.' },
  { title: 'Чего нет — спрашиваем', text: 'Неизвестное не угадываем: агент задаёт вопрос отельеру, а ответ попадает в следующие подборы.' },
];

export function HomePage() {
  const navigate = useNavigate();
  const [query] = useSearchParams();
  const defaults = dataSource.getDefaultSearch();
  const initial = searchFromQuery(query, defaults);
  const [text, setText] = useState(initial.text);
  const [destination, setDestination] = useState(initial.destination);
  const [checkIn, setCheckIn] = useState(initial.checkIn);
  const [checkOut, setCheckOut] = useState(initial.checkOut);
  const [guests, setGuests] = useState(initial.guests);
  const [errors, setErrors] = useState<{ text?: string; dates?: string }>({});
  const suggestions = useSuggestions();
  const caps = dataSource.capabilities;
  const chipsLabel = useId();

  function addPhrase(phrase: string) {
    setText((current) => {
      const trimmed = current.trim();
      if (trimmed.toLowerCase().includes(phrase.toLowerCase())) return current;
      if (!trimmed) return phrase[0]!.toUpperCase() + phrase.slice(1);
      return `${trimmed.replace(/[.!]?$/, ',')} ${phrase}`;
    });
    setErrors((e) => ({ ...e, text: undefined }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const next: typeof errors = {};
    if (!text.trim()) next.text = 'Опишите, что важно в поездке — хотя бы пару слов.';
    if (checkIn && checkOut && checkOut <= checkIn) next.dates = 'Дата выезда должна быть позже даты заезда.';
    setErrors(next);
    if (next.text || next.dates) {
      document.getElementById(next.text ? 'wish-text' : 'check-out')?.focus();
      return;
    }
    navigate(`/search?${searchToQuery({ text: text.trim(), destination, checkIn, checkOut, guests })}`);
  }

  const dateHint = caps.prices ? undefined : 'Пока не влияет на подбор';

  return (
    <div className={styles.page}>
      <SkipLink />
      <div className={styles.hero}>
        <SiteHeader variant="hero" />
        <main id="main" tabIndex={-1} className={styles.heroInner}>
          <h1 className={styles.title}>
            Найдём отель
            <br />
            под ваши пожелания
          </h1>

          <p className={styles.tab}>
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3 18v-6.5A2.5 2.5 0 0 1 5.5 9H19a2 2 0 0 1 2 2v7M3 15h18M3 18v2M21 18v2M7 9V7a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            Жильё
          </p>

          <form className={styles.form} onSubmit={submit} noValidate aria-label="Поиск отеля">
            <div className={styles.row}>
              <TextField
                className={styles.destination}
                label="Направление"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="Город, отель или аэропорт"
                disabled={!caps.freeDestination}
                hint={caps.freeDestination ? undefined : 'API поддерживает только прибрежный Адлер'}
                autoComplete="off"
              />
              <div className={styles.dates}>
                <TextField label="Заезд" type="date" value={checkIn} onChange={(e) => setCheckIn(e.target.value)} hint={dateHint} />
                <TextField
                  id="check-out"
                  label="Выезд"
                  type="date"
                  value={checkOut}
                  min={checkIn || undefined}
                  onChange={(e) => setCheckOut(e.target.value)}
                  aria-invalid={Boolean(errors.dates) || undefined}
                />
              </div>
              <SelectField className={styles.guests} label="1 номер для" value={guests} onChange={(e) => setGuests(Number(e.target.value))}>
                {[1, 2, 3, 4, 5, 6].map((n) => (
                  <option key={n} value={n}>
                    {n} {plural(n, ['гостя', 'гостей', 'гостей'])}
                  </option>
                ))}
              </SelectField>
            </div>
            {errors.dates && (
              <p className={styles.error} role="alert">
                {errors.dates}
              </p>
            )}

            <div className={styles.wishCard}>
              <TextArea
                id="wish-text"
                label="Что важно для проживания?"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  if (errors.text) setErrors((x) => ({ ...x, text: undefined }));
                }}
                rows={3}
                maxLength={2000}
                placeholder="Например: прилетаем поздно, нужен тёмный номер, магазин ночью и море пешком"
                aria-invalid={Boolean(errors.text) || undefined}
                aria-describedby={errors.text ? 'wish-error' : undefined}
              />
              {errors.text && (
                <p id="wish-error" className={styles.error} role="alert">
                  {errors.text}
                </p>
              )}
              {suggestions.data && (
                <div className={styles.chips} role="group" aria-labelledby={chipsLabel}>
                  <span id={chipsLabel} className="visually-hidden">
                    Добавить пожелание в запрос
                  </span>
                  {suggestions.data.chips.map((chip) => (
                    <button key={chip.label} type="button" className={styles.chip} onClick={() => addPhrase(chip.phrase)}>
                      {chip.label}
                    </button>
                  ))}
                </div>
              )}
              <div className={styles.submitRow}>
                <Button type="submit">Найти отели</Button>
              </div>
              <p className={styles.note}>Используем уже собранные данные, маршруты и ответы отельеров.</p>
            </div>
          </form>
        </main>
      </div>

      <section className={styles.sheet} aria-labelledby="examples-title">
        <div className={styles.sheetInner}>
          <div className={styles.sheetHead}>
            <h2 id="examples-title" className={styles.sheetTitle}>
              Попробуйте запрос
            </h2>
            <p className={styles.sheetLead}>
              {dataSource.mode === 'mock'
                ? 'Демо-сценарий: Батуми, шторы blackout, магазин ночью и море пешком.'
                : 'Проверенные формулировки из /api/demo-queries — их понимает разбор запроса без LLM.'}
            </p>
          </div>
          {suggestions.isError && <p className={styles.note}>Примеры запросов не загрузились — напишите свой.</p>}
          <ul className={styles.examples}>
            {(suggestions.data?.examples ?? []).slice(0, 6).map((example) => (
              <li key={example}>
                <button
                  type="button"
                  className={styles.example}
                  onClick={() => {
                    setText(example);
                    document.getElementById('wish-text')?.focus();
                  }}
                >
                  <span>{example}</span>
                  <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
                    <path d="M7 4l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>

          <h2 className={styles.sheetTitle}>Как это работает</h2>
          <ol className={styles.steps}>
            {STEPS.map((step, i) => (
              <li key={step.title} className={styles.step}>
                <span className={styles.stepNum} aria-hidden="true">
                  {i + 1}
                </span>
                <h3 className={styles.stepTitle}>{step.title}</h3>
                <p className={styles.stepText}>{step.text}</p>
              </li>
            ))}
          </ol>
          <p className={styles.hotelier}>
            Вы отельер? <Link to="/hotelier">Ответьте на вопросы гостей в кабинете</Link> — один ответ используется во всех будущих подборах.
          </p>
        </div>
        <SiteFooter />
      </section>
    </div>
  );
}
