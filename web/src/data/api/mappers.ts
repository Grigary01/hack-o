import { capitalize, compactNumbers, formatDay, formatMeters, plural, walkMinutes } from '../../lib/format';
import { hotelPhoto } from '../photos';
import type {
  Criterion,
  CriterionState,
  EvidenceLine,
  HotelFact,
  HotelSummary,
  HotelierQuestion,
  ParsedClaim,
  RequestChip,
  ResultGroup,
} from '../types';
import type {
  CriterionDto,
  FactDto,
  FeatureDefinitionDto,
  FeatureRegistryDto,
  HardConstraintDto,
  HotelSearchResultDto,
  ObservationDto,
  ParsedQueryDto,
  QuestionDto,
  RoomClaimDto,
  SourceDto,
  Value,
} from './contract';

interface FeatureCopy {
  /** Короткое имя для карточек и чипов. */
  name: string;
  /** Для характеристик отельера: как задать вопрос в кабинете. */
  question?: { title: string; why: string; example: string };
}

/**
 * Тексты интерфейса для ключей из app/features/registry.yaml.
 * Новый ключ без записи здесь всё равно отобразится — по label из /api/features.
 */
const FEATURE_COPY: Record<string, FeatureCopy> = {
  walking_distance_to_beach_m: { name: 'До пляжа' },
  quietness_proxy: { name: 'Тишина снаружи' },
  nightlife_distance_m: { name: 'До баров и клубов' },
  sea_view: {
    name: 'Вид на море',
    question: {
      title: 'Есть ли в номерах вид на море?',
      why: 'Гости ищут номер с видом на море. Расчёт по зданию знает, с какой стороны и с какого этажа видно море, но не знает, где окна конкретных номеров.',
      example: 'В номерах 301–305 есть вид на море. В номере 101 нет вида на море.',
    },
  },
  soundproofing: {
    name: 'Шумоизоляция',
    question: {
      title: 'Есть ли в номерах шумоизоляция?',
      why: 'Гости ищут тихий номер. Шумоизоляцию нельзя рассчитать по карте — о ней знает только отель.',
      example: 'В номерах 201–204 есть шумоизоляция. В номере 101 нет шумоизоляции.',
    },
  },
  sunset_view: {
    name: 'Вид на закат',
    question: {
      title: 'Виден ли закат из номеров?',
      why: 'Гости хотят видеть закат из окна. Расчёт по рельефу знает сезоны, но не окна конкретных номеров.',
      example: 'В номерах 401–405 есть вид на закат. В номере 102 нет вида на закат.',
    },
  },
  blackout_curtains: {
    name: 'Шторы blackout',
    question: {
      title: 'Есть ли в номерах шторы blackout?',
      why: 'Гости ищут номер с затемнением. Пока это условие не подтверждено — его нельзя рассчитать по карте.',
      example: 'В номерах 301–305 есть шторы blackout. В номере 101 нет штор blackout.',
    },
  },
  sea_view_potential: { name: 'Море из окон здания (расчёт)' },
  sea_view_min_floor: { name: 'Море видно с этажа' },
  sunset_view_potential: { name: 'Закат из окон здания (расчёт)' },
  sunset_view_min_floor: { name: 'Закат виден с этажа' },
  aircraft_noise_exposure: { name: 'Авиашум' },
  aircraft_path_distance_m: { name: 'До траектории самолётов' },
  beach_route_climb_m: { name: 'Подъёмы по пути к пляжу' },
  beach_route_busy_crossings: { name: 'Переходы через трассы' },
  night_open_places_500m: { name: 'Открыто ночью рядом' },
  nearest_night_pharmacy_m: { name: 'Ночная аптека' },
  mountain_view_potential: { name: 'Вид на горы' },
  mountain_view_min_floor: { name: 'Горы видны с этажа' },
  quiet_side_potential: { name: 'Тихая сторона здания' },
};

const OPERATORS: Record<HardConstraintDto['operator'], string> = {
  '<': '<',
  '<=': '≤',
  '=': '=',
  '>=': '≥',
  '>': '>',
  '!=': '≠',
};

export function featureName(key: string, registry: FeatureRegistryDto): string {
  return FEATURE_COPY[key]?.name ?? registry[key]?.label ?? key;
}

export function roomNumber(subjectId: string | null): string | null {
  if (!subjectId || !subjectId.includes(':room:')) return null;
  return subjectId.split(':room:')[1] ?? null;
}

/** Значение характеристики человеческим языком, без ложной точности. */
export function valueText(key: string, value: Value | null, definition: FeatureDefinitionDto | undefined): string {
  if (value === null || value === undefined) return 'нет данных';
  if (typeof value === 'boolean') return value ? 'есть' : 'нет';
  if (typeof value === 'number') {
    const unit = definition?.unit;
    if (key === 'walking_distance_to_beach_m') return `${walkMinutes(value)} мин пешком · ${formatMeters(value)}`;
    if (unit === 'm') return `≈ ${formatMeters(value)}`;
    if (unit === 'floor') return `с ${value}-го этажа`;
    if (key === 'beach_route_busy_crossings') {
      return value === 0 ? 'без переходов' : `${value} ${plural(value, ['переход', 'перехода', 'переходов'])}`;
    }
    if (key === 'night_open_places_500m') {
      return value === 0 ? 'не найдено в OSM' : `${value} ${plural(value, ['место', 'места', 'мест'])} в 500 м`;
    }
    return String(value);
  }
  return definition?.choice_labels?.[value] ?? value;
}

export function sourceText(source: SourceDto | undefined): string {
  switch (source?.type) {
    case 'openstreetmap':
      return 'OpenStreetMap, расчёт по карте';
    case 'geo_model':
      return `Расчёт: ${source.name}`;
    case 'hotelier':
      return 'Ответ отельера. Независимо не проверено';
    case 'hotelier_simulated':
      return 'Ответ отельера (демо-симулятор). Независимо не проверено';
    case 'operator_decision':
      return 'Решение оператора по расхождению источников';
    default:
      return 'Источник не указан';
  }
}

const CONFIDENCE: Record<ObservationDto['confidence_level'], string> = {
  high: 'высокая',
  medium: 'средняя',
  low: 'низкая',
  unknown: 'неизвестна',
};

function criterionState(c: CriterionDto): CriterionState {
  if (c.outcome === 'matched') return 'met';
  if (c.outcome === 'violated') return 'violated';
  if (c.outcome === 'unknown' || c.actual === null) return 'unknown';
  return (c.match ?? 0) >= 0.75 ? 'met' : 'weak';
}

export function mapCriterion(c: CriterionDto, registry: FeatureRegistryDto, requiredKeys: Set<string>): Criterion {
  const definition = registry[c.feature_key];
  const name = featureName(c.feature_key, registry);
  const room = roomNumber(c.subject_id);
  let value = valueText(c.feature_key, c.actual, definition);
  if (typeof c.actual === 'boolean' && room) value = `${value} в номере ${room}`;
  const evidence = c.evidence[0];
  const source = evidence
    ? `${sourceText(evidence.evidence.source)} · уверенность ${CONFIDENCE[evidence.confidence_level]}`
    : definition?.provider === 'hotelier'
      ? 'Нет ответа отельера'
      : 'Нет данных в источниках';
  return {
    key: c.feature_key,
    name,
    text: `${name} — ${value}`,
    state: criterionState(c),
    required: requiredKeys.has(c.feature_key),
    askable: definition?.provider === 'hotelier',
    source,
    conflict: c.model_conflicts.map((m) => m.text).filter(Boolean).join(' ') || undefined,
  };
}

export function evidenceLines(criteria: CriterionDto[], registry: FeatureRegistryDto): EvidenceLine[] {
  return criteria.map((c) => {
    const observation = c.evidence[0];
    const label = registry[c.feature_key]?.label ?? c.feature_key;
    if (!observation) {
      return { title: label, text: c.explanation, note: 'Данных пока нет — значение не угадываем.' };
    }
    const quote = observation.evidence.details.quote;
    const text = typeof quote === 'string' && quote ? `«${quote}». ${c.explanation}` : c.explanation;
    return {
      title: label,
      text,
      note: `${sourceText(observation.evidence.source)} · получено ${formatDay(observation.collected_at)} · уверенность ${CONFIDENCE[observation.confidence_level]}`,
      url: observation.evidence.source.url ?? undefined,
    };
  });
}

/**
 * Отельер про номер не ответил, но есть расчёт по зданию (model_check в реестре):
 * показываем расчёт, а не «нет данных», и честно пишем, что номер не подтверждён.
 * Иначе отель у самой воды с широким расчётным видом уходил в «Не все условия
 * подтверждены» ниже отеля с одним подтверждённым номером и худшими фактами.
 */
export function estimatedFromModel(
  criterion: Criterion,
  dto: CriterionDto,
  byKey: Map<string, CriterionDto>,
  registry: FeatureRegistryDto,
): Criterion {
  const potentialKey = registry[dto.feature_key]?.model_check?.potential;
  const potential = potentialKey ? byKey.get(potentialKey) : undefined;
  if (criterion.state !== 'unknown' || !potential || potential.actual === null) return criterion;
  const value = valueText(potential.feature_key, potential.actual, registry[potential.feature_key]);
  const observation = potential.evidence[0];
  return {
    ...criterion,
    text: `${criterion.name} — по расчёту: ${value} · номер не подтверждён`,
    state: criterionState(potential),
    source: observation
      ? `${sourceText(observation.evidence.source)} · уверенность ${CONFIDENCE[observation.confidence_level]}`
      : criterion.source,
  };
}

export function companionKeys(parsed: ParsedQueryDto): Set<string> {
  return new Set(parsed.soft_preferences.filter((p) => p.weight_source === 'companion').map((p) => p.feature_key));
}

/** Сайт из тегов OSM: website / contact:website; «www.site.ru» → https://www.site.ru. */
export function hotelWebsite(tags: Record<string, string>): string | undefined {
  const raw = (tags.website ?? tags['contact:website'] ?? '').split(';')[0]?.trim();
  if (!raw) return undefined;
  const url = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  try {
    return new URL(url).toString();
  } catch {
    return undefined;
  }
}

export function mapHotelResult(
  item: HotelSearchResultDto,
  backendGroup: 'matched' | 'needs_verification' | 'excluded',
  parsed: ParsedQueryDto,
  registry: FeatureRegistryDto,
): HotelSummary {
  const companions = companionKeys(parsed);
  const required = new Set(parsed.hard_constraints.map((h) => h.feature_key));
  const primary = item.criteria.filter((c) => !companions.has(c.feature_key));
  const byKey = new Map(item.criteria.map((c) => [c.feature_key, c]));
  const criteria = primary.map((c) => estimatedFromModel(mapCriterion(c, registry, required), c, byKey, registry));
  // «Условия подтверждены» только если по каждому пожеланию гостя есть данные.
  let group: ResultGroup = 'partial';
  if (backendGroup === 'excluded') group = 'excluded';
  else if (backendGroup === 'matched' && criteria.every((c) => c.state !== 'unknown')) group = 'confirmed';
  const room = roomNumber(item.recommended_room_id);
  const conflicts = item.criteria.flatMap((c) => c.model_conflicts.map((m) => m.text ?? '')).filter(Boolean);
  return {
    id: item.hotel.id,
    name: item.hotel.name,
    area: 'Адлер',
    coords: { lat: item.hotel.lat, lon: item.hotel.lon },
    group,
    price: null,
    roomHint: room ? `Номер ${room}` : null,
    criteria,
    evidence: evidenceLines([...primary, ...item.criteria.filter((c) => companions.has(c.feature_key))], registry),
    warnings: [...item.warnings, ...conflicts],
    pendingQuestion: item.pending_hotelier_question_ids.length > 0,
    photo: hotelPhoto(item.hotel.id, item.hotel.name),
    website: hotelWebsite(item.hotel.tags),
    sourceUrl: item.hotel.source_url,
  };
}

export function requestChips(parsed: ParsedQueryDto, registry: FeatureRegistryDto): RequestChip[] {
  const chips: RequestChip[] = [];
  for (const hard of parsed.hard_constraints) {
    const name = featureName(hard.feature_key, registry);
    const definition = registry[hard.feature_key];
    const value =
      typeof hard.value === 'boolean'
        ? ((hard.operator === '!=' ? !hard.value : hard.value) ? ': да' : ': нет')
        : ` ${OPERATORS[hard.operator]} ${typeof hard.value === 'number' && definition?.unit === 'm' ? formatMeters(hard.value) : valueText(hard.feature_key, hard.value, definition)}`;
    chips.push({ label: `${name}${value} · обязательно`, kind: 'required' });
  }
  for (const soft of parsed.soft_preferences) {
    if (soft.weight_source === 'companion') continue;
    const name = featureName(soft.feature_key, registry);
    const negative = soft.desired === false;
    chips.push({ label: negative ? `Без: ${name.toLowerCase()}` : name, kind: 'preference' });
  }
  // Только непонятые слова. Оговорки парсера (unknown_or_ambiguous) — не «неизвестная
  // характеристика», а просьба уточнить: их показывает экран needs_clarification.
  for (const term of parsed.ignored_terms ?? []) {
    chips.push({ label: `Не учтено: ${term}`, kind: 'unsupported' });
  }
  return chips;
}

/* ---------- кабинет ---------- */

function sentences(text: string): string[] {
  return text
    .split(/(?<=[.?!])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

const REASON_NOTES: Partial<Record<QuestionDto['context']['reasons'][number], string>> = {
  pending_answer: 'Ответ отправлен, но ещё не проверен',
  unparsed_answer: 'Часть ответа не удалось разобрать',
  rejected_answer: 'Прошлый разбор отклонён — нужен новый ответ',
  conflicted: 'Источники расходятся — нужно уточнение',
  stale: 'Сведения устарели — подтвердите заново',
};

function questionNote(q: QuestionDto): string | null {
  for (const reason of ['unparsed_answer', 'pending_answer', 'rejected_answer', 'conflicted', 'stale'] as const) {
    if (q.context.reasons.includes(reason)) return REASON_NOTES[reason] ?? null;
  }
  return null;
}

export function mapQuestion(q: QuestionDto, hotelName: string, registry: FeatureRegistryDto): HotelierQuestion {
  const definition = registry[q.feature_key];
  const copy = FEATURE_COPY[q.feature_key];
  const parts = sentences(q.text);
  const ask = parts[0] ?? q.text;
  const label = definition?.label ?? q.feature_key;
  const short = copy?.name ?? label;
  const lower = short.toLowerCase();
  return {
    id: q.id,
    hotelId: q.hotel_id,
    hotelName,
    featureKey: q.feature_key,
    featureLabel: label,
    featureShort: short,
    title: copy?.question?.title ?? ask,
    prompt: parts.slice(1).join(' ') || 'Укажите конкретные номера.',
    ask,
    why: copy?.question?.why ?? `Гости ищут «${label.toLowerCase()}». Пока это условие не подтверждено.`,
    requestedBy: 'агент проверки данных',
    status: q.status === 'answered' ? 'answered' : 'open',
    createdAt: q.created_at,
    answerHint:
      'Разбор ответа пока понимает простые предложения с номерами комнат. Категории, сезоны и условия («кроме», «летом») не распознаются — их нужно переформулировать.',
    answerPlaceholder: copy?.question?.example ?? `В номерах 301–305 есть ${lower}.`,
    pendingAnswerId: q.context.reasons.includes('pending_answer') ? q.context.review_answer_id : null,
    statusNote: questionNote(q),
  };
}

/** Группирует номера с одинаковым утверждением: «Номера 301–303». */
export function groupClaims(claims: RoomClaimDto[]): ParsedClaim[] {
  const groups = new Map<string, RoomClaimDto[]>();
  for (const claim of claims) {
    const key = `${claim.value}|${claim.floor ?? ''}|${claim.quote}`;
    groups.set(key, [...(groups.get(key) ?? []), claim]);
  }
  return [...groups.values()].map((items) => {
    const first = items[0]!;
    const numbers = items.map((i) => i.room_number);
    return {
      id: numbers.join(','),
      subject: numbers.length > 1 ? `Номера ${compactNumbers(numbers)}` : `Номер ${first.room_number}`,
      subjectNote: first.floor !== null ? `${first.floor}-й этаж` : null,
      value: first.value,
      detail: capitalize(first.quote),
      quote: first.quote,
    };
  });
}

export function mapFact(f: FactDto, registry: FeatureRegistryDto): HotelFact {
  const definition = registry[f.feature_key];
  return {
    key: f.feature_key,
    label: f.label,
    value: capitalize(valueText(f.feature_key, f.value, definition)),
    status: f.reviewed_by_hotelier ? 'hotelier' : f.status,
    confidence: f.confidence_level,
    explanation: f.explanation,
    source: f.reviewed_by_hotelier ? 'Проверено отельером (демо)' : definition?.provider === 'hotelier' ? 'Ответ отельера' : 'Расчёт по открытым данным',
    reviewedByHotelier: f.reviewed_by_hotelier,
  };
}
