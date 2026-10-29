/**
 * Фотографии для карточек. У отелей из OSM своих фото нет, поэтому показываем
 * стоковые снимки (Unsplash License, web/public/photos) с явной пометкой
 * «Фото для примера». Подбор детерминирован: один и тот же отель — одно и то же фото.
 */

export interface Photo {
  src: string;
  alt: string;
  /** true — не фото этого отеля, а иллюстрация. UI обязан это показать. */
  illustrative: boolean;
}

const HOTEL_PHOTOS = 8;
const ROOM_PHOTOS = 5;

/** Стабильный индекс по строке (FNV-1a), чтобы фото не «прыгали» между запросами. */
function stableIndex(key: string | number, size: number): number {
  if (typeof key === 'number') return Math.abs(key) % size;
  let hash = 2166136261;
  for (let i = 0; i < key.length; i += 1) {
    hash ^= key.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % size;
}

export function hotelPhoto(key: string | number, hotelName: string): Photo {
  return {
    src: `/photos/hotel-${stableIndex(key, HOTEL_PHOTOS) + 1}.webp`,
    alt: `Иллюстративное фото отеля, не «${hotelName}»`,
    illustrative: true,
  };
}

export function roomPhoto(key: string | number, roomTitle: string): Photo {
  return {
    src: `/photos/room-${stableIndex(key, ROOM_PHOTOS) + 1}.webp`,
    alt: `Иллюстративное фото номера, не «${roomTitle}»`,
    illustrative: true,
  };
}
