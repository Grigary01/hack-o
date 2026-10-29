import { useState } from 'react';
import type { Photo } from '../data';
import styles from './HotelPhoto.module.css';

interface Props {
  photo: Photo;
  /** card — карточка выдачи, wide — фото номера на странице отеля. */
  variant?: 'card' | 'wide';
  className?: string;
  priority?: boolean;
}

/** Фото отеля/номера. Иллюстративные снимки всегда подписаны — их нельзя выдать за фото отеля. */
export function HotelPhoto({ photo, variant = 'card', className, priority }: Props) {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  return (
    <figure className={[styles.frame, styles[variant], styles[state], className].filter(Boolean).join(' ')}>
      {state !== 'error' && (
        <img
          className={styles.img}
          src={photo.src}
          alt={photo.alt}
          loading={priority ? 'eager' : 'lazy'}
          decoding="async"
          onLoad={() => setState('ready')}
          onError={() => setState('error')}
        />
      )}
      {photo.illustrative && <figcaption className={styles.badge}>Фото для примера</figcaption>}
    </figure>
  );
}
