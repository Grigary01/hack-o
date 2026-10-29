import { compactNumbers, formatDay, formatGuests } from '../../lib/format';
import { DataError } from '../errors';
import type {
  Capabilities,
  CheckRequestResult,
  DataSource,
  HotelDetail,
  HotelSummary,
  HotelierAnswer,
  HotelierRoom,
  PublishConflict,
  PublishResult,
  Refinement,
  SearchParams,
  SearchResult,
} from '../types';
import type {
  AnswerDto,
  ConflictDto,
  ConfirmResponseDto,
  ModelReviewDto,
  FactsResponseDto,
  FeatureRegistryDto,
  HealthDto,
  HotelDetailDto,
  HotelEvidenceDto,
  HotelDto,
  QuestionDto,
  SearchRequestDto,
  SearchResponseDto,
} from './contract';
import { get, post } from './http';
import { hotelPhoto, roomPhoto } from '../photos';
import { evidenceLines, featureName, hotelWebsite, groupClaims, mapFact, mapHotelResult, mapQuestion, requestChips, roomNumber, sourceText, valueText } from './mappers';

const capabilities: Capabilities = {
  prices: false,
  booking: false,
  roomCategories: false,
  editClaims: false,
  guestNotifications: false,
  freeDestination: false,
};

/** Один запрос на сессию: реестр и health меняются только при перезапуске бэкенда. */
function once<T>(load: () => Promise<T>): () => Promise<T> {
  let promise: Promise<T> | null = null;
  return () => {
    promise ??= load().catch((error: unknown) => {
      promise = null;
      throw error;
    });
    return promise;
  };
}

const loadRegistry = once(() => get<FeatureRegistryDto>('/features'));
const loadHealth = once(() => get<HealthDto>('/health'));

/* Последние ответы поиска: карточка отеля переиспользует их, чтобы не гонять агента повторно. */
const SEARCH_TTL_MS = 60_000;
const searchCache = new Map<string, { at: number; promise: Promise<SearchOutcome> }>();

type SearchOutcome = SearchResponseDto & {
  /** Условия, без которых искали по просьбе гостя (только при skipUnclear). */
  skipped: string[];
};

/** Что мешает искать: непроверяемые условия или вопрос парсера. */
export function unclearItems(parsed: SearchResponseDto['parsed']): string[] {
  if (parsed.unknown_or_ambiguous.length) return parsed.unknown_or_ambiguous;
  return parsed.clarification_question ? [parsed.clarification_question] : [];
}

function choicesKey(choices: Record<string, string> | undefined): string {
  return Object.entries(choices ?? {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join(',');
}

async function runSearch(params: SearchParams, fresh = false): Promise<SearchOutcome> {
  const text = params.text.trim();
  const refine = choicesKey(params.choices);
  const key = `${text}|${params.skipUnclear ? 'relax' : ''}|${refine}`;
  const cached = searchCache.get(key);
  if (!fresh && cached && Date.now() - cached.at < SEARCH_TTL_MS) return cached.promise;
  const promise = (async (): Promise<SearchOutcome> => {
    const health = await loadHealth();
    // Демо-ответы отельера участвуют в подборе только в DEMO_MODE бэкенда и помечаются в источниках.
    const options = { include_simulated: health.demo_mode, ranking_method: 'balanced_v2' as const };
    if (!params.skipUnclear && !refine) {
      const body: SearchRequestDto = { text, ...options };
      return { ...(await post<SearchResponseDto>('/search', body)), skipped: [] };
    }
    // Уточнения и «искать без условия» не разбирают текст заново: берём уже полученный
    // разбор (из кэша, без повторного вызова LLM) и отправляем его как parsed.
    const first = await runSearch({ ...params, skipUnclear: false, choices: undefined });
    const relax = Boolean(params.skipUnclear) && first.status === 'needs_clarification' && first.parsed.region === 'Adler';
    if (first.status === 'needs_clarification' && !relax) return first;
    // Уточнять можно только понятия, которые есть в запросе (адрес мог устареть).
    const concepts = new Set((first.parsed.needs ?? []).filter((n) => n.kind === 'any_of').map((n) => n.concept));
    const choices = Object.fromEntries(Object.entries(params.choices ?? {}).filter(([concept]) => concepts.has(concept)));
    if (!relax && !Object.keys(choices).length) return first;
    const parsed = relax ? { ...first.parsed, unknown_or_ambiguous: [], clarification_question: null } : first.parsed;
    const body: SearchRequestDto = { parsed, ...options, ...(Object.keys(choices).length ? { choices } : {}) };
    const response = await post<SearchResponseDto>('/search', body);
    return { ...response, skipped: relax ? unclearItems(first.parsed) : [] };
  })();
  searchCache.set(key, { at: Date.now(), promise });
  if (searchCache.size > 8) searchCache.delete(searchCache.keys().next().value!);
  promise.catch(() => searchCache.delete(key));
  return promise;
}

/** Кнопки «Какой вид важнее?» над выдачей — по расплывчатым пожеланиям из запроса. */
export function refinementsOf(parsed: SearchResponseDto['parsed']): Refinement[] {
  return (parsed.needs ?? [])
    .filter((n) => n.kind === 'any_of' && n.concept && n.options.length > 1)
    .map((n) => ({
      concept: n.concept!,
      quote: n.quote,
      question: n.question ?? `Уточнить «${n.quote}»`,
      options: n.options.map((o) => ({ key: o.key, label: o.label })),
      chosen: n.chosen,
    }));
}

function mapAnswer(dto: AnswerDto): HotelierAnswer {
  return {
    id: dto.id,
    questionId: dto.question_id,
    text: dto.text,
    claims: groupClaims(dto.extraction.claims),
    unparsed: dto.extraction.unparsed,
    status: dto.status,
    createdAt: dto.created_at,
  };
}

async function hotelsById(): Promise<Map<string, HotelDto>> {
  const hotels = await get<HotelDto[]>('/hotels');
  return new Map(hotels.map((h) => [h.id, h]));
}

async function questionById(questionId: string) {
  const [questions, registry, hotels] = await Promise.all([get<QuestionDto[]>('/hotelier/questions'), loadRegistry(), hotelsById()]);
  const question = questions.find((q) => q.id === questionId);
  if (!question) throw new DataError('not_found', 'Вопрос не найден', 404);
  return mapQuestion(question, hotels.get(question.hotel_id)?.name ?? question.hotel_id, registry);
}

const getAnswerDto = (answerId: string) => get<AnswerDto>(`/hotelier/answers/${encodeURIComponent(answerId)}`);

/** Что увидит гость и с чем разошёлся ответ — собирается из сохранённых данных, переживает перезагрузку. */
async function buildPublishResult(answer: AnswerDto, review: ModelReviewDto[] | null): Promise<PublishResult> {
  const question = await questionById(answer.question_id);
  const claims = groupClaims(answer.extraction.claims);
  const positive = claims.filter((c) => c.value).map((c) => c.subject.replace(/^Номера?/, '').trim());
  let conflicts: PublishConflict[];
  if (review) {
    conflicts = review.map((item) => ({ subject: `Номер ${roomNumber(item.room_id) ?? item.room_id}`, reason: item.text }));
  } else {
    // После перезагрузки: review-конфликты, где одна из сторон — наблюдение из этого ответа.
    const open = await get<ConflictDto[]>(`/hotelier/conflicts?hotel_id=${encodeURIComponent(question.hotelId)}&status=open`);
    conflicts = open
      .filter((c) => c.policy.startsWith('review:') && [c.left_id, c.right_id].some((id) => id.startsWith(`${answer.id}:`)))
      .map((c) => ({ subject: `Номер ${roomNumber(c.subject_id) ?? c.subject_id}`, reason: 'Расходится с расчётом по зданию — проверит оператор.' }));
  }
  return {
    answerId: answer.id,
    questionId: question.id,
    featureLabel: question.featureLabel,
    featureShort: question.featureShort,
    claims,
    conflicts,
    publishedAt: answer.created_at,
    guestPreview: positive.length ? `${question.featureShort} — в номерах ${positive.join(', ')}` : `${question.featureShort} — нет в указанных номерах`,
    sourceLabel: 'ответ представителя отеля (демо-симулятор)',
    statusLabel: 'заявление отельера, без независимой проверки',
  };
}

/** Почему поиск просит уточнения: вопрос парсера, непонятые места или регион вне Адлера. */
export function clarificationText(parsed: SearchResponseDto['parsed']): string {
  if (parsed.clarification_question) return parsed.clarification_question;
  if (parsed.unknown_or_ambiguous.length) return `Уточните: ${parsed.unknown_or_ambiguous.join('; ')}`;
  if (parsed.region !== 'Adler') return 'Сейчас поддерживается только прибрежный Адлер.';
  return 'Уточните запрос.';
}

export function createApiSource(): DataSource {
  return {
    mode: 'api',
    capabilities,

    async getHealth() {
      const health = await loadHealth();
      if (health.status !== 'ok') {
        return { ok: false, label: 'База пуста', details: 'Выполните python -m scripts.seed_demo и перезапустите бэкенд.' };
      }
      return { ok: true, label: `API · ${health.hotels} отелей`, details: `Разбор запроса: ${health.parser_mode}` };
    },

    getDefaultSearch() {
      return {
        text: 'Ищу тихий отель в Адлере, не дальше 500 метров пешком от пляжа, хотелось бы вид на море',
        destination: 'Адлер',
        checkIn: '',
        checkOut: '',
        guests: 2,
      };
    },

    async getSuggestions() {
      const examples = await get<string[]>('/demo-queries');
      return {
        chips: [
          { label: 'Тихо ночью', phrase: 'тихий отель' },
          { label: 'До пляжа пешком', phrase: 'не дальше 500 метров пешком от пляжа' },
          { label: 'Вид на море', phrase: 'хотелось бы вид на море' },
          { label: 'Подальше от самолётов', phrase: 'подальше от самолётов' },
        ],
        examples,
      };
    },

    async search(params) {
      const [response, registry] = await Promise.all([runSearch(params, true), loadRegistry()]);
      const notes = ['Цены и бронирование не подключены к API.', 'Даты и число гостей пока не передаются в подбор.'];
      if (response.include_simulated) notes.push('Учитываются демо-ответы отельеров — они помечены в источниках.');
      const result: SearchResult = {
        status: response.status,
        clarification: response.status === 'needs_clarification' ? clarificationText(response.parsed) : null,
        contextLabel: `Адлер · ${formatGuests(params.guests)}`,
        chips: requestChips(response.parsed, registry),
        ignoredTerms: [...(response.parsed.unsupported ?? []), ...(response.parsed.ignored_terms ?? [])],
        hotels: [
          ...response.matched.map((h) => mapHotelResult(h, 'matched', response.parsed, registry)),
          ...response.needs_verification.map((h) => mapHotelResult(h, 'needs_verification', response.parsed, registry)),
          ...response.excluded.map((h) => mapHotelResult(h, 'excluded', response.parsed, registry)),
        ],
        notes,
        canSearchAnyway: response.status === 'needs_clarification' && response.parsed.region === 'Adler',
        skipped: response.skipped,
        refinements: response.status === 'ok' ? refinementsOf(response.parsed) : [],
      };
      return result;
    },

    async getHotel(hotelId, params) {
      const [detail, registry, evidence, health] = await Promise.all([
        get<HotelDetailDto>(`/hotels/${encodeURIComponent(hotelId)}`),
        loadRegistry(),
        get<HotelEvidenceDto>(`/hotels/${encodeURIComponent(hotelId)}/evidence`),
        loadHealth(),
      ]);
      let summary: HotelSummary | null = null;
      if (params?.text.trim()) {
        const response = await runSearch(params);
        const groups = [
          ['matched', response.matched],
          ['needs_verification', response.needs_verification],
          ['excluded', response.excluded],
        ] as const;
        for (const [group, items] of groups) {
          const found = items.find((i) => i.hotel.id === hotelId);
          if (found) summary = mapHotelResult(found, group, response.parsed, registry);
        }
      }
      const hotel = detail.hotel;
      summary ??= {
        id: hotel.id,
        name: hotel.name,
        area: 'Адлер',
        coords: { lat: hotel.lat, lon: hotel.lon },
        group: 'partial',
        price: null,
        roomHint: null,
        criteria: [],
        needRows: [],
        evidence: [],
        warnings: [],
        pendingQuestion: false,
        photo: hotelPhoto(hotel.id, hotel.name),
        sourceUrl: hotel.source_url,
        website: hotelWebsite(hotel.tags),
      };

      // Подтверждённые отельером номера — из наблюдений уровня room.
      const caveats: string[] = [];
      const roomClaims = new Map<string, { yes: string[]; no: string[] }>();
      // История не равна текущему знанию: устаревшие и конфликтующие утверждения
      // не показываем гостю как действующие характеристики номера.
      for (const o of health.demo_mode ? evidence.current_demo : evidence.current_real) {
        if (!o.subject_id.includes(':room:') || typeof o.value !== 'boolean') continue;
        const number = roomNumber(o.subject_id);
        if (!number) continue;
        const entry = roomClaims.get(o.feature_key) ?? { yes: [], no: [] };
        (o.value ? entry.yes : entry.no).push(number);
        roomClaims.set(o.feature_key, entry);
      }
      for (const [key, { yes, no }] of roomClaims) {
        const name = featureName(key, registry);
        if (yes.length) caveats.push(`${name}: по словам отельера (демо) — в номерах ${compactNumbers(yes)}.`);
        if (no.length) caveats.push(`${name}: нет в номерах ${compactNumbers(no)}.`);
      }
      for (const c of summary.criteria) {
        if (c.state === 'unknown') {
          caveats.push(
            c.askable
              ? `${c.name}: отельер пока не ответил. Вопрос ${summary.pendingQuestion ? 'уже отправлен' : 'можно отправить из выдачи'}.`
              : `${c.name}: нет данных в открытых источниках.`,
          );
        }
      }
      caveats.push(...summary.warnings);

      const basis =
        summary.evidence.length > 0
          ? summary.evidence
          : evidenceLines(
              detail.observations
                .filter((o) => o.subject_type === 'hotel' && o.value !== null)
                .slice(0, 6)
                .map((o) => ({
                  feature_key: o.feature_key,
                  requested: '',
                  actual: o.value,
                  outcome: 'preference' as const,
                  status: o.status,
                  subject_id: o.subject_id,
                  match: null,
                  explanation: `${registry[o.feature_key]?.label ?? o.feature_key}: ${valueText(o.feature_key, o.value, registry[o.feature_key])}. ${o.confidence_method}`,
                  evidence: [o],
                  model_conflicts: [],
                })),
              registry,
            );

      const room = summary.roomHint
        ? {
            title: summary.roomHint,
            subtitle: '',
            guests: `Для ${formatGuests(params?.guests ?? 2)}`,
            price: null,
            nights: null,
            total: null,
          }
        : null;
      const result: HotelDetail = {
        hotel: summary,
        room,
        roomPhoto: roomPhoto(hotel.id, room?.title ?? hotel.name),
        roomUnavailableReason: room
          ? null
          : 'API пока не возвращает категории номеров. Показываем характеристики отеля и номеров, о которых ответил отельер.',
        basis,
        caveats,
      };
      return result;
    },

    async requestCheck(hotelId, featureKeys): Promise<CheckRequestResult> {
      const created = await Promise.all(
        featureKeys.map((key) => post<QuestionDto>('/hotelier/questions', { hotel_id: hotelId, feature_key: key })),
      );
      return {
        questionIds: created.map((q) => q.id),
        message: 'Вопрос отправлен отельеру. Уведомления гостям пока не подключены — проверьте выдачу позже.',
        cabinetPath: `/hotelier/${encodeURIComponent(hotelId)}/questions`,
      };
    },

    async listHotelierHotels() {
      const [hotels, open] = await Promise.all([get<HotelDto[]>('/hotels'), get<QuestionDto[]>('/hotelier/questions?status=open')]);
      const counts = new Map<string, number>();
      for (const q of open) counts.set(q.hotel_id, (counts.get(q.hotel_id) ?? 0) + 1);
      return hotels
        .map((h) => ({ id: h.id, name: h.name, openQuestions: counts.get(h.id) ?? 0 }))
        .sort((a, b) => b.openQuestions - a.openQuestions || a.name.localeCompare(b.name, 'ru'));
    },

    async listQuestions(hotelId) {
      const [questions, registry, hotels] = await Promise.all([
        get<QuestionDto[]>(`/hotelier/questions?hotel_id=${encodeURIComponent(hotelId)}`),
        loadRegistry(),
        hotelsById(),
      ]);
      const name = hotels.get(hotelId)?.name ?? hotelId;
      return questions
        .map((q) => mapQuestion(q, name, registry))
        .sort((a, b) => (a.status === b.status ? b.createdAt.localeCompare(a.createdAt) : a.status === 'open' ? -1 : 1));
    },

    getQuestion: questionById,

    async submitAnswer(questionId, text) {
      return mapAnswer(await post<AnswerDto>(`/hotelier/questions/${encodeURIComponent(questionId)}/answer`, { text }));
    },

    async getAnswer(answerId) {
      return mapAnswer(await getAnswerDto(answerId));
    },

    async rejectAnswer(answerId) {
      await post<ConfirmResponseDto>(`/hotelier/answers/${encodeURIComponent(answerId)}/confirm`, { accept: false });
    },

    async publishAnswer(answerId, overrides) {
      if (Object.keys(overrides).length > 0) {
        throw new DataError('unsupported', 'API не принимает правки отдельных строк. Измените текст ответа и отправьте его заново.');
      }
      const response = await post<ConfirmResponseDto>(`/hotelier/answers/${encodeURIComponent(answerId)}/confirm`, { accept: true });
      searchCache.clear();
      return buildPublishResult(await getAnswerDto(answerId), response.idempotent ? null : response.model_review);
    },

    async getPublishResult(answerId) {
      const answer = await getAnswerDto(answerId);
      if (answer.status !== 'confirmed') throw new DataError('not_found', 'Ответ ещё не опубликован', 404);
      return buildPublishResult(answer, null);
    },

    async getFacts(hotelId) {
      const [response, registry] = await Promise.all([
        get<FactsResponseDto>(`/hotelier/hotels/${encodeURIComponent(hotelId)}/facts`),
        loadRegistry(),
      ]);
      return { facts: response.facts.map((f) => mapFact(f, registry)), conflicts: response.conflicts.filter((c) => c.status === 'open').length };
    },

    async getRooms(hotelId) {
      const [evidence, registry] = await Promise.all([
        get<HotelEvidenceDto>(`/hotels/${encodeURIComponent(hotelId)}/evidence`),
        loadRegistry(),
      ]);
      const rooms = new Map<string, HotelierRoom>();
      // Кабинет — демо-мир: текущее значение с учётом симулированных ответов, TTL и решений по конфликтам.
      for (const state of evidence.current_demo) {
        if (!state.subject_id.includes(':room:')) continue;
        const o = [...state.observations].sort((a, b) => b.collected_at.localeCompare(a.collected_at))[0];
        if (!o) continue;
        const number = roomNumber(o.subject_id) ?? o.subject_id;
        const room = rooms.get(o.subject_id) ?? { id: o.subject_id, title: `Номер ${number}`, note: null, facts: [] };
        const floor = o.evidence.details.floor;
        if (typeof floor === 'number') room.note = `${floor}-й этаж`;
        room.facts.push({
          label: featureName(o.feature_key, registry),
          value:
            state.value === null
              ? state.status === 'conflicted'
                ? 'Конфликт — нужна проверка'
                : 'Нет актуальных данных'
              : valueText(o.feature_key, state.value, registry[o.feature_key]),
          source: `${sourceText(o.evidence.source)} · ${formatDay(o.collected_at)}`,
        });
        rooms.set(o.subject_id, room);
      }
      return [...rooms.values()].sort((a, b) => a.title.localeCompare(b.title, 'ru', { numeric: true }));
    },
  };
}
