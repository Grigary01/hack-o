/**
 * Формы ответов FastAPI. Сверено с app/api/*, app/schemas/* и /openapi.json
 * (ветка development/adler-mvp, 2026-10-29). При изменении бэкенда правится
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

export interface ParsedQueryDto {
  region: string;
  hard_constraints: HardConstraintDto[];
  soft_preferences: SoftPreferenceDto[];
  unknown_or_ambiguous: string[];
  clarification_question: string | null;
  original_text: string;
  ignored_terms?: string[];
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
}

export interface SearchRequestDto {
  text: string;
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
  conflicts: unknown[];
}

export interface HealthDto {
  status: 'ok' | 'needs_seed';
  hotels: number;
  parser_mode: string;
  demo_mode: boolean;
}

export interface QuestionDto {
  id: string;
  hotel_id: string;
  feature_key: string;
  text: string;
  status: 'open' | 'answered' | string;
  created_at: string;
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
  idempotent?: boolean;
  observation_ids?: string[];
  model_review?: { room_id: string; reason?: string; text?: string }[];
  conflicts?: unknown[];
  source_type?: string;
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
  conflicts: unknown[];
}
