"""OpenAQ API v3: станция → датчик PM2.5 → почасовые измерения.

Используем уже установленный httpx и официальный HTTP API, без старого py-openaq
(он несовместим с v3). Ключ передаётся только в заголовке; в отчёт не попадает.
Самый близкий датчик не обязательно пригоден: проверяем стационарность, единицы,
время и покрытие за 7 завершённых суток (168 часов), затем выбираем ближайший
из пригодных. Пороги 75% / 48 часов — политика MVP, не норматив качества воздуха.
"""
from datetime import datetime, timedelta, timezone
import math
import time
import httpx
from app.geo.geometry import geodesic_distance_m

BASE = 'https://api.openaq.org/v3'
NOTICE = 'Измерение станции поблизости, не непосредственно у окна гостиницы.'


class OpenAQError(Exception):
    pass


def utc(value):
    if isinstance(value, dict):
        value = value.get('utc')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Нужна временная зона')
    return result.astimezone(timezone.utc)


class OpenAQProvider:
    def __init__(self, api_key='', transport=None):
        self.api_key = api_key
        self.transport = transport

    def _pages(self, client, path, params, max_pages=10):
        """Не принимаем обрезанную выборку за полную. Лимит защищает API-бюджет."""
        output = []
        for page in range(1, max_pages + 1):
            if time.monotonic() > self.deadline or self.request_count >= 30:
                raise OpenAQError('request_budget_exceeded')
            self.request_count += 1
            response = client.get(path, params={**params, 'limit': 1000, 'page': page})
            if response.is_error:
                raise OpenAQError(f'openaq_http_{response.status_code}')
            payload = response.json()
            rows = payload['results']
            if not isinstance(rows, list):
                raise ValueError('Некорректный results')
            output.extend(rows)
            found = payload.get('meta', {}).get('found')
            if len(rows) < 1000 or (isinstance(found, int) and len(output) >= found):
                return output
        raise OpenAQError('pagination_limit_reached')

    def collect(self, hotel, now=None, radius_m=25000):
        now = now or datetime.now(timezone.utc)
        end = now.replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=7)
        report = dict(kind='air_quality', hotel_id=hotel.id, provider='OpenAQ v3',
                      collected_at=now.isoformat(), status='not_configured',
                      notice=NOTICE, parameter='pm25', radius_m=radius_m,
                      period_from=start.isoformat(), period_to=end.isoformat(),
                      expected_hours=168, stations=[], selected=None,
                      policy={'min_coverage': .75, 'max_age_hours': 48,
                              'max_stations_checked': 10},
                      source_url='https://explore.openaq.org/')
        if not 0 < radius_m <= 25000:
            raise ValueError('OpenAQ radius должен быть 1–25000 м')
        if not self.api_key:
            report['reason'] = 'Добавьте OPENAQ_API_KEY в локальный .env и перезапустите backend.'
            return report
        try:
            self.deadline = time.monotonic() + 60
            self.request_count = 0
            with httpx.Client(base_url=BASE + '/', headers={'X-API-Key': self.api_key},
                              timeout=20, transport=self.transport) as client:
                locations = self._pages(client, 'locations', {
                    'coordinates': f'{hotel.lat},{hotel.lon}', 'radius': radius_m,
                    'parameters_id': 2})
                candidates = []
                for location in locations:
                    coords = location.get('coordinates') or {}
                    lat, lon = coords.get('latitude'), coords.get('longitude')
                    if location.get('isMobile') is not False or lat is None or lon is None:
                        continue
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        continue
                    distance = geodesic_distance_m((hotel.lat, hotel.lon), (lat, lon))
                    if distance <= radius_m:
                        candidates.append((distance, location))
                candidates.sort(key=lambda pair: (pair[0], pair[1]['id']))
                report['stations_found'] = len(candidates)
                report['candidate_limit_reached'] = len(candidates) > 10
                for distance, station in candidates[:10]:
                    sensors = self._pages(client, f'locations/{station["id"]}/sensors', {})
                    for sensor in sensors:
                        param = sensor.get('parameter') or {}
                        if param.get('name') != 'pm25':
                            continue
                        rows = self._pages(client, f'sensors/{sensor["id"]}/hours', {
                            'datetime_from': start.isoformat(), 'datetime_to': end.isoformat()})
                        item = summarize_hours(rows, start, end, param.get('units'))
                        item.update(station_id=station['id'], sensor_id=sensor['id'],
                                    station_name=station.get('name'),
                                    distance_m=round(distance), coordinates=station['coordinates'],
                                    provider=station.get('provider'), licenses=station.get('licenses', []),
                                    source_url=f'https://explore.openaq.org/locations/{station["id"]}')
                        report['stations'].append(item)
                        if report['selected'] is None and item['eligible']:
                            report['selected'] = item
                report['status'] = ('available' if report['selected'] else
                                    'no_suitable_station' if candidates else 'no_stations')
        except (httpx.HTTPError, OpenAQError, ValueError, KeyError, TypeError) as exc:
            report['status'] = 'provider_error'
            # Никогда не записываем str(httpx exception): URL/headers могут содержать секреты.
            report['reason'] = str(exc) if isinstance(exc, OpenAQError) else type(exc).__name__
            report['selected'] = None
        return report


def summarize_hours(rows, start, end, unit):
    """Пустые часы остаются пропусками, а не нулевой концентрацией.

OpenAQ отдаёт покрытие внутри каждого часа. Считаем час пригодным при >=75%
внутреннего покрытия; отдельно считаем долю таких часов во всём запросе.
При неизвестном покрытии час не используется. Дубли не увеличивают полноту.
"""
    valid = {}
    rejected = 0
    supported = unit in ('µg/m³', 'μg/m³', 'ug/m3')
    for row in rows:
        try:
            value = float(row['value'])
            a = utc(row['period']['datetimeFrom'])
            b = utc(row['period']['datetimeTo'])
            coverage = float(row['coverage']['percentCoverage'])
            parameter = row.get('parameter') or {}
            if (not supported or parameter.get('name') != 'pm25' or
                parameter.get('units') != unit or not math.isfinite(value) or value < 0 or
                not 75 <= coverage <= 100 or b - a != timedelta(hours=1) or
                a.minute or a.second or a.microsecond or a < start or b > end):
                raise ValueError('Некорректный или неполный час')
            # Повторяющиеся несовпадающие значения — конфликт, час исключаем целиком.
            valid[a] = value if a not in valid or valid[a] == value else None
        except (KeyError, TypeError, ValueError, OverflowError):
            rejected += 1
    usable = {a: v for a, v in valid.items() if v is not None}
    expected = int((end - start).total_seconds() / 3600)
    completeness = len(usable) / expected
    last = max(usable) + timedelta(hours=1) if usable else None
    age = (end - last).total_seconds() / 3600 if last else None
    return dict(unit=unit, valid_hours=len(usable), rejected_rows=rejected,
                coverage_fraction=round(completeness, 4),
                latest_measurement_at=last.isoformat() if last else None,
                age_hours=age, eligible=completeness >= .75 and age is not None and age <= 48,
                mean_pm25=round(sum(usable.values()) / len(usable), 3) if usable else None,
                aggregation='Среднее по пригодным часам; пропуски не заполнены',
                flags=[] if supported else ['unsupported_unit'])
