"""Что работает ночью рядом с отелем: по opening_hours из OSM.

«Открыто ночью» — открыто в 01:00 все семь дней недели. Разбор opening_hours
минимальный, но с семантикой OSM для частых форм: 24/7; «Mo-Fr 09:00-21:00;
Sa 10:00-18:00» (более позднее правило для дня перекрывает раннее); интервалы
через полночь «17:00-03:00»; off/closed; несколько интервалов через запятую.
Всё сложнее (PH, сезоны, «sunrise», недели месяца) не угадывается: такое
заведение считается «часы неизвестны» и в счёт не идёт.

Расстояние — по прямой от точки отеля (UTM). Отсутствие в OSM не доказывает,
что ночью ничего не работает: в evidence есть число заведений без часов.
"""
import re
from app.geo.geometry import metric_point, element_shape
from app.geo.osm_provider import osm_id

DAYS = ['mo', 'tu', 'we', 'th', 'fr', 'sa', 'su']
NIGHT_MINUTE = 60  # 01:00
RADIUS_M = 500
KINDS = {'pharmacy': 'аптека', 'convenience': 'магазин', 'supermarket': 'супермаркет', 'kiosk': 'киоск',
         'alcohol': 'магазин', 'bakery': 'пекарня', 'cafe': 'кафе', 'restaurant': 'ресторан',
         'fast_food': 'фастфуд', 'fuel': 'АЗС', 'bar': 'бар', 'pub': 'паб', 'nightclub': 'клуб',
         'hospital': 'больница', 'clinic': 'клиника'}
TIME = re.compile(r'^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$')
DAY_TOKEN = re.compile(r'^(mo|tu|we|th|fr|sa|su)(?:-(mo|tu|we|th|fr|sa|su))?$')


class Unsupported(ValueError):
    pass


def _days(spec):
    if not spec:
        return list(range(7))
    days = []
    for part in spec.split(','):
        m = DAY_TOKEN.match(part.strip())
        if not m:
            raise Unsupported(part)
        a = DAYS.index(m[1])
        b = DAYS.index(m[2]) if m[2] else a
        days += [d % 7 for d in range(a, b + 1 if b >= a else b + 8)]
    return days


def weekly_schedule(opening_hours):
    """Список из 7 списков интервалов (минуты от начала дня, конец может быть > 1440)."""
    text = opening_hours.strip().lower()
    if text in ('24/7', 'mo-su 00:00-24:00', '00:00-24:00'):
        return [[(0, 1440)] for _ in range(7)]
    schedule = [None] * 7
    for rule in filter(None, (r.strip() for r in text.split(';'))):
        parts = rule.split()
        if len(parts) == 1 and (TIME.match(parts[0].split(',')[0]) or parts[0] in ('off', 'closed')):
            days, times = list(range(7)), parts[0]
        elif len(parts) == 2:
            days, times = _days(parts[0]), parts[1]
        else:
            raise Unsupported(rule)
        if times in ('off', 'closed'):
            intervals = []
        else:
            intervals = []
            for span in times.split(','):
                m = TIME.match(span)
                if not m:
                    raise Unsupported(span)
                start, end = int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4])
                intervals.append((start, end if end > start else end + 1440))
        for day in days:
            schedule[day] = intervals  # более позднее правило для дня перекрывает
    return [day or [] for day in schedule]


def open_at(schedule, day, minute):
    """Открыто ли в день day (0=пн) в minute; учитывает хвост предыдущего дня после полуночи."""
    if any(a <= minute < b for a, b in schedule[day]):
        return True
    return any(a <= minute + 1440 < b for a, b in schedule[(day - 1) % 7])


def night_status(opening_hours):
    """'24/7' | 'night' (открыто в 01:00 каждый день) | 'not_night' | 'unknown'."""
    if not opening_hours:
        return 'unknown'
    if opening_hours.strip() == '24/7':
        return '24/7'
    try:
        schedule = weekly_schedule(opening_hours)
    except Unsupported:
        return 'unknown'
    return 'night' if all(open_at(schedule, d, NIGHT_MINUTE) for d in range(7)) else 'not_night'


def nearby(hotel, elements, radius=RADIUS_M):
    """Заведения в радиусе с ночным статусом, отсортированные по расстоянию."""
    point = metric_point(hotel.lat, hotel.lon)
    result = []
    for item in elements:
        tags = item.get('tags', {})
        kind = tags.get('amenity') or tags.get('shop') or ('pharmacy' if tags.get('healthcare') == 'pharmacy' else None)
        if kind not in KINDS:
            continue
        shape = element_shape(item if 'lat' in item or 'geometry' in item else
                              {**item, 'lat': item.get('center', {}).get('lat'), 'lon': item.get('center', {}).get('lon')})
        if shape is None:
            continue
        distance = point.distance(shape)
        if distance > radius:
            continue
        result.append({'osm_id': osm_id(item), 'kind': kind, 'label': KINDS[kind], 'name': tags.get('name'),
                       'distance_m': round(distance), 'opening_hours': tags.get('opening_hours'),
                       'night': night_status(tags.get('opening_hours'))})
    return sorted(result, key=lambda x: x['distance_m'])


def summarize(hotel, elements):
    places = nearby(hotel, elements)
    night = [p for p in places if p['night'] in ('24/7', 'night')]
    pharmacies = [p for p in nearby(hotel, elements, radius=5000) if p['kind'] == 'pharmacy'
                  and p['night'] in ('24/7', 'night')]
    return {
        'radius_m': RADIUS_M, 'night_places': night, 'night_count': len(night),
        'places_in_radius': len(places), 'unknown_hours_in_radius': sum(p['night'] == 'unknown' for p in places),
        'nearest_night_pharmacy': pharmacies[0] if pharmacies else None,
        'definition': 'открыто в 01:00 все 7 дней по opening_hours OSM',
    }


def explain_places(summary):
    if not summary['night_places']:
        text = f'В {summary["radius_m"]} м по OSM нет заведений, открытых ночью'
    else:
        top = ', '.join(f'{p["label"]}{" «" + p["name"] + "»" if p["name"] else ""} {p["distance_m"]} м'
                        for p in summary['night_places'][:4])
        text = f'Ночью открыто в {summary["radius_m"]} м: {top}'
        if summary['night_count'] > 4:
            text += f' и ещё {summary["night_count"] - 4}'
    unknown = summary['unknown_hours_in_radius']
    return text + (f'. У {unknown} заведений рядом часы в OSM не указаны.' if unknown else '.')


def explain_pharmacy(summary):
    p = summary['nearest_night_pharmacy']
    if p is None:
        return 'Круглосуточной аптеки в OSM поблизости не найдено (это не доказывает её отсутствие).'
    return f'Ближайшая аптека, открытая ночью: {p["name"] or "без названия"}, {p["distance_m"]} м по прямой ({p["opening_hours"]}).'
