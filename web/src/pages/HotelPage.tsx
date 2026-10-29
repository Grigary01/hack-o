import { useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { CriteriaList } from '../components/CriteriaList';
import { EvidenceList } from '../components/EvidenceList';
import { HotelPhoto } from '../components/HotelPhoto';
import { GuestLayout } from '../components/layout/GuestLayout';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Notice } from '../components/ui/Notice';
import { ErrorState, Loading } from '../components/ui/StateView';
import { dataSource, DataError, useHotel } from '../data';
import { formatMoney, plural } from '../lib/format';
import { describeSearch, hasSearch, searchFromQuery, searchToQuery } from '../lib/searchUrl';
import styles from './HotelPage.module.css';

export function HotelPage() {
  const { hotelId = '' } = useParams();
  const [query] = useSearchParams();
  const params = useMemo(() => (hasSearch(query) ? searchFromQuery(query, dataSource.getDefaultSearch()) : null), [query]);
  const hotel = useHotel(hotelId, params);
  const [bookingTried, setBookingTried] = useState(false);
  const backHref = params ? `/search?${searchToQuery(params)}` : '/';
  const context = params ? describeSearch(params) : null;

  return (
    <GuestLayout context={context}>
      <Link to={backHref} className={styles.back}>
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M13 8H3m4-4L3 8l4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {params ? 'К результатам' : 'На главную'}
      </Link>

      {hotel.isPending && <Loading label="Загружаем отель и основания подбора…" />}
      {hotel.isError && (
        <ErrorState
          title={hotel.error instanceof DataError && hotel.error.kind === 'not_found' ? 'Отель не найден' : 'Не удалось загрузить отель'}
          error={hotel.error}
          onRetry={() => hotel.refetch()}
        />
      )}

      {hotel.data && (
        <>
          <h1 className={styles.title}>{hotel.data.hotel.name}</h1>
          <div className={styles.layout}>
            <div className={styles.main}>
              <HotelPhoto variant="wide" photo={hotel.data.roomPhoto} priority />

              <div className={styles.roomHead}>
                <h2 className={styles.roomTitle}>
                  {hotel.data.room ? [hotel.data.room.title, hotel.data.room.subtitle].filter(Boolean).join(' · ') : hotel.data.hotel.area}
                </h2>
                {hotel.data.room && <p className={styles.muted}>{hotel.data.room.guests}</p>}
              </div>

              {(hotel.data.hotel.needRows.length > 0 || hotel.data.hotel.criteria.length > 0) && (
                <section className={styles.section} aria-labelledby="match-title">
                  <h2 id="match-title" className={styles.sectionTitle}>
                    Соответствие вашим пожеланиям
                  </h2>
                  <CriteriaList
                    criteria={hotel.data.hotel.needRows.length ? hotel.data.hotel.needRows : hotel.data.hotel.criteria}
                    tone="confirmed"
                    size="l"
                  />
                </section>
              )}

              <Card as="section" padding="m" className={styles.basis} aria-labelledby="basis-title">
                <h2 id="basis-title" className={styles.cardTitle}>
                  На чём основан подбор
                </h2>
                <EvidenceList lines={hotel.data.basis} />
                {(hotel.data.hotel.website || hotel.data.hotel.sourceUrl) && (
                  <p className={styles.links}>
                    {hotel.data.hotel.website && (
                      <a href={hotel.data.hotel.website} target="_blank" rel="noreferrer">
                        Сайт отеля — настоящие фото<span className="visually-hidden"> (откроется в новой вкладке)</span>
                      </a>
                    )}
                    {hotel.data.hotel.sourceUrl && (
                      <a href={hotel.data.hotel.sourceUrl} target="_blank" rel="noreferrer">
                        Отель на карте OpenStreetMap<span className="visually-hidden"> (откроется в новой вкладке)</span>
                      </a>
                    )}
                  </p>
                )}
              </Card>
            </div>

            <aside className={styles.side} aria-label="Выбор номера">
              <Card padding="l" className={styles.offer}>
                {hotel.data.room ? (
                  <>
                    <h2 className={styles.offerTitle}>{hotel.data.room.title}</h2>
                    {hotel.data.room.price ? (
                      <div className={styles.priceBlock}>
                        <p className={styles.price}>{formatMoney(hotel.data.room.price)} / ночь</p>
                        {hotel.data.room.nights && hotel.data.room.total && (
                          <p className={styles.total}>
                            {hotel.data.room.nights} {plural(hotel.data.room.nights, ['ночь', 'ночи', 'ночей'])} · {formatMoney(hotel.data.room.total)}
                          </p>
                        )}
                        <p className={styles.demoNote}>Демонстрационная цена</p>
                      </div>
                    ) : (
                      <p className={styles.muted}>Цены не реализованы в текущей версии.</p>
                    )}
                  </>
                ) : (
                  <>
                    <h2 className={styles.offerTitle}>Номер не выбран</h2>
                    <p className={styles.muted}>{hotel.data.roomUnavailableReason}</p>
                  </>
                )}
                <Button block onClick={() => setBookingTried(true)} aria-describedby="booking-note">
                  Выбрать номер
                </Button>
                {bookingTried ? (
                  <Notice tone="info" live>
                    Бронирование в демо не подключено: оно ждёт контракта бэкенда. Сохраните ссылку на эту страницу, чтобы вернуться к варианту.
                  </Notice>
                ) : (
                  <p id="booking-note" className={styles.muted}>
                    Бронирование не реализовано в текущей версии
                  </p>
                )}
              </Card>

              {hotel.data.caveats.length > 0 && (
                <Card tone="warning" padding="l" as="section" aria-label="Что не подтверждено">
                  <ul className={styles.caveats}>
                    {hotel.data.caveats.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </Card>
              )}
            </aside>
          </div>
        </>
      )}
    </GuestLayout>
  );
}
