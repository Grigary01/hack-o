import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { dataSource, errorMessage, useRequestCheck, type HotelSummary } from '../../data';
import { formatMoney } from '../../lib/format';
import { CriteriaList } from '../CriteriaList';
import { EvidenceList } from '../EvidenceList';
import { HotelPhoto } from '../HotelPhoto';
import { Button, ButtonLink } from '../ui/Button';
import { Notice } from '../ui/Notice';
import styles from './HotelCard.module.css';

interface Props {
  hotel: HotelSummary;
  hotelHref: string;
  active: boolean;
  onHover: (id: string | null) => void;
}

export function HotelCard({ hotel, hotelHref, active, onHover }: Props) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const sourcesId = useId();
  const titleId = useId();
  const request = useRequestCheck();
  const askable = hotel.criteria.filter((c) => c.state === 'unknown' && c.askable).map((c) => c.key);
  const tone = hotel.group === 'confirmed' ? 'confirmed' : 'muted';

  return (
    <article
      id={`hotel-${hotel.id}`}
      tabIndex={-1}
      aria-labelledby={titleId}
      className={[styles.card, styles[hotel.group], active ? styles.active : ''].join(' ')}
      onMouseEnter={() => onHover(hotel.id)}
      onMouseLeave={() => onHover(null)}
    >
      <div className={styles.media}>
        <Link to={hotelHref} className={styles.photoLink} tabIndex={-1} aria-hidden="true">
          <HotelPhoto photo={hotel.photo} />
        </Link>
        {hotel.group === 'partial' && <p className={styles.mediaNote}>Можно продолжить поиск</p>}
      </div>

      <div className={styles.body}>
        <div className={styles.head}>
          <h3 id={titleId} className={styles.name}>
            <Link to={hotelHref} className={styles.nameLink}>
              {hotel.name}
            </Link>
          </h3>
          {hotel.price ? (
            <p className={styles.price}>
              от {formatMoney(hotel.price)} / ночь <span className={styles.demoTag}>демо-цена</span>
            </p>
          ) : (
            <p className={styles.area}>
              {hotel.area}
              {hotel.roomHint ? ` · ${hotel.roomHint}` : ''}
            </p>
          )}
        </div>

        {hotel.criteria.length > 0 ? (
          <CriteriaList criteria={hotel.criteria} tone={tone} />
        ) : (
          <p className={styles.area}>Пожелания не распознаны — показываем отель без проверки условий.</p>
        )}

        {request.isSuccess ? (
          <Notice tone="success" live>
            <p>{request.data.message}</p>
            {request.data.cabinetPath && (
              <p>
                <Link to={request.data.cabinetPath}>Ответить за отельера (демо-кабинет)</Link>
              </p>
            )}
          </Notice>
        ) : (
          request.isError && (
            <Notice tone="danger" live>
              Не удалось отправить вопрос: {errorMessage(request.error)}
            </Notice>
          )
        )}

        <div className={styles.actions}>
          {hotel.group === 'partial' && askable.length > 0 && !request.isSuccess ? (
            <>
              <Button
                variant="secondary"
                loading={request.isPending}
                loadingLabel="Отправляем…"
                onClick={() => request.mutate({ hotelId: hotel.id, featureKeys: askable })}
                aria-describedby={`${titleId}-ask`}
              >
                {dataSource.capabilities.guestNotifications ? 'Запросить и уведомить' : 'Запросить у отельера'}
              </Button>
              <span id={`${titleId}-ask`} className="visually-hidden">
                Спросить отельера {hotel.name} о недостающих условиях
              </span>
            </>
          ) : (
            <ButtonLink to={hotelHref} variant={hotel.group === 'excluded' ? 'secondary' : 'primary'}>
              Посмотреть номер
            </ButtonLink>
          )}
          <Button variant="link" aria-expanded={sourcesOpen} aria-controls={sourcesId} onClick={() => setSourcesOpen((v) => !v)}>
            {sourcesOpen ? 'Скрыть источники' : 'Источники'}
          </Button>
        </div>
        {hotel.pendingQuestion && hotel.group !== 'confirmed' && !request.isSuccess && (
          <p className={styles.pending}>Агент уже спросил отельера — ответ появится в следующих подборах.</p>
        )}

        <div id={sourcesId} className={styles.sources} hidden={!sourcesOpen}>
          <EvidenceList lines={hotel.evidence} warnings={hotel.warnings} />
          {hotel.sourceUrl && (
            <a className={styles.osm} href={hotel.sourceUrl} target="_blank" rel="noreferrer">
              Карточка отеля в OpenStreetMap<span className="visually-hidden"> (откроется в новой вкладке)</span>
            </a>
          )}
        </div>
      </div>
    </article>
  );
}
