import { formatDateRange, formatGuests, nightsBetween, walkMinutes, formatMeters } from '../../lib/format';
import { DataError } from '../errors';
import type {
  Capabilities,
  Criterion,
  DataSource,
  EvidenceLine,
  HotelDetail,
  HotelSummary,
  HotelierAnswer,
  HotelierQuestion,
  Money,
  PublishResult,
  RequestChip,
  ResultGroup,
  SearchParams,
} from '../types';
import { DEMO_DESTINATION, DEMO_EXAMPLES, DEMO_QUERY, FEATURE_COPY, type MockAnswer, type MockHotel, type MockState } from './fixtures';
import { parseBlackoutAnswer } from './parseAnswer';
import { hotelPhoto, roomPhoto } from '../photos';
import { latency, maybeFail, readState, resetState, writeState } from './store';

const capabilities: Capabilities = {
  prices: true,
  booking: false,
  roomCategories: true,
  editClaims: true,
  guestNotifications: true,
  freeDestination: true,
};

const money = (amount: number): Money => ({ amount, currency: 'RUB', demo: true });

interface Wishes {
  blackout: boolean;
  shop: boolean;
  beach: boolean;
  beachLimitMinutes: number | null;
  quiet: boolean;
  ignored: string[];
}

const UNSUPPORTED: [RegExp, string][] = [
  [/бассейн/u, 'бассейн'],
  [/завтрак/u, 'завтрак'],
  [/парковк/u, 'парковка'],
  [/спа(?!\p{L})/u, 'спа'],
  [/живот|собак|кошк/u, 'с животными'],
  [/трансфер/u, 'трансфер'],
];

/** Демо-разбор пожеланий: ключевые слова, без попытки «понять всё». */
export function parseWishes(text: string): Wishes {
  const t = text.toLowerCase().replace(/ё/g, 'е');
  const limit = /(?:до|не\s+больше|не\s+более|максимум)?\s*(\d{1,2})\s*мин/u.exec(t);
  return {
    blackout: /blackout|блэкаут|блекаут|затемн|штор/u.test(t),
    shop: /магазин|24\/7|круглосуточ|ночью/u.test(t),
    beach: /мор[еяю]|пляж/u.test(t),
    beachLimitMinutes: limit ? Number(limit[1]) : null,
    quiet: /тих|тишин|шум|высп/u.test(t),
    ignored: UNSUPPORTED.filter(([re]) => re.test(t)).map(([, label]) => label),
  };
}

function chipsFor(w: Wishes): RequestChip[] {
  const chips: RequestChip[] = [];
  if (w.blackout) chips.push({ label: 'Blackout · обязательно', kind: 'required' });
  if (w.shop) chips.push({ label: 'Магазин открыт ночью', kind: 'preference' });
  if (w.beach) {
    chips.push(
      w.beachLimitMinutes
        ? { label: `До моря ≤ ${w.beachLimitMinutes} мин · обязательно`, kind: 'required' }
        : { label: 'До моря пешком · время не задано', kind: 'preference' },
    );
  }
  if (w.quiet) chips.push({ label: 'Низкий уровень шума', kind: 'preference' });
  for (const term of w.ignored) chips.push({ label: `Не распознано: ${term}`, kind: 'unsupported' });
  return chips;
}

const ROOM_TITLES: Record<string, string> = {
  Улучшенный: 'Улучшенный номер',
  Стандартный: 'Стандартный номер',
  Делюкс: 'Номер делюкс',
  Люкс: 'Люкс',
  Семейный: 'Семейный номер',
  Эконом: 'Номер эконом',
};
const roomTitle = (category: string) => ROOM_TITLES[category] ?? category;

function categoryPhrase(category: string): string {
  const map: Record<string, string> = {
    Улучшенный: 'в улучшенном номере',
    Стандартный: 'в стандартном номере',
    Делюкс: 'в номере делюкс',
    Люкс: 'в люксе',
    Семейный: 'в семейном номере',
    Эконом: 'в номере эконом',
  };
  return map[category] ?? `в категории «${category}»`;
}

function blackoutCriterion(hotel: MockHotel): Criterion {
  const base = { key: 'blackout_curtains', name: 'Blackout', required: true, askable: true };
  if (hotel.blackout.status === 'unknown') {
    return { ...base, text: 'Blackout — нет данных', state: 'unknown', source: 'Отельер ещё не ответил' };
  }
  const positive = hotel.blackout.claims.filter((c) => c.value);
  if (positive.length === 0) {
    return { ...base, text: 'Blackout — нет ни в одной категории', state: 'violated', source: 'Ответ отельера. Независимо не проверено' };
  }
  return {
    ...base,
    text: `Blackout — ${positive.map((c) => categoryPhrase(c.category)).join(', ')}`,
    state: 'met',
    source: 'Ответ отельера. Независимо не проверено',
  };
}

function criteriaFor(hotel: MockHotel, w: Wishes): Criterion[] {
  const list: Criterion[] = [];
  if (w.blackout) list.push(blackoutCriterion(hotel));
  if (w.beach) {
    const minutes = walkMinutes(hotel.beachMeters);
    const limit = w.beachLimitMinutes;
    list.push({
      key: 'beach',
      name: 'До пляжа',
      text: `До пляжа — ${minutes} мин пешком`,
      state: limit ? (minutes <= limit ? 'met' : 'violated') : minutes <= 15 ? 'met' : 'weak',
      required: limit !== null,
      askable: false,
      source: `OpenStreetMap, ${formatMeters(hotel.beachMeters)} по пешему маршруту (демо)`,
    });
  }
  if (w.shop) {
    list.push(
      hotel.shopMinutes === null
        ? {
            key: 'shop',
            name: 'Магазин 24/7',
            text: 'Магазин 24/7 — нет данных',
            state: 'unknown',
            required: false,
            askable: false,
            source: 'В OpenStreetMap нет часов работы рядом',
          }
        : {
            key: 'shop',
            name: 'Магазин 24/7',
            text: `Магазин 24/7 — ${hotel.shopMinutes} мин пешком`,
            state: hotel.shopMinutes <= 10 ? 'met' : 'weak',
            required: false,
            askable: false,
            source: 'В OpenStreetMap указан режим 24/7 (демо)',
          },
    );
  }
  if (w.quiet) {
    const label = { high: 'высокий потенциал', medium: 'средний потенциал', low: 'низкий потенциал' }[hotel.quiet];
    list.push({
      key: 'quiet',
      name: 'Тишина снаружи',
      text: `Тишина снаружи — ${label}`,
      state: hotel.quiet === 'high' ? 'met' : 'weak',
      required: false,
      askable: false,
      source: 'Расчёт по дорогам и барам OSM (демо). Не дБ',
    });
  }
  return list;
}

function evidenceFor(hotel: MockHotel, w: Wishes): EvidenceLine[] {
  const lines: EvidenceLine[] = [];
  if (w.blackout) {
    lines.push(
      hotel.blackout.status === 'answered'
        ? { title: 'Затемнение', text: `«${hotel.blackout.quote}».`, note: 'Ответ отельера. Независимо не проверено.' }
        : { title: 'Затемнение', text: 'Отельер ещё не ответил. Значение не угадываем.', note: 'Вопрос отправлен агентом проверки данных.' },
    );
  }
  if (w.beach) {
    lines.push({ title: 'Путь до пляжа', text: `OpenStreetMap, ${formatMeters(hotel.beachMeters)} по пешему маршруту.` });
  }
  if (w.shop) {
    lines.push(
      hotel.shopMinutes === null
        ? { title: 'Магазин', text: 'В OpenStreetMap рядом нет заведений с указанными часами работы.' }
        : { title: 'Магазин', text: 'В OpenStreetMap указан режим 24/7.', note: 'Фактическая работа не гарантирована.' },
    );
  }
  if (w.quiet) {
    lines.push({ title: 'Тишина', text: 'Эвристика по дорогам, железной дороге и барам рядом.', note: 'Не измерение шума в номере.' });
  }
  return lines;
}

function groupFor(criteria: Criterion[]): ResultGroup {
  if (criteria.some((c) => c.required && c.state === 'violated')) return 'excluded';
  if (criteria.some((c) => c.state === 'unknown')) return 'partial';
  return 'confirmed';
}

function summarize(hotel: MockHotel, w: Wishes, state: MockState): HotelSummary {
  const criteria = criteriaFor(hotel, w);
  const positive = hotel.blackout.status === 'answered' ? hotel.blackout.claims.find((c) => c.value) : undefined;
  return {
    id: hotel.id,
    name: hotel.name,
    area: hotel.area,
    coords: hotel.coords,
    group: groupFor(criteria),
    price: money(hotel.pricePerNight),
    roomHint: w.blackout && positive ? roomTitle(positive.category) : null,
    criteria,
    needRows: [],
    evidence: evidenceFor(hotel, w),
    warnings: [],
    pendingQuestion: state.questions.some((q) => q.hotelId === hotel.id && q.status === 'open'),
    photo: hotelPhoto(hotel.photoIndex, hotel.name),
  };
}

function hotelById(state: MockState, id: string): MockHotel {
  const hotel = state.hotels.find((h) => h.id === id);
  if (!hotel) throw new DataError('not_found', 'Отель не найден в демо-данных', 404);
  return hotel;
}

function contextLabel(params: SearchParams): string {
  const dates = formatDateRange(params.checkIn, params.checkOut);
  return [params.destination || DEMO_DESTINATION, dates, formatGuests(params.guests)].filter(Boolean).join(' · ');
}

function questionView(state: MockState, id: string): HotelierQuestion {
  const q = state.questions.find((item) => item.id === id);
  if (!q) throw new DataError('not_found', 'Вопрос не найден', 404);
  const hotel = hotelById(state, q.hotelId);
  return {
    id: q.id,
    hotelId: q.hotelId,
    hotelName: hotel.name,
    featureKey: q.featureKey,
    featureLabel: FEATURE_COPY.label,
    featureShort: FEATURE_COPY.short,
    title: FEATURE_COPY.title,
    prompt: FEATURE_COPY.prompt,
    ask: FEATURE_COPY.ask,
    why: FEATURE_COPY.why,
    requestedBy: 'из поиска гостей',
    status: q.status,
    createdAt: q.createdAt,
    answerHint: FEATURE_COPY.hint,
    answerPlaceholder: FEATURE_COPY.placeholder,
    pendingAnswerId: null,
    statusNote: null,
  };
}

function answerView(a: MockAnswer): HotelierAnswer {
  return {
    id: a.id,
    questionId: a.questionId,
    text: a.text,
    claims: a.claims.map((c) => ({ id: c.id, subject: c.category, subjectNote: c.note, value: c.value, detail: c.detail, quote: c.quote })),
    unparsed: a.unparsed,
    status: a.status,
    createdAt: a.createdAt,
  };
}

function answerById(state: MockState, id: string): MockAnswer {
  const answer = state.answers.find((a) => a.id === id);
  if (!answer) throw new DataError('not_found', 'Ответ не найден. Возможно, демо было сброшено.', 404);
  return answer;
}

function guestPreview(claims: { category: string; note: string | null; value: boolean }[]): string {
  const positive = claims.filter((c) => c.value);
  if (positive.length === 0) return 'Blackout — нет в номерах этого отеля';
  const phrases = positive.map((c) => {
    const plural: Record<string, string> = {
      Улучшенный: 'улучшенных номерах',
      Стандартный: 'стандартных номерах',
      Делюкс: 'номерах делюкс',
      Люкс: 'люксах',
      Семейный: 'семейных номерах',
      Эконом: 'номерах эконом',
    };
    const note = c.note ? ` с ${c.note.toLowerCase().replace(/^окна/, 'окнами')}` : '';
    return `${plural[c.category] ?? c.category}${note}`;
  });
  return `Blackout — в ${phrases.join(' и ')}`;
}

function publishView(a: MockAnswer): PublishResult {
  return {
    answerId: a.id,
    questionId: a.questionId,
    featureLabel: FEATURE_COPY.label,
    featureShort: FEATURE_COPY.short,
    claims: answerView(a).claims,
    conflicts: [],
    publishedAt: a.publishedAt ?? a.createdAt,
    guestPreview: guestPreview(a.claims),
    sourceLabel: 'представитель отеля',
    statusLabel: 'заявление отельера',
  };
}

let answerCounter = 0;

export function createMockSource(): DataSource & { resetDemo(): Promise<void> } {
  return {
    mode: 'mock',
    capabilities,

    async getHealth() {
      return { ok: true, label: 'Демо-данные', details: 'Без бэкенда: отели, цены и ответы отельеров — демонстрационные.' };
    },

    getDefaultSearch() {
      return { text: DEMO_QUERY, destination: DEMO_DESTINATION, checkIn: '2027-06-12', checkOut: '2027-06-16', guests: 2 };
    },

    async getSuggestions() {
      await latency(150);
      return {
        chips: [
          { label: 'Затемнение номера', phrase: 'нужны шторы blackout' },
          { label: 'Низкий уровень шума', phrase: 'тихо ночью' },
          { label: 'Море пешком', phrase: 'море пешком' },
        ],
        examples: DEMO_EXAMPLES,
      };
    },

    async search(params) {
      await latency(650);
      maybeFail('search');
      const state = readState();
      const w = parseWishes(params.text);
      const destination = params.destination.trim().toLowerCase();
      const known = !destination || destination.includes('батуми') || destination.includes('batumi');
      const notes = known ? [] : [`В демо-данных есть только ${DEMO_DESTINATION}. Попробуйте это направление.`];
      return {
        status: 'ok',
        clarification: null,
        contextLabel: contextLabel(params),
        chips: chipsFor(w),
        ignoredTerms: w.ignored,
        unsupported: [],
        modelUnavailable: false,
        hotels: known ? state.hotels.map((h) => summarize(h, w, state)) : [],
        notes,
        // Демо-разбор не блокирует поиск: непонятое уходит в «Не учтено».
        canSearchAnyway: false,
        skipped: [],
        refinements: [],
      };
    },

    async getHotel(hotelId, params) {
      await latency(400);
      maybeFail('hotel');
      const state = readState();
      const hotel = hotelById(state, hotelId);
      const w = parseWishes(params?.text ?? DEMO_QUERY);
      const summary = summarize(hotel, w, state);
      const nights = params ? nightsBetween(params.checkIn, params.checkOut) : null;
      const answered = hotel.blackout.status === 'answered' ? hotel.blackout : null;
      const positive = answered?.claims.find((c) => c.value);
      const category = positive ? roomTitle(positive.category) : hotel.room.category;
      const note = positive?.note?.toLowerCase() ?? hotel.room.note;
      const caveats: string[] = [];
      if (w.blackout) {
        if (!answered) caveats.push('Blackout ещё не подтверждён отельером. Вопрос отправлен — ответ появится в выдаче.');
        for (const c of answered?.claims ?? []) {
          if (!c.value) caveats.push(`В номерах категории «${c.category.toLowerCase()}» blackout не подтверждён.`);
        }
      }
      const criteria = summary.criteria.map((c) =>
        c.key === 'blackout_curtains' && c.state === 'met' ? { ...c, text: 'Шторы blackout — подтверждено отельером' } : c,
      );
      const detail: HotelDetail = {
        hotel: { ...summary, criteria },
        room: {
          title: category,
          subtitle: note,
          guests: `Для ${formatGuests(params?.guests ?? 2)}`,
          price: money(hotel.pricePerNight),
          nights,
          total: nights ? money(hotel.pricePerNight * nights) : null,
        },
        roomPhoto: roomPhoto(hotel.photoIndex, category),
        roomUnavailableReason: null,
        basis: summary.evidence,
        caveats,
      };
      return detail;
    },

    async requestCheck(hotelId) {
      await latency(350);
      const state = writeState((draft) => {
        if (!draft.notify.includes(hotelId)) draft.notify.push(hotelId);
        const open = draft.questions.find((q) => q.hotelId === hotelId && q.status === 'open');
        if (!open) {
          draft.questions.push({
            id: `q-${hotelId}-${Date.now()}`,
            hotelId,
            featureKey: 'blackout_curtains',
            status: 'open',
            createdAt: new Date().toISOString(),
          });
        }
      });
      const question = state.questions.find((q) => q.hotelId === hotelId && q.status === 'open')!;
      return {
        questionIds: [question.id],
        message: 'Вопрос отправлен отельеру. Сообщим, когда он ответит — пока можно продолжить поиск.',
        cabinetPath: `/hotelier/${encodeURIComponent(hotelId)}/questions/${encodeURIComponent(question.id)}`,
      };
    },

    async listHotelierHotels() {
      await latency(250);
      maybeFail('cabinet');
      const state = readState();
      return state.hotels
        .map((h) => ({ id: h.id, name: h.name, openQuestions: state.questions.filter((q) => q.hotelId === h.id && q.status === 'open').length }))
        .sort((a, b) => b.openQuestions - a.openQuestions);
    },

    async listQuestions(hotelId) {
      await latency(350);
      maybeFail('cabinet');
      const state = readState();
      hotelById(state, hotelId);
      return state.questions
        .filter((q) => q.hotelId === hotelId)
        .map((q) => questionView(state, q.id))
        .sort((a, b) => (a.status === b.status ? 0 : a.status === 'open' ? -1 : 1));
    },

    async getQuestion(questionId) {
      await latency(250);
      maybeFail('cabinet');
      return questionView(readState(), questionId);
    },

    async submitAnswer(questionId, text) {
      await latency(700);
      maybeFail('cabinet');
      const trimmed = text.trim();
      if (!trimmed) throw new DataError('invalid', 'Напишите ответ — хотя бы одно предложение.');
      questionView(readState(), questionId);
      const parsed = parseBlackoutAnswer(trimmed);
      answerCounter += 1;
      const answer: MockAnswer = {
        id: `a-${Date.now().toString(36)}-${answerCounter}`,
        questionId,
        text: trimmed,
        claims: parsed.claims.map((c, i) => ({ ...c, id: `c${i}` })),
        unparsed: parsed.unparsed,
        status: 'pending',
        createdAt: new Date().toISOString(),
      };
      writeState((draft) => {
        draft.answers.push(answer);
      });
      return answerView(answer);
    },

    async getAnswer(answerId) {
      await latency(200);
      return answerView(answerById(readState(), answerId));
    },

    async rejectAnswer(answerId) {
      await latency(250);
      writeState((draft) => {
        const answer = answerById(draft, answerId);
        if (answer.status === 'pending') answer.status = 'rejected';
      });
    },

    async publishAnswer(answerId, overrides) {
      await latency(700);
      maybeFail('publish');
      const current = answerById(readState(), answerId);
      if (current.status === 'confirmed') return publishView(current);
      if (current.status !== 'pending') throw new DataError('invalid', 'Этот ответ уже отклонён. Отправьте новый ответ.');
      if (current.claims.length === 0 || current.unparsed.length > 0) {
        throw new DataError('invalid', 'Ответ разобран не полностью. Измените формулировку и проверьте снова.');
      }
      const state = writeState((draft) => {
        const answer = answerById(draft, answerId);
        answer.claims = answer.claims.map((c) => {
          const value = overrides[c.id];
          if (value === undefined || value === c.value) return c;
          // Отельер поправил разбор: исходное уточнение к новому значению уже не относится.
          return { ...c, value, detail: value ? 'Шторы blackout (исправлено при проверке)' : 'Без штор blackout (исправлено при проверке)' };
        });
        answer.status = 'confirmed';
        answer.publishedAt = new Date().toISOString();
        const question = draft.questions.find((q) => q.id === answer.questionId)!;
        question.status = 'answered';
        const hotel = hotelById(draft, question.hotelId);
        hotel.blackout = {
          status: 'answered',
          quote: answer.text,
          answeredAt: answer.publishedAt,
          claims: answer.claims.map(({ category, note, value, detail }) => ({ category, note, value, detail })),
        };
        draft.notify = draft.notify.filter((id) => id !== hotel.id);
      });
      return publishView(answerById(state, answerId));
    },

    async getPublishResult(answerId) {
      await latency(200);
      const state = readState();
      const answer = answerById(state, answerId);
      if (answer.status !== 'confirmed') throw new DataError('not_found', 'Ответ ещё не опубликован', 404);
      return publishView(answer);
    },

    async getFacts(hotelId) {
      await latency(350);
      maybeFail('cabinet');
      const hotel = hotelById(readState(), hotelId);
      const blackout = hotel.blackout;
      const positive = blackout.status === 'answered' ? blackout.claims.filter((c) => c.value) : [];
      return {
        conflicts: 0,
        facts: [
          {
            key: 'blackout_curtains',
            label: FEATURE_COPY.label,
            value:
              blackout.status === 'unknown'
                ? 'Нет данных'
                : positive.length
                  ? `Есть: ${positive.map((c) => c.category.toLowerCase()).join(', ')}`
                  : 'Нет',
            status: blackout.status === 'unknown' ? 'unknown' : 'hotelier',
            confidence: blackout.status === 'unknown' ? 'unknown' : 'low',
            explanation: 'Заявление отельера о категориях номеров. Независимо не проверено.',
            source: blackout.status === 'unknown' ? 'Ждёт ответа отельера' : 'Представитель отеля (демо)',
            reviewedByHotelier: blackout.status === 'answered',
          },
          {
            key: 'beach',
            label: 'Путь до пляжа',
            value: `${formatMeters(hotel.beachMeters)} · ${walkMinutes(hotel.beachMeters)} мин пешком`,
            status: 'estimated',
            confidence: 'low',
            explanation: 'Пеший маршрут по OpenStreetMap. Входы на пляж не проверены на месте.',
            source: 'Расчёт по открытым данным (демо)',
            reviewedByHotelier: false,
          },
          {
            key: 'shop',
            label: 'Магазин 24/7 рядом',
            value: hotel.shopMinutes === null ? 'Нет данных' : `${hotel.shopMinutes} мин пешком`,
            status: hotel.shopMinutes === null ? 'unknown' : 'estimated',
            confidence: hotel.shopMinutes === null ? 'unknown' : 'low',
            explanation: 'Часы работы из OpenStreetMap. Фактическая работа не гарантирована.',
            source: 'Расчёт по открытым данным (демо)',
            reviewedByHotelier: false,
          },
          {
            key: 'quiet',
            label: 'Потенциал тишины снаружи',
            value: { high: 'Высокий', medium: 'Средний', low: 'Низкий' }[hotel.quiet],
            status: 'estimated',
            confidence: 'low',
            explanation: 'Эвристика по дорогам и барам рядом. Не дБ и не тишина в номере.',
            source: 'Расчёт по открытым данным (демо)',
            reviewedByHotelier: false,
          },
        ],
      };
    },

    async getRooms(hotelId) {
      await latency(300);
      maybeFail('cabinet');
      const hotel = hotelById(readState(), hotelId);
      const claims = hotel.blackout.status === 'answered' ? hotel.blackout.claims : [];
      return hotel.categories.map((category) => {
        const claim = claims.find((c) => c.category === category.name);
        return {
          id: category.name,
          title: category.name,
          note: category.note,
          facts: [
            {
              label: 'Шторы blackout',
              value: claim ? (claim.value ? `Есть · ${claim.detail.toLowerCase()}` : `Нет · ${claim.detail.toLowerCase()}`) : 'Нет данных',
              source: claim ? 'Заявление отельера (демо)' : 'Ждёт ответа',
            },
          ],
        };
      });
    },

    async resetDemo() {
      resetState();
    },
  };
}
