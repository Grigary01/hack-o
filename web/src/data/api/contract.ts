/**
 * Формы ответов FastAPI. Сверено с app/api/*, app/schemas/* и /openapi.json
 * (слияние main + grisha_hack, 2026-10-29). При изменении бэкенда правится
 * только этот файл и mappers.ts — компоненты не зависят от DTO.
 */

export type Value = boolean | number | string;

export interface SourceDto {
  type: 'openstreetmap' | 'geo_model' | 'hotelier' | 'hotelier_simulated' | 'operator_decision';
  name: string;
  ref: string;
  url?: string | null;
}

export interface EvidenceDto {
  source: SourceDto;
  method: string;
  raw_excerpt: string;
  snapshot_path?: string | null;
  details: Record<string, unknown>;
}

export interface ObservationDto {
  id: string;
  hotel_id: string;
  subject_type: 'hotel' | 'room';
  subject_id: string;
  feature_key: string;
  value: Value | null;
  unit: string | null;
  observed_at: string;
  collected_at: string;
  expires_at: string;
  status: 'verified' | 'estimated' | 'unknown' | 'conflicted' | 'stale';
  confidence_level: 'high' | 'medium' | 'low' | 'unknown';
  confidence: number | null;
  confidence_method: string;
  quality_flags: string[];
  evidence: EvidenceDto;
}

export interface HotelDto {
  id: string;
  name: string;
  lat: number;
  lon: number;
  region: string;
  tags: Record<string, string>;
  source_url: string;
  collected_at: string;
}

export interface FeatureDefinitionDto {
  label: string;
  description: string;
  type: 'number' | 'boolean' | 'category' | string;
  unit: string | null;
  scope: 'hotel' | 'room';
  provider: string;
  choices: string[];
  question: string | null;
  choice_labels: Record<string, string>;
  /** Утверждение отельера, которое проверяется расчётом по зданию (sea_view → sea_view_potential). */
  model_check?: { potential: string; none_value: string; min_floor: string | null } | null;
}

export type FeatureRegistryDto = Record<string, FeatureDefinitionDto>;

export interface HardConstraintDto {
  feature_key: string;
  operator: '<' | '<=' | '=' | '>=' | '>' | '!=';
  value: Value;
  unit: string | null;
  scope: 'hotel' | 'room';
}

export interface SoftPreferenceDto {
  feature_key: string;
  desired: Value;
  importance: number;
  weight_source: 'default' | 'explicit' | 'relative_inferred' | 'companion';
  scope: 'hotel' | 'room';
  derived_from: string | null;
}

/** Часть запроса гостя с цитатой (app/schemas/query.py:Need). */
export interface NeedDto {
  quote: string;
  kind: 'feature' | 'any_of' | 'unsupported';
  features: string[];
  concept: string | null;
  topic: string | null;
  /** Варианты уточнения расплывчатого пожелания — заполняет backend. */
  options: { key: string; label: string; feature_key: string }[];
  chosen: string | null;
  question: string | null;
}

/** Что нашлось у отеля по одной части запроса (app/schemas/search.py:NeedResult). */
export interface NeedResultDto {
  quote: string;
  kind: NeedDto['kind'];
  outcome: 'matched' | 'partial' | 'unknown' | 'violated' | 'unchecked';
  text: string;
  detail: string | null;
  features: string[];
  best_option: string | null;
  best_feature: string | null;
}

export interface ParsedQueryDto {
  region: string;
  hard_constraints: HardConstraintDto[];
  soft_preferences: SoftPreferenceDto[];
  unknown_or_ambiguous: string[];
  clarification_question: string | null;
  original_text: string;
  ignored_terms?: string[];
  /** Темы без поддержки (цена, бассейн…): поиск идёт без них, гостю — «не учтено». */
  unsupported?: string[];
  needs?: NeedDto[];
}

export interface CriterionDto {
  feature_key: string;
  requested: string;
  actual: Value | null;
  outcome: 'matched' | 'violated' | 'unknown' | 'preference';
  status: string;
  subject_id: string | null;
  match: number | null;
  explanation: string;
  evidence: ObservationDto[];
  model_conflicts: { text?: string }[];
}

export interface HotelSearchResultDto {
  hotel: HotelDto;
  eligible: boolean | null;
  recommended_room_id: string | null;
  score: number | null;
  coverage: number;
  ranking_score: number;
  uncertainty: number;
  criteria: CriterionDto[];
  warnings: string[];
  pending_hotelier_question_ids: string[];
  needs?: NeedResultDto[];
}

export interface SearchRequestDto {
  /** Ровно одно из двух: text (разберёт парсер) или parsed (уже разобранный запрос). */
  text?: string;
  parsed?: ParsedQueryDto;
  /** Уточнение расплывчатого пожелания без нового разбора: {"window_view": "sea"}. */
  choices?: Record<string, string>;
  include_simulated: boolean;
  ranking_method: 'weighted_v1' | 'balanced_v2';
}

export interface SearchResponseDto {
  parsed: ParsedQueryDto;
  parser_mode: string;
  status: 'ok' | 'needs_clarification';
  matched: HotelSearchResultDto[];
  needs_verification: HotelSearchResultDto[];
  excluded: HotelSearchResultDto[];
  include_simulated: boolean;
}

export interface HotelDetailDto {
  hotel: HotelDto;
  observations: ObservationDto[];
  conflicts: ConflictDto[];
}

/** Текущее знание вычисляет backend с учётом TTL, конфликтов и режима демо. */
export interface CurrentFeatureDto {
  subject_id: string;
  feature_key: string;
  value: Value | null;
  status: ObservationDto['status'];
  observations: ObservationDto[];
  resolved_conflict_ids: string[];
}

export interface HotelEvidenceDto {
  observations: ObservationDto[];
  conflicts: ConflictDto[];
  current_real: CurrentFeatureDto[];
  current_demo: CurrentFeatureDto[];
}

export interface HealthDto {
  status: 'ok' | 'needs_seed';
  hotels: number;
  parser_mode: string;
  reply_parser_mode: string;
  demo_mode: boolean;
}

/** Ошибка API: { code, detail }; detail совместим с прежним форматом FastAPI. */
export interface ApiErrorDto {
  code: 'not_found' | 'invalid_request' | 'state_conflict' | 'service_unavailable' | 'invalid_model_output' | 'forbidden' | 'http_error';
  detail: unknown;
}

export interface QuestionContextDto {
  reasons: ('unknown' | 'stale' | 'conflicted' | 'pending_answer' | 'unparsed_answer' | 'rejected_answer')[];
  subject_ids: string[];
  review_answer_id: string | null;
}

export interface QuestionDto {
  id: string;
  hotel_id: string;
  feature_key: string;
  text: string;
  status: 'open' | 'answered';
  created_at: string;
  updated_at: string;
  context: QuestionContextDto;
}

export interface ConflictDto {
  id: string;
  hotel_id: string;
  subject_id: string;
  feature_key: string;
  left_id: string;
  right_id: string;
  created_at: string;
  /** withhold_and_ask_hotelier — два ответа противоречат; review:<причина> — ответ против расчёта. */
  policy: string;
  status: 'open' | 'resolved';
  resolution: { selected_observation_id: string; reason: string; resolved_at: string; operator_id: string } | null;
}

export interface ModelReviewDto {
  room_id: string;
  reason: 'model_sees_none' | 'below_model_min_floor';
  text: string;
  hotelier_observation_id: string;
  model_observation_id: string;
}

export interface RoomClaimDto {
  room_number: string;
  floor: number | null;
  feature_key: string;
  value: boolean;
  quote: string;
}

export interface AnswerDto {
  id: string;
  question_id: string;
  text: string;
  extraction: { claims: RoomClaimDto[]; unparsed: string[]; parser_mode: string };
  status: 'pending' | 'confirmed' | 'rejected';
  simulated: boolean;
  created_at: string;
}

export interface ConfirmResponseDto {
  answer_id: string;
  status: 'confirmed' | 'rejected';
  idempotent: boolean;
  observation_ids: string[];
  conflicts: ConflictDto[];
  source_type: 'hotelier_simulated' | null;
  question: QuestionDto;
  model_review: ModelReviewDto[];
}

export interface FactDto {
  feature_key: string;
  label: string;
  value: Value | null;
  display: Value | null;
  status: ObservationDto['status'];
  confidence_level: ObservationDto['confidence_level'];
  explanation: string;
  type: string;
  unit: string | null;
  reviewed_by_hotelier: boolean;
}

export interface FactsResponseDto {
  facts: FactDto[];
  conflicts: ConflictDto[];
}
