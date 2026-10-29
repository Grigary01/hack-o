/**
 * Доменная модель интерфейса. Её возвращают оба адаптера (mock и api),
 * компоненты знают только эти типы и ничего не знают о форме ответов FastAPI.
 */

export type DataMode = 'mock' | 'api';

/** Что источник данных умеет на самом деле. UI показывает недоступное честно, а не имитирует. */
export interface Capabilities {
  /** Есть ли цены. В mock — демонстрационные, в API их нет. */
  prices: boolean;
  /** Бронирование не поддержано ни в одном режиме. */
  booking: false;
  /** Ответ отельера по категориям номеров (mock) или по номерам комнат (API). */
  roomCategories: boolean;
  /** Можно ли поправить отдельную строку разбора перед публикацией. */
  editClaims: boolean;
  /** Подписка гостя на уведомление об ответе отельера. */
  guestNotifications: boolean;
  /** Можно ли выбрать направление (API знает только прибрежный Адлер). */
  freeDestination: boolean;
}

export interface Money {
  amount: number;
  currency: 'RUB';
  /** Всегда true: реальных цен у бэкенда пока нет. */
  demo: true;
}

export interface SearchParams {
  text: string;
  destination: string;
  checkIn: string;
  checkOut: string;
  guests: number;
}

export interface HealthInfo {
  ok: boolean;
  label: string;
  details?: string;
}

/** met — условие выполнено по имеющимся данным; weak — известно, но совпадает частично. */
export type CriterionState = 'met' | 'weak' | 'unknown' | 'violated';

export interface Criterion {
  key: string;
  /** Короткое имя, например «Blackout» или «До пляжа». */
  name: string;
  /** Полная строка для карточки: «До пляжа — 12 мин пешком». */
  text: string;
  state: CriterionState;
  required: boolean;
  /** Можно ли спросить отельера (характеристика из его ответа). */
  askable: boolean;
  /** Пояснение с источником: «Ответ отельера. Независимо не проверено». */
  source: string;
  conflict?: string;
}

export interface EvidenceLine {
  title: string;
  text: string;
  note?: string;
  url?: string;
}

export interface RequestChip {
  label: string;
  kind: 'required' | 'preference' | 'unsupported';
}

export type ResultGroup = 'confirmed' | 'partial' | 'excluded';

export interface HotelSummary {
  id: string;
  name: string;
  area: string;
  coords: { lat: number; lon: number };
  group: ResultGroup;
  price: Money | null;
  /** Какая категория/номер подходит: «Улучшенный номер» или «Номер 301». */
  roomHint: string | null;
  criteria: Criterion[];
  evidence: EvidenceLine[];
  warnings: string[];
  /** Агент уже отправил отельеру вопрос по неизвестной характеристике. */
  pendingQuestion: boolean;
  /** Номер для иллюстрации: разные отели получают разные цвета рисунка. */
  illustration: number;
  sourceUrl?: string;
}

export interface SearchResult {
  status: 'ok' | 'needs_clarification';
  clarification: string | null;
  contextLabel: string;
  chips: RequestChip[];
  ignoredTerms: string[];
  hotels: HotelSummary[];
  /** Пояснения о качестве данных, общие для выдачи. */
  notes: string[];
}

export interface RoomOffer {
  title: string;
  subtitle: string;
  guests: string;
  price: Money | null;
  nights: number | null;
  total: Money | null;
}

export interface HotelDetail {
  hotel: HotelSummary;
  room: RoomOffer | null;
  roomUnavailableReason: string | null;
  basis: EvidenceLine[];
  caveats: string[];
}

export interface CheckRequestResult {
  questionIds: string[];
  message: string;
  /** Куда отправить демонстратора, чтобы ответить за отельера. */
  cabinetPath: string | null;
}

/* ---------- Кабинет отельера ---------- */

export interface HotelierHotel {
  id: string;
  name: string;
  openQuestions: number;
}

export interface HotelierQuestion {
  id: string;
  hotelId: string;
  hotelName: string;
  featureKey: string;
  /** Название признака: «Затемнение номера». */
  featureLabel: string;
  /** Короткое имя для бейджей: «Blackout». */
  featureShort: string;
  /** Заголовок карточки: «Есть ли в номерах шторы blackout?». */
  title: string;
  /** Подзаголовок: что именно уточнить. */
  prompt: string;
  /** Вопрос на странице ответа: «В каких номерах установлены шторы blackout?». */
  ask: string;
  why: string;
  requestedBy: string;
  status: 'open' | 'answered';
  createdAt: string;
  /** Подсказка, как сформулировать ответ, чтобы его разобрали. */
  answerHint: string;
  answerPlaceholder: string;
  /** Неподтверждённый ответ, к проверке которого можно вернуться. */
  pendingAnswerId: string | null;
  /** Почему вопрос снова открыт: «ответ разобран не полностью», «источники расходятся»… */
  statusNote: string | null;
}

export interface ParsedClaim {
  id: string;
  /** «Улучшенный» или «Номера 301–303». */
  subject: string;
  subjectNote: string | null;
  value: boolean;
  detail: string;
  quote: string;
}

export interface HotelierAnswer {
  id: string;
  questionId: string;
  text: string;
  claims: ParsedClaim[];
  unparsed: string[];
  status: 'pending' | 'confirmed' | 'rejected';
  createdAt: string;
}

export interface PublishConflict {
  subject: string;
  reason: string;
}

export interface PublishResult {
  answerId: string;
  questionId: string;
  featureLabel: string;
  featureShort: string;
  claims: ParsedClaim[];
  conflicts: PublishConflict[];
  publishedAt: string;
  /** Как гость увидит факт в выдаче. */
  guestPreview: string;
  sourceLabel: string;
  statusLabel: string;
}

export interface HotelFact {
  key: string;
  label: string;
  value: string;
  status: 'verified' | 'estimated' | 'unknown' | 'conflicted' | 'stale' | 'hotelier';
  confidence: 'high' | 'medium' | 'low' | 'unknown';
  explanation: string;
  source: string;
  reviewedByHotelier: boolean;
}

export interface HotelierFacts {
  facts: HotelFact[];
  conflicts: number;
}

export interface HotelierRoom {
  id: string;
  title: string;
  note: string | null;
  facts: { label: string; value: string; source: string }[];
}

export interface Suggestions {
  /** Быстрые пожелания: подпись чипа и фраза, которую он добавляет в запрос. */
  chips: { label: string; phrase: string }[];
  examples: string[];
}

export interface DataSource {
  mode: DataMode;
  capabilities: Capabilities;
  getHealth(): Promise<HealthInfo>;
  getDefaultSearch(): SearchParams;
  getSuggestions(): Promise<Suggestions>;
  search(params: SearchParams): Promise<SearchResult>;
  getHotel(hotelId: string, params: SearchParams | null): Promise<HotelDetail>;
  requestCheck(hotelId: string, featureKeys: string[]): Promise<CheckRequestResult>;

  listHotelierHotels(): Promise<HotelierHotel[]>;
  listQuestions(hotelId: string): Promise<HotelierQuestion[]>;
  getQuestion(questionId: string): Promise<HotelierQuestion>;
  submitAnswer(questionId: string, text: string): Promise<HotelierAnswer>;
  getAnswer(answerId: string): Promise<HotelierAnswer>;
  rejectAnswer(answerId: string): Promise<void>;
  /** overrides — правки значений по id строки; в API не поддержаны. */
  publishAnswer(answerId: string, overrides: Record<string, boolean>): Promise<PublishResult>;
  getPublishResult(answerId: string): Promise<PublishResult>;
  getFacts(hotelId: string): Promise<HotelierFacts>;
  getRooms(hotelId: string): Promise<HotelierRoom[]>;
  /** Только mock: вернуть демо в исходное состояние. */
  resetDemo?(): Promise<void>;
}
