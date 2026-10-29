import { lazy, Suspense, useMemo, useState } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { GuestLayout } from '../components/layout/GuestLayout';
import { Filters } from '../components/results/Filters';
import { RefinementBar } from '../components/results/RefinementBar';
import { DEFAULT_FILTERS, type FilterState } from '../components/results/filterState';
import { HotelCard } from '../components/results/HotelCard';
import type { MapPin } from '../components/SchematicMap';
import { Badge } from '../components/ui/Badge';
import { ButtonLink } from '../components/ui/Button';
import { Notice } from '../components/ui/Notice';
import { EmptyState, ErrorState } from '../components/ui/StateView';
import { Spinner } from '../components/ui/Spinner';
import { dataSource, useSearch, type HotelSummary, type ResultGroup } from '../data';
import { formatMoney, plural } from '../lib/format';
import { describeSearch, hasSearch, searchFromQuery, searchToQuery } from '../lib/searchUrl';
import styles from './ResultsPage.module.css';

// Карта (MapLibre ~250 КБ gzip) грузится отдельным чанком, не задерживая выдачу.
const HotelMap = lazy(() => import('../components/map/HotelMap'));

const shortName = (name: string) => (name.length > 18 ? `${name.slice(0, 17).trimEnd()}…` : name);

const GROUP_TITLES: Record<ResultGroup, string> = {
  confirmed: 'Условия подтверждены',
  partial: 'Не все условия подтверждены',
  excluded: 'Не подходят по обязательным условиям',
};

function applyFilters(hotels: HotelSummary[], filters: FilterState, pricesAvailable: boolean) {
  const from = Number(filters.priceFrom) || 0;
  const to = Number(filters.priceTo) || Infinity;
  return hotels.filter((h) => {
    if (filters.onlyConfirmed && h.group !== 'confirmed') return false;
    if (pricesAvailable && h.price && (h.price.amount < from || h.price.amount > to)) return false;
    return true;
  });
}

export function ResultsPage() {
  const [query] = useSearchParams();
  const params = useMemo(() => searchFromQuery(query, dataSource.getDefaultSearch()), [query]);
  const search = useSearch(params);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);
  const caps = dataSource.capabilities;

  if (!hasSearch(query)) return <Navigate to="/" replace />;

  const queryString = searchToQuery(params);
  const fallbackContext = describeSearch(params);
  const result = search.data;
  const all = result?.hotels ?? [];
  const visible = applyFilters(all, filters, caps.prices);
  const hiddenCount = all.length - visible.length;
  const byGroup = (g: ResultGroup) => visible.filter((h) => h.group === g);
  const confirmed = byGroup('confirmed');
  const partial = byGroup('partial');
  const excluded = byGroup('excluded');
  const listed = [...confirmed, ...partial];

  const pins: MapPin[] = listed.map((h) => ({
    id: h.id,
    name: h.name,
    label: h.price ? formatMoney(h.price) : shortName(h.name),
    coords: h.coords,
    tone: h.group,
  }));

  function selectFromMap(id: string) {
    setActiveId(id);
    const card = document.getElementById(`hotel-${id}`);
    card?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card?.focus({ preventScroll: true });
  }

  const hrefFor = (h: HotelSummary) => `/hotels/${encodeURIComponent(h.id)}?${queryString}`;
  const renderCards = (hotels: HotelSummary[]) => (
    <div className={styles.cards}>
      {hotels.map((h) => (
        <HotelCard key={h.id} hotel={h} hotelHref={hrefFor(h)} active={activeId === h.id} onHover={setActiveId} />
      ))}
    </div>
  );

  return (
    <GuestLayout context={result?.contextLabel ?? fallbackContext}>
      <div className={styles.titleRow}>
        <h1 className={styles.title}>Отели под ваши пожелания</h1>
        <ButtonLink to={`/?${queryString}`} variant="secondary" className={styles.edit}>
          Изменить запрос
        </ButtonLink>
      </div>

      {result && result.chips.length > 0 && (
        <ul className={styles.chips} aria-label="Как мы поняли запрос">
          {result.chips.map((chip) => (
            <li key={chip.label}>
              <Badge tone={chip.kind === 'unsupported' ? 'warning' : 'primary'} size="m">
                {chip.label}
              </Badge>
            </li>
          ))}
        </ul>
      )}
      {result && result.skipped.length > 0 && (
        <Notice tone="warning" className={styles.notice} title="Ищем без условий, которые система пока не умеет проверять">
          <ul className={styles.skipped}>
            {result.skipped.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>
            <Link to={`/search?${searchToQuery({ ...params, skipUnclear: false })}`}>Вернуть условие</Link> или{' '}
            <Link to={`/?${searchToQuery({ ...params, skipUnclear: false })}`}>изменить запрос</Link>.
          </p>
        </Notice>
      )}
      {result && result.refinements.length > 0 && (
        <RefinementBar refinements={result.refinements} params={params} busy={search.isFetching} />
      )}
      {result?.modelUnavailable && (
        <Notice tone="warning" className={styles.notice}>
          Языковая модель сейчас недоступна — запрос разобран упрощённо, свободные формулировки могут быть поняты не полностью.
        </Notice>
      )}
      {result && result.unsupported.length > 0 && (
        <Notice tone="info" className={styles.notice}>
          Не реализовано в текущей версии, поэтому не учитывается в подборе: {result.unsupported.join(', ')}.
        </Notice>
      )}
      {result && result.ignoredTerms.length > 0 && (
        <Notice tone="warning" className={styles.notice}>
          Эти слова не удалось связать с характеристиками отелей, в подборе они не учитываются: {result.ignoredTerms.join(', ')}.
        </Notice>
      )}

      <div className={styles.toolbar}>
        <button type="button" className={styles.toggle} aria-expanded={filtersOpen} aria-controls="filters-panel" onClick={() => setFiltersOpen((v) => !v)}>
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <path d="M2 4h14M5 9h8M7.5 14h3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          Фильтры{hiddenCount > 0 ? ` · скрыто ${hiddenCount}` : ''}
        </button>
        <button type="button" className={styles.toggle} aria-expanded={mapOpen} aria-controls="map-panel" onClick={() => setMapOpen((v) => !v)}>
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <path d="M6.5 2.5 2 4.5v11l4.5-2 5 2 4.5-2v-11l-4.5 2-5-2Zm0 0v11m5-9v11" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
          </svg>
          {mapOpen ? 'Скрыть карту' : 'Карта'}
        </button>
      </div>

      <div className={styles.layout}>
        <aside id="filters-panel" className={`${styles.filters} ${filtersOpen ? styles.open : ''}`}>
          <Filters
            value={filters}
            onChange={setFilters}
            pricesAvailable={caps.prices}
            hiddenCount={hiddenCount}
            onReset={() => setFilters(DEFAULT_FILTERS)}
          />
        </aside>

        <section className={styles.results} aria-label="Результаты" aria-busy={search.isFetching || undefined}>
          {search.isPending && (
            <div className={styles.loading} role="status">
              <div className={styles.loadingHead}>
                <Spinner />
                <p>Подбираем отели и проверяем условия по источникам…</p>
              </div>
              {[0, 1].map((i) => (
                <div key={i} className={styles.skeleton} aria-hidden="true">
                  <span className={styles.skPhoto} />
                  <span className={styles.skLines}>
                    <span />
                    <span />
                    <span />
                  </span>
                </div>
              ))}
            </div>
          )}

          {search.isError && <ErrorState title="Не удалось подобрать отели" error={search.error} onRetry={() => search.refetch()} />}

          {result?.status === 'needs_clarification' && (
            <EmptyState
              title="Уточните запрос"
              action={
                <div className={styles.clarifyActions}>
                  {result.canSearchAnyway && (
                    <ButtonLink to={`/search?${searchToQuery({ ...params, skipUnclear: true })}`}>Искать без этого условия</ButtonLink>
                  )}
                  <ButtonLink to={`/?${queryString}`} variant={result.canSearchAnyway ? 'secondary' : 'primary'}>
                    Изменить запрос
                  </ButtonLink>
                </div>
              }
            >
              <p>{result.clarification}</p>
              {result.canSearchAnyway && (
                <p>Можно искать по остальным пожеланиям — это условие останется в списке над результатами.</p>
              )}
            </EmptyState>
          )}

          {result?.status === 'ok' && all.length === 0 && (
            <EmptyState title="Подходящих отелей не нашли" action={<ButtonLink to={`/?${queryString}`}>Изменить запрос</ButtonLink>}>
              {result.notes.map((n) => (
                <p key={n}>{n}</p>
              ))}
            </EmptyState>
          )}

          {result?.status === 'ok' && all.length > 0 && visible.length === 0 && (
            <EmptyState
              title="Все варианты скрыты фильтрами"
              action={
                <button type="button" className={styles.resetLink} onClick={() => setFilters(DEFAULT_FILTERS)}>
                  Сбросить фильтры
                </button>
              }
            >
              <p>
                {all.length} {plural(all.length, ['вариант', 'варианта', 'вариантов'])} не прошли бюджет или требование подтверждённых условий.
              </p>
            </EmptyState>
          )}

          {result?.status === 'ok' && visible.length > 0 && (
            <>
              {search.isFetching && !search.isPending && (
                <p className={styles.refreshing} role="status">
                  <Spinner size={16} /> Обновляем выдачу…
                </p>
              )}
              {(confirmed.length > 0 || !filters.onlyConfirmed) && (
                <section className={styles.group} aria-labelledby="group-confirmed">
                  <h2 id="group-confirmed" className={styles.groupTitle}>
                    {GROUP_TITLES.confirmed}
                  </h2>
                  {confirmed.length > 0 ? (
                    renderCards(confirmed)
                  ) : (
                    <p className={styles.groupEmpty}>Пока ни один вариант не подтверждён по всем условиям. Ниже — где не хватает данных.</p>
                  )}
                </section>
              )}
              {partial.length > 0 && (
                <section className={styles.group} aria-labelledby="group-partial">
                  <h2 id="group-partial" className={styles.groupTitle}>
                    {GROUP_TITLES.partial}
                  </h2>
                  {renderCards(partial)}
                </section>
              )}
              {excluded.length > 0 && (
                <details className={styles.excluded}>
                  <summary className={styles.excludedSummary}>
                    {GROUP_TITLES.excluded} · {excluded.length}
                  </summary>
                  {renderCards(excluded)}
                </details>
              )}
              {result.notes.length > 0 && (
                <ul className={styles.notes}>
                  {result.notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>

        <div id="map-panel" className={`${styles.map} ${mapOpen ? styles.open : ''}`}>
          {search.isPending && <div className={styles.mapSkeleton} aria-hidden="true" />}
          {pins.length > 0 && (
            <Suspense fallback={<div className={styles.mapSkeleton} aria-hidden="true" />}>
              <HotelMap
                pins={pins}
                activeId={activeId}
                onSelect={selectFromMap}
                onHover={setActiveId}
                seaSide={dataSource.mode === 'mock' ? 'east' : 'southwest'}
                fallbackCaption="Схема по координатам"
              />
            </Suspense>
          )}
        </div>
      </div>
    </GuestLayout>
  );
}
