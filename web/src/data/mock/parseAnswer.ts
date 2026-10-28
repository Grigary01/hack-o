/**
 * Демо-разбор свободного ответа отельера про шторы blackout по категориям номеров.
 * Нарочно ограниченный: непонятное не угадывается, а попадает в unparsed —
 * так же ведёт себя bounded-парсер бэкенда (app/hotelier/dialogue.py).
 */

export interface DraftClaim {
  category: string;
  note: string | null;
  value: boolean;
  detail: string;
  quote: string;
}

export interface ParseResult {
  claims: DraftClaim[];
  unparsed: string[];
}

const CATEGORIES: [RegExp, string][] = [
  [/улучшенн/, 'Улучшенный'],
  [/стандартн/, 'Стандартный'],
  [/делюкс|deluxe/, 'Делюкс'],
  [/(?<!де)люкс(?!\p{L})|(?<!де)люкс(?:ах|ы|ов)|suite/u, 'Люкс'],
  [/семейн/, 'Семейный'],
  [/эконом/, 'Эконом'],
];

const NOTES: [RegExp, string][] = [
  [/окн\p{L}*\s+(?:выходят\s+)?во\s+двор/u, 'Окна во двор'],
  [/окн\p{L}*\s+(?:выходят\s+)?на\s+море|вид\p{L}*\s+на\s+море/u, 'Окна на море'],
  [/окн\p{L}*\s+(?:выходят\s+)?на\s+улиц/u, 'Окна на улицу'],
];

const MENTIONS = /blackout|блэкаут|блекаут|затемн|штор/;
// В JS \b не знает кириллицу, поэтому границы слова — через \p{L}.
const word = (body: string) => new RegExp(`(?<!\\p{L})(?:${body})(?!\\p{L})`, 'u');
const NEGATIVE = new RegExp(`обычн|${word('нет|без').source}|отсутств|не\\s+устан|не\\s+имеют|только\\s+тюль`, 'u');
const UNCERTAIN = word('возможно|наверно|кажется|если|кроме|частично|летом|зимой|скоро|планиру\\p{L}*');
const FULL_DARK = /полностью\s+перекрыва|не\s+пропуска\p{L}*\s+свет|полн\p{L}+\s+затемн/u;

function detailFor(sentence: string, value: boolean): string {
  if (FULL_DARK.test(sentence)) return 'Полностью перекрывают дневной свет';
  if (!value && /обычн/.test(sentence)) return 'Обычные шторы';
  if (/электропривод/.test(sentence)) return 'Шторы blackout с электроприводом';
  if (/плотн/.test(sentence)) return 'Плотные шторы';
  return value ? 'Шторы blackout' : 'Без штор blackout';
}

export function parseBlackoutAnswer(text: string): ParseResult {
  const claims: DraftClaim[] = [];
  const unparsed: string[] = [];
  const sentences = text
    .split(/[.;!?\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  for (const raw of sentences) {
    const sentence = raw.toLowerCase().replace(/ё/g, 'е');
    const categories = CATEGORIES.filter(([re]) => re.test(sentence)).map(([, name]) => name);
    const note = NOTES.find(([re]) => re.test(sentence))?.[1] ?? null;
    const negative = NEGATIVE.test(sentence);

    // «Они полностью перекрывают свет» — уточнение к предыдущему утверждению.
    if (categories.length === 0 && FULL_DARK.test(sentence) && claims.length > 0) {
      const last = claims[claims.length - 1]!;
      if (last.value) last.detail = 'Полностью перекрывают дневной свет';
      continue;
    }
    if (categories.length === 0 || UNCERTAIN.test(sentence) || (!MENTIONS.test(sentence) && !negative)) {
      unparsed.push(raw);
      continue;
    }
    const value = !negative;
    for (const category of categories) {
      claims.push({ category, note, value, detail: detailFor(sentence, value), quote: raw });
    }
  }

  // Ответ, противоречащий сам себе, подтверждать нельзя.
  const seen = new Map<string, boolean>();
  for (const claim of claims) {
    const previous = seen.get(claim.category);
    if (previous !== undefined && previous !== claim.value) {
      unparsed.push(`Противоречие: категория «${claim.category}» указана и с blackout, и без`);
    }
    seen.set(claim.category, claim.value);
  }
  return { claims, unparsed };
}
