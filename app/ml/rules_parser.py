"""Офлайн-разбор свободного русского запроса по правилам и словарю из реестра.

Нужен, чтобы произвольный запрос работал без ключа LLM. Это не NLP-модель:
регулярные выражения по основам слов (registry.query_patterns) плюс небольшой
набор правил для отрицаний, близости, чисел и важности. Выход — тот же
ParsedHotelQuery, что у LLM, с той же проверкой Pydantic.

Принципы те же, что в промпте LLM:
- отрицание сохраняется: «без баров» → far, «без вида на море» → False;
- числа не выдумываются: нет числа — только near/far;
- неподдерживаемое (цена, бассейн, другой город) не отбрасывается молча,
  а попадает в unknown_or_ambiguous с вопросом на уточнение.

Новая характеристика понимается после добавления query_patterns в YAML.
"""
import re
from app.features.registry import get_registry
from app.schemas.query import ParsedHotelQuery, HardConstraint, SoftPreference, UtilityCurve

WALK_M_PER_MINUTE = 80  # ~4.8 км/ч; «5 минут пешком» → 400 м
WORD = re.compile(r'[a-zа-я0-9]+(?:[.,][0-9]+)?')
# Грубые формы тоже отрицание: «нахуй бары» — бары не нужны. Английские — для простых запросов без LLM.
NEGATIONS = {'не', 'без', 'нет', 'никаких', 'никакого', 'никакой', 'ни', 'нахуй', 'нахер', 'нафиг', 'нафик', 'долой',
             'no', 'not', 'without', 'never'}
# «не» перед этими словами — оператор («не дальше 500 м»), а не отрицание желания.
OPERATOR_AFTER_NE = re.compile(r'^(дальше|далее|более|больше|ближе|менее|меньше|выше|ниже)$')
NEAR_WORDS = re.compile(r'^(рядом|поближе|ближе|недалеко|близко|возле|около|вблизи|шаговой|самого|берегу|у|к|до|'
                        r'near|nearby|close|next)$')
FAR_WORDS = re.compile(r'^(подальше|далеко|вдали|вдалеке|дальше|далее|far|away)$')
AFTER_DIRECTION = re.compile(r'^\s*[—-]?\s*(не\s+)?(подальше|далеко|поближе|рядом|близко|недалеко)\b')
HARD_MARKERS = re.compile(r'\b(обязател\w*|только|строго|непременно|точно|гарантированно|исключительно|никак\w*)\b')
SOFT_MARKERS = re.compile(r'\b(желательно|хотелось бы|по возможности|неплохо бы|было бы|можно|не обязател\w*|необязател\w*|если получится)\b')
POST_NEGATION = re.compile(r'^\s*(\S+\s+){0,2}?не\s+(надо|хочу|хотим|интересн\w*|люблю)')
# «не хочу рядом с барами»: отрицание глагола переворачивает «рядом» в «подальше».
VERB_NEGATION = re.compile(r'\bне\s+(хоч|хот|нуж|надо|люб)\w*')
IRRELEVANT = re.compile(r'^\s*(\S+\s+){0,2}?(не\s+важ\w*|неважн\w*|все равно|без разницы|не принципиальн\w*|'
                        r'не\s+нуж\w*|не\s+обязател\w*|необязател\w*)')
EXPLICIT_WEIGHT = re.compile(r'^\s*(\S+\s+){0,2}?с?\s*вес\w*\s*(0?[.,]\d+|1(?:[.,]0+)?|0)\b')
WORD_NUMBERS = {'один': 1, 'одну': 1, 'одной': 1, 'одного': 1, 'две': 2, 'два': 2, 'двух': 2, 'три': 3, 'трех': 3,
                'четыре': 4, 'четырех': 4, 'пять': 5, 'пяти': 5, 'шесть': 6, 'шести': 6, 'семь': 7, 'семи': 7,
                'восемь': 8, 'восьми': 8, 'девять': 9, 'девяти': 9, 'десять': 10, 'десяти': 10,
                'пятнадцать': 15, 'пятнадцати': 15, 'двадцать': 20, 'двадцати': 20, 'тридцать': 30, 'тридцати': 30,
                'сорок': 40, 'сорока': 40, 'пятьдесят': 50, 'пятидесяти': 50, 'сто': 100, 'ста': 100,
                'двести': 200, 'двухсот': 200, 'триста': 300, 'трехсот': 300, 'пятьсот': 500, 'пятисот': 500,
                'полтора': 1.5, 'полутора': 1.5}
# Служебные и общие слова запроса: их отсутствие в разборе — не потеря смысла.
FILLER = set('''хочу хотим хотелось хотела хотел нужен нужна нужно нужны надо ищу ищем найди найдите покажи покажите
подбери подберите посоветуй посоветуйте отель отеля отели отелей отелю гостиница гостиницу гостиницы гостиниц номер
номера номере номером чтобы было были была быть есть рядом недалеко поближе подальше близко далеко очень пожалуйста
желательно обязательно главное важно важнее можно вариант варианты варианта поездки поездку отдых отдыха отдыхать
жить пожить остановиться адлер адлере адлера сочи район районе района место места месте где который которая
которые чтоб тоже также просто всего более менее минимум максимум ровно примерно около пешком минут минуты метров
метра километр километра километре километров дорога дороги путь пути нас мне меня нам себя хорошо хороший хорошая
будет было бы лучше самый самая самое так этот эта это хачу хочю хачю
hotel hotels room rooms with the and for want need would like please very from that this some just'''.split())
LONGEST_TERM = 30  # длиннее — мусор вроде «аааа…», в «не учтено» не показываем
MAX_DISTANCE_M = 50_000  # дальше 50 км — уже не прибрежный Адлер, число скорее ошибочно

# Модерация: такие слова не показываются гостю в «не учтено». Запрещённые темы — вежливый отказ
# в этом условии (unknown_or_ambiguous), остальной запрос не разбирается молча.
PROFANITY = re.compile(
    r'\b(ху[йеёяию]\w*|нахуй\w*|похуй\w*|пизд\w*|(по|за|на|от|вы|у|при|раз)?еб(а|у|и|л|ё)\w*|'
    r'бля\w*|сук[аи]\b|сучк\w*|мудак\w*|мудил\w*|пидор\w*|пидар\w*|гандон\w*|(по|за|на|от|вы|пере)?трах\w*|дерьм\w*|говн\w*|'
    r'жоп\w*|залуп\w*|нахер\w*|fuck\w*|shit\w*|bitch\w*)')
BLOCKED = {
    'sex': (r'\b(проститут\w*|шлюх\w*|эскорт\w*|бордел\w*|интим-?услуг\w*|секс(а|ом|у)?\b|sex\b|escort\w*|prostitut\w*)',
            'Интим-услуги и подобные условия в подборе не участвуют'),
    'drugs': (r'\b(травк\w*|закладк\w*|нарко\w*|кокаин\w*|героин\w*|мефедрон\w*|гашиш\w*|марихуан\w*|спайс\w*|'
              r'weed\b|drugs?\b|cocaine\b)',
              'Поиск запрещённых веществ не поддерживается'),
    'documents': (r'без паспорт\w*|не провер\w* паспорт\w*|без документ\w*|без регистрац\w*',
                  'Заселение без документов не поддерживается: отели обязаны их проверять'),
    'discrimination': (r'\b(без|кроме|только для|не для|никаких|чтобы не было|запрет\w*)\s+(\w+\s+)?'
                       r'(кавказц|славян|армян|грузин|чечен|дагестан|узбек|таджик|киргиз|евре|цыган|азиат|'
                       r'мусульман|христиан|негр|черн(ых|ые|ым)\b|иностран|приезж)\w*|'
                       r'\b(чурк\w*|хачи\b|хачей\b|хачам\b|жид(ы|ов|ам|ами|ах|а|у|ом)?\b|негр(ы|ов|ам|ами|ах|а|у|ом)?\b|nigg\w*)',
                       'Подбор по национальности, вере или происхождению гостей не выполняется'),
}
NEGATIVE_NUMBER = re.compile(r'(?<!\w)[-−–]\s?\d+(?:[.,]\d+)?\s*(км|километр\w*|метр\w*|м\b)')
SCIENTIFIC_NUMBER = re.compile(r'\d[eе][+-]?\d')
# Запятая/точка внутри числа («1,2 км») фразу не делят.
CLAUSE_SPLIT = re.compile(r'(?:[;!?\n]|(?<!\d)[,.]|[,.](?!\d))+|\s(?:но|однако|зато|а также)\s')
# Число не должно быть хвостом другого токена: «1e9 м» — не «9 м», «-500 м» — не «500 м».
NUMBER = re.compile(r'(?<![\w.,\-−–])(\d+(?:[.,]\d+)?)\s*(км|километр\w*|метр\w*|м\b|мин\w*)|(полкилометра|километр[еау]?\b|полчаса)')
RANGE = re.compile(r'(между|от)\s+(\d+(?:[.,]\d+)?)\s*(км|м|метр\w*|километр\w*)?\s+(и|до)\s+(\d+(?:[.,]\d+)?)\s*(км|километр\w*|метр\w*|м\b)')
OPERATORS = [  # проверяются на тексте между предыдущим и текущим числом; длинные формы раньше
    (re.compile(r'не\s+(дальше|далее|более|больше)|максимум|в пределах|не превыша\w*|\bдо\s*$'), '<='),
    (re.compile(r'не\s+(ближе|менее|меньше)|минимум|хотя бы|как минимум|\bот\s*$'), '>='),
    (re.compile(r'(меньше|ближе|менее)\s*(чем)?\s*(в)?\s*$'), '<'),
    (re.compile(r'(больше|дальше|более)\s*(чем)?\s*(в)?\s*$'), '>'),
    (re.compile(r'ровно\s*$'), '='),
]
SUFFIX_OPERATORS = [
    (re.compile(r'^\s*(и\s+)?(максимум|не\s+(дальше|далее|больше|более)|в\s+пределах)'), '<='),
    (re.compile(r'^\s*(и\s+)?(минимум|не\s+(ближе|меньше|менее)|как\s+минимум)'), '>='),
]
OTHER_REGIONS = re.compile(
    r'\b(москв\w*|питер\w*|петербург\w*|спб|анап\w*|геленджик\w*|ялт\w*|крым\w*|казан\w*|красн\w* полян\w*|'
    r'роз\w* хутор\w*|лазаревск\w*|хост\w*|туапсе|кисловодск\w*|абхази\w*|гагр\w*|пицунд\w*|турци\w*|сириус\w*|'
    r'имеретинск\w*|евпатори\w*|калининград\w*|минск\w*|центр\w* сочи|сочи[- ]центр\w*)\b')
UNSUPPORTED = {
    'цена': r'руб\w*|₽|\bр\.|дешев\w*|недорог\w*|бюджет\w*|\bцен[аыу]\b|стоимост\w*|эконом\w*|скидк\w*',
    'звёздность': r'звезд\w*|звёзд\w*|\b\d\s*\*',
    'питание': r'завтрак\w*|питани\w*|вс[её] включено|ужин\w*',
    'бассейн': r'бассейн\w*|аквапарк\w*',
    'питомцы': r'собак\w*|кошк\w*|питом\w*|животн\w*',
    'парковка': r'парковк\w*|машин\w*|автомобил\w*|\bавто\b',
    'дети': r'\bдет(и|ей|ям|ьми|ский|ская|ское|ские)\b|реб[её]н\w*|малыш\w*',
    'интернет': r'wi-?fi|вайфай\w*|интернет\w*',
    'даты поездки': r'\b\d+\s*(ноч\w*|дн(я|ей)|суток)\b|\bдат[аыу]\b|заезд\w*|выезд\w*',
    'спа и сауна': r'\bспа\b|spa|саун\w*|массаж\w*',
    'отзывы и рейтинг': r'отзыв\w*|рейтинг\w*',
    'наличие мест и бронирование': r'бронир\w*|свободн\w* номер\w*|доступ\w* ли|наличи\w* мест|\bзавтра\b|\bсегодня\b',
    'магазины и кафе рядом днём': r'магазин\w*|супермаркет\w*|\bкафе\b|ресторан\w*|столов\w*',
    'расстояние по прямой': r'по прямой',
}
GENERAL = re.compile(r'отел\w*|гостиниц\w*|гостев\w*|покажи|подбери|найди|ищу|вариант\w*|жиль\w*|номер\w*|адлер\w*|\bhotels?\b')


def normalize(text):
    """Нижний регистр, ё → е, числа словами → цифры («пять минут» → «5 минут»)."""
    text = text.lower().replace('ё', 'е')
    return re.sub(r'\b(' + '|'.join(WORD_NUMBERS) + r')\b', lambda m: str(WORD_NUMBERS[m[1]]), text)


class RulesQueryParser:
    mode = 'rules'

    def __init__(self, registry=None):
        self.registry = registry or get_registry()
        self.compiled = {
            key: ([re.compile(p.replace('ё', 'е')) for p in d.query_patterns],
                  [re.compile(p.replace('ё', 'е')) for p in d.query_negative_patterns])
            for key, d in self.registry.definitions.items() if d.query_patterns
        }

    def parse(self, text: str) -> ParsedHotelQuery:
        lowered = normalize(text)
        unknown = []
        region = 'Adler'
        if OTHER_REGIONS.search(lowered):
            region = 'other'
            unknown.append('Поддерживается только прибрежный Адлер')
        for pattern, message in BLOCKED.values():
            if re.search(pattern, lowered) and message not in unknown:
                unknown.append(message)
        if NEGATIVE_NUMBER.search(lowered):
            unknown.append('Отрицательное расстояние не имеет смысла — уточните число')
        if SCIENTIFIC_NUMBER.search(lowered):
            unknown.append('Число вида 1e9 не разбираем — напишите его цифрами')
        mentions = self._find_mentions(lowered)
        sunset = any(m['key'] == 'sunset_view' for m in mentions)
        for topic, pattern in UNSUPPORTED.items():
            if topic == 'даты поездки' and sunset:
                continue  # «закат в июле» — месяцы уже в объяснении расчёта
            if topic == 'магазины и кафе рядом днём' and any(m['key'] == 'night_open_places_500m' for m in mentions):
                continue  # «круглосуточный магазин» — это уже ночная характеристика
            if topic == 'расстояние по прямой' and not any(m['key'] == 'walking_distance_to_beach_m' for m in mentions):
                continue  # до баров расстояние и так по прямой; не поддерживается только для пляжа
            if re.search(pattern, lowered):
                unknown.append(f'Пока не поддерживается: {topic}')
        hard, soft = [], []
        for mention in mentions:
            items = self._interpret(mention, unknown, lowered)
            for item in items if isinstance(items, list) else [items]:
                if item is not None:
                    (hard if isinstance(item, HardConstraint) else soft).append(item)
        # Одно и то же условие, найденное по двум упоминаниям («у моря … до пляжа <= 700 м»), — один раз.
        hard = [h for i, h in enumerate(hard) if h not in hard[:i]]
        soft = self._dedupe(soft, hard)
        self._relative_importance(lowered, mentions, soft)
        if not hard and not soft and not unknown and not mentions and not GENERAL.search(lowered):
            unknown.append('Не нашёл поддерживаемых пожеланий')
        ignored = self._ignored_terms(lowered, mentions)
        question = None
        if unknown:
            supported = ', '.join(sorted({self.registry.get(k).label.lower() for k in self.compiled}))
            question = ('Уточните запрос: ' + '; '.join(unknown) + '. Уберите эти условия, чтобы искать по остальным. '
                        'Сейчас система проверяет: ' + supported + '.')
        return ParsedHotelQuery(region=region, hard_constraints=hard, soft_preferences=soft,
                                unknown_or_ambiguous=unknown, clarification_question=question, original_text=text,
                                ignored_terms=ignored)

    def _ignored_terms(self, lowered, mentions):
        """Содержательные слова вне найденных характеристик, модификаторов и неподдерживаемых тем."""
        covered = [(m['start'], m['end']) for m in mentions]
        hidden = list(UNSUPPORTED.values()) + [p for p, _ in BLOCKED.values()] + [PROFANITY.pattern]
        for pattern in hidden + [OTHER_REGIONS.pattern, NUMBER.pattern, RANGE.pattern]:
            covered += [(m.start(), m.end()) for m in re.finditer(pattern, lowered)]
        result = []
        for m in WORD.finditer(lowered):
            word = m.group()
            if (len(word) < 4 or len(word) > LONGEST_TERM or word.isdigit() or word in FILLER or word in NEGATIONS
                    or NEAR_WORDS.match(word)
                    or FAR_WORDS.match(word) or HARD_MARKERS.match(word) or SOFT_MARKERS.match(word)
                    or any(a <= m.start() < b for a, b in covered) or word in result):
                continue
            result.append(word)
        return result[:30]

    def _find_mentions(self, lowered):
        """Все совпадения; перекрывающиеся — в пользу более длинного (потом порядка реестра)."""
        found = []
        order = list(self.registry.definitions)
        for key, (positive, negative) in self.compiled.items():
            for polarity, patterns in ((True, positive), (False, negative)):
                for pattern in patterns:
                    for m in pattern.finditer(lowered):
                        found.append({'key': key, 'start': m.start(), 'end': m.end(), 'positive': polarity})
        found.sort(key=lambda m: (-(m['end'] - m['start']), order.index(m['key']), m['start']))
        taken, result = [], []
        for m in found:
            if any(m['start'] < e and s < m['end'] for s, e in taken):
                continue
            taken.append((m['start'], m['end']))
            result.append(m)
        return sorted(result, key=lambda m: m['start'])

    @staticmethod
    def _clause(lowered, start, end):
        bounds = [0] + [m.end() for m in CLAUSE_SPLIT.finditer(lowered)] + [len(lowered)]
        left = max(b for b in bounds if b <= start)
        right = min((m.start() for m in CLAUSE_SPLIT.finditer(lowered) if m.start() >= end), default=len(lowered))
        return lowered[left:start], lowered[end:right], lowered[left:right]

    def _interpret(self, mention, unknown, lowered):
        key = mention['key']
        definition = self.registry.get(key)
        before, after, clause = self._clause(lowered, mention['start'], mention['end'])
        if IRRELEVANT.match(after):
            return None  # «шумоизоляция не важна» — не учитывать, а не «нужно без неё»
        weight = EXPLICIT_WEIGHT.match(after)
        pre = WORD.findall(before)[-6:]
        negated = any(word in NEGATIONS and not (i + 1 < len(pre) and OPERATOR_AFTER_NE.match(pre[i + 1]))
                      and not (i + 1 < len(pre) and pre[i + 1].startswith('обязател'))
                      for i, word in enumerate(pre))
        # «без шумоизоляции не надо» — двойное отрицание, желание остаётся.
        negated ^= bool(POST_NEGATION.match(after))
        near = far = False
        window = pre[-4:]
        for i, word in enumerate(window):
            prev_ne = i > 0 and window[i - 1] == 'не'
            if NEAR_WORDS.match(word):
                near, far = (False, True) if prev_ne else (True, False)
            elif FAR_WORDS.match(word):
                near, far = (True, False) if prev_ne else (False, True)
        if not near and not far:
            # «бары подальше», «пляж рядом», «бары не рядом» — наречие после признака.
            post = AFTER_DIRECTION.match(after)
            if post:
                near = (post[2] in ('поближе', 'рядом', 'близко', 'недалеко')) != bool(post[1])
                far = not near
        if near and VERB_NEGATION.search(before):
            near, far = False, True
        if far or near:
            negated = False  # «не рядом» уже учтено как far
        hard = bool(HARD_MARKERS.search(clause)) and not SOFT_MARKERS.search(clause)
        positive = mention['positive'] != negated

        if definition.type == 'number':
            numbers = self._numbers(clause, key, unknown)
            if numbers:
                return numbers
            # Для мест и источников шума отрицание значит «держаться подальше»:
            # «без баров», «чтобы не было слышно самолётов» → far.
            desired = 'near' if near else 'far' if far or not positive else definition.query_desired
            if definition.query_negation_keeps:
                desired = definition.query_desired  # «без подъёмов», «не переходить трассу» — тоже «поменьше»
            if key == 'aircraft_path_distance_m' and desired == 'near':
                unknown.append('Близость к аэропорту ради трансфера пока не поддерживается')
                return None
            if weight:  # «пляж рядом с весом 0.3»
                return SoftPreference(feature_key=key, desired=desired, scope=definition.scope,
                                      importance=float(weight[2].replace(',', '.')), weight_source='explicit')
            return SoftPreference(feature_key=key, desired=desired, scope=definition.scope)
        if definition.type == 'boolean':
            value = positive
        else:  # category: желаемое значение или противоположный край шкалы
            value = definition.query_desired if positive else definition.choices[0]
        if hard:
            return HardConstraint(feature_key=key, operator='=', value=value, scope=definition.scope)
        if weight:
            return SoftPreference(feature_key=key, desired=value, scope=definition.scope,
                                  importance=float(weight[2].replace(',', '.')), weight_source='explicit')
        return SoftPreference(feature_key=key, desired=value, scope=definition.scope)

    def _numbers(self, clause, key, unknown):
        """Числа фразы: «не дальше 500 м» → hard <=; «между 300 и 800 м» → два hard;
        «в 300 м от моря» без оператора → мягкая цель «идеально до 300 м»."""
        definition = self.registry.get(key)
        to_m = lambda raw, unit: float(raw.replace(',', '.')) * (1000 if unit and unit.startswith('к') else 1)
        clean = lambda v: int(v) if float(v).is_integer() else round(v, 1)
        span = RANGE.search(clause)
        if span:
            unit = span[6]
            low, high = sorted((to_m(span[2], span[3] or unit), to_m(span[5], unit)))
            return [HardConstraint(feature_key=key, operator='>=', value=clean(low), unit=definition.unit,
                                   scope=definition.scope),
                    HardConstraint(feature_key=key, operator='<=', value=clean(high), unit=definition.unit,
                                   scope=definition.scope)]
        result, previous_end = [], 0
        for match in NUMBER.finditer(clause):
            if match[3]:  # число словом: «в километре», «полкилометра», «полчаса»
                word = match[3]
                value, unit = (500., 'м') if word == 'полкилометра' else (30., 'мин') if word == 'полчаса' else (1000., 'м')
            else:
                value, unit = to_m(match[1], match[2]), match[2]
            if unit.startswith('мин'):
                if not re.search(r'пешк\w*|ходьб\w*|пешеход\w*', clause):
                    unknown.append('Время в пути без «пешком» неоднозначно')
                    return [None]
                value *= WALK_M_PER_MINUTE
            if value > MAX_DISTANCE_M:
                km = f'{value / 1000:,.0f}'.replace(',', ' ')
                unknown.append(f'Расстояние {km} км выходит за район поиска — уточните число')
                return [None]
            prefix = clause[previous_end:match.start()]
            previous_end = match.end()
            operator = next((op for pattern, op in OPERATORS if pattern.search(prefix[-40:])), None)
            if operator is None:  # «1,5 км максимум», «300 м и не ближе»
                suffix = clause[match.end():match.end() + 20]
                operator = next((op for pattern, op in SUFFIX_OPERATORS if pattern.match(suffix)), None)
            if operator:
                result.append(HardConstraint(feature_key=key, operator=operator, value=clean(value),
                                             unit=definition.unit, scope=definition.scope))
            elif not result and value == 0:
                # «0 метров до пляжа» — просто «как можно ближе»; кривая с нулевым допуском невозможна.
                result.append(SoftPreference(feature_key=key, desired='near', scope=definition.scope))
            elif not result:
                # Число без оператора — пожелание, а не запрет: идеально до N, к 2N уже неудобно.
                result.append(SoftPreference(feature_key=key, desired='near', scope=definition.scope,
                                             utility=UtilityCurve(kind='lower', ideal_max=clean(value),
                                                                  tolerance=clean(value))))
        return result

    @staticmethod
    def _dedupe(soft, hard):
        """Одна характеристика — одно пожелание; hard важнее soft того же ключа."""
        hard_keys = {h.feature_key for h in hard}
        result, seen = [], set()
        for pref in soft:
            if pref.feature_key in hard_keys or pref.feature_key in seen:
                continue
            seen.add(pref.feature_key)
            result.append(pref)
        return result

    def _relative_importance(self, lowered, mentions, soft):
        """«Тишина важнее вида»: левая часть — 1, правая — 0.5 (relative_inferred)."""
        split = re.search(r'\bважнее\b', lowered)
        if not split:
            return
        left = {m['key'] for m in mentions if m['end'] <= split.start()}
        right = {m['key'] for m in mentions if m['start'] >= split.end()}
        for pref in soft:
            if pref.feature_key in left or pref.feature_key in right:
                pref.importance = 1. if pref.feature_key in left else .5
                pref.weight_source = 'relative_inferred'
