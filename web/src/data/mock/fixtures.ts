/**
 * Демонстрационные данные. Это НЕ данные бэкенда: город (Батуми), цены, категории
 * номеров и характеристика «шторы blackout» сейчас не поддерживаются API
 * (в app/features/registry.yaml нет ключа blackout_curtains). Всё помечено в UI как демо.
 */

export type Quietness = 'high' | 'medium' | 'low';

export interface CategoryClaim {
  category: string;
  note: string | null;
  value: boolean;
  detail: string;
}

export type BlackoutState =
  | { status: 'unknown' }
  | { status: 'answered'; claims: CategoryClaim[]; quote: string; answeredAt: string };

export interface MockHotel {
  id: string;
  name: string;
  area: string;
  coords: { lat: number; lon: number };
  photoIndex: number;
  pricePerNight: number;
  room: { category: string; note: string };
  beachMeters: number;
  /** Минуты до круглосуточного магазина; null — в OSM нет данных о часах. */
  shopMinutes: number | null;
  quiet: Quietness;
  blackout: BlackoutState;
  categories: { name: string; note: string | null }[];
}

export interface MockQuestion {
  id: string;
  hotelId: string;
  featureKey: 'blackout_curtains';
  status: 'open' | 'answered';
  createdAt: string;
}

export interface MockAnswer {
  id: string;
  questionId: string;
  text: string;
  claims: { id: string; category: string; note: string | null; value: boolean; detail: string; quote: string }[];
  unparsed: string[];
  status: 'pending' | 'confirmed' | 'rejected';
  createdAt: string;
  publishedAt?: string;
}

export interface MockState {
  version: 1;
  hotels: MockHotel[];
  questions: MockQuestion[];
  answers: MockAnswer[];
  /** Гости, попросившие уведомить об ответе: hotelId. */
  notify: string[];
}

const DAY = 86_400_000;
const daysAgo = (n: number) => new Date(Date.now() - n * DAY).toISOString();

export const DEMO_DESTINATION = 'Батуми';

export const DEMO_QUERY = 'Прилетаем поздно. Нужен номер со шторами blackout, магазин ночью и море пешком.';

export const DEMO_EXAMPLES = [
  DEMO_QUERY,
  'Нужен номер с blackout и тихо ночью',
  'Хочу до моря не больше 10 минут пешком и круглосуточный магазин рядом',
  'Тихий отель у моря с бассейном',
];

export const FEATURE_COPY = {
  key: 'blackout_curtains',
  label: 'Затемнение номера',
  short: 'Blackout',
  title: 'Есть ли в номерах шторы blackout?',
  prompt: 'Уточните категории номеров и полностью ли шторы перекрывают дневной свет.',
  ask: 'В каких номерах установлены шторы blackout?',
  why: 'Гости ищут номер с затемнением. Пока это условие не подтверждено.',
  hint: 'Пишите своими словами: по категориям номеров, с уточнениями. Перед публикацией вы проверите, как мы поняли ответ.',
  placeholder:
    'Например: в улучшенных номерах, окнами во двор, есть шторы blackout — они полностью перекрывают дневной свет. В стандартных номерах обычные шторы.',
} as const;

export function initialState(): MockState {
  return {
    version: 1,
    hotels: [
      {
        id: 'demo-primorsky',
        name: 'Приморский',
        area: 'Батуми, Приморский бульвар',
        coords: { lat: 41.648, lon: 41.633 },
        photoIndex: 0,
        pricePerNight: 9200,
        room: { category: 'Улучшенный номер', note: 'окна во двор' },
        beachMeters: 920,
        shopMinutes: 4,
        quiet: 'medium',
        categories: [
          { name: 'Улучшенный', note: 'Окна во двор' },
          { name: 'Стандартный', note: null },
        ],
        blackout: {
          status: 'answered',
          quote: 'В улучшенных номерах установлены шторы blackout',
          answeredAt: daysAgo(3),
          claims: [
            { category: 'Улучшенный', note: 'Окна во двор', value: true, detail: 'Полностью перекрывают дневной свет' },
            { category: 'Стандартный', note: null, value: false, detail: 'Обычные шторы' },
          ],
        },
      },
      {
        id: 'demo-tikhiy-dvor',
        name: 'Тихий двор',
        area: 'Батуми, Старый город (у Пьяццы)',
        coords: { lat: 41.6497, lon: 41.6395 },
        photoIndex: 1,
        pricePerNight: 8400,
        room: { category: 'Улучшенный номер', note: 'окна во двор' },
        beachMeters: 700,
        shopMinutes: 6,
        quiet: 'high',
        categories: [
          { name: 'Улучшенный', note: 'Окна во двор' },
          { name: 'Стандартный', note: null },
        ],
        blackout: { status: 'unknown' },
      },
      {
        id: 'demo-morskaya-milya',
        name: 'Морская миля',
        area: 'Батуми, Новый бульвар (ул. Шерифа Химшиашвили)',
        coords: { lat: 41.6315, lon: 41.603 },
        photoIndex: 2,
        pricePerNight: 12600,
        room: { category: 'Номер делюкс', note: 'вид на море' },
        beachMeters: 210,
        shopMinutes: null,
        quiet: 'medium',
        categories: [
          { name: 'Делюкс', note: 'Вид на море' },
          { name: 'Стандартный', note: null },
        ],
        blackout: {
          status: 'answered',
          quote: 'Во всех номерах делюкс есть плотные шторы blackout',
          answeredAt: daysAgo(12),
          claims: [{ category: 'Делюкс', note: 'Вид на море', value: true, detail: 'Плотные шторы blackout' }],
        },
      },
      {
        id: 'demo-staryi-batumi',
        name: 'Старый Батуми',
        area: 'Батуми, ул. Руставели',
        coords: { lat: 41.644, lon: 41.642 },
        photoIndex: 3,
        pricePerNight: 6900,
        room: { category: 'Стандартный номер', note: 'окна на улицу' },
        beachMeters: 1400,
        shopMinutes: 3,
        quiet: 'low',
        categories: [{ name: 'Стандартный', note: 'Окна на улицу' }],
        blackout: {
          status: 'answered',
          quote: 'Штор blackout в отеле нет, только обычные',
          answeredAt: daysAgo(30),
          claims: [{ category: 'Стандартный', note: 'Окна на улицу', value: false, detail: 'Обычные шторы' }],
        },
      },
      {
        id: 'demo-bulvar-residence',
        name: 'Бульвар Резиденс',
        area: 'Батуми, Приморский бульвар',
        coords: { lat: 41.647, lon: 41.624 },
        photoIndex: 4,
        pricePerNight: 16800,
        room: { category: 'Люкс', note: 'вид на море' },
        beachMeters: 150,
        shopMinutes: 5,
        quiet: 'medium',
        categories: [{ name: 'Люкс', note: 'Вид на море' }],
        blackout: {
          status: 'answered',
          quote: 'В люксах установлены шторы blackout',
          answeredAt: daysAgo(8),
          claims: [{ category: 'Люкс', note: 'Вид на море', value: true, detail: 'Шторы blackout с электроприводом' }],
        },
      },
    ],
    questions: [
      { id: 'q-tikhiy-blackout', hotelId: 'demo-tikhiy-dvor', featureKey: 'blackout_curtains', status: 'open', createdAt: daysAgo(0) },
      { id: 'q-primorsky-blackout', hotelId: 'demo-primorsky', featureKey: 'blackout_curtains', status: 'answered', createdAt: daysAgo(4) },
    ],
    answers: [],
    notify: [],
  };
}
