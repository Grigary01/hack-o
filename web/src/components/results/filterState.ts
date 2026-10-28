export interface FilterState {
  priceFrom: string;
  priceTo: string;
  onlyConfirmed: boolean;
}

/** Бюджет по умолчанию — как на макете (5 000–15 000 ₽). */
export const DEFAULT_FILTERS: FilterState = { priceFrom: '5000', priceTo: '15000', onlyConfirmed: false };
