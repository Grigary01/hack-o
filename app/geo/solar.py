"""Положение солнца по алгоритму NOAA Solar Calculator (Meeus), без зависимостей.

Точность азимута/высоты ~0.01° для 1800–2100 гг., этого с запасом хватает:
шаг лучей viewshed 1°, а погрешность рельефа и высот зданий намного больше.
Высота «видимая» — с поправкой на рефракцию, как её видит человек.
"""
from datetime import date, datetime, timedelta, timezone
import math

# Центр диска на -0.833° — стандартное определение захода (радиус + рефракция).
SUNSET_ALTITUDE = -0.833


def sun_position(when: datetime, lat: float, lon: float) -> tuple[float, float]:
    """(азимут по часовой от севера, видимая высота) в градусах для момента UTC."""
    if when.tzinfo is None:
        raise ValueError('Нужно время с часовым поясом')
    jd = when.timestamp() / 86400 + 2440587.5
    jc = (jd - 2451545) / 36525
    mean_long = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    mean_anom = math.radians(357.52911 + jc * (35999.05029 - 0.0001537 * jc))
    ecc = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    centre = (math.sin(mean_anom) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
              + math.sin(2 * mean_anom) * (0.019993 - 0.000101 * jc)
              + math.sin(3 * mean_anom) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * jc)
    app_long = math.radians(mean_long + centre - 0.00569 - 0.00478 * math.sin(omega))
    mean_obliq = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    obliq = math.radians(mean_obliq + 0.00256 * math.cos(omega))
    decl = math.asin(math.sin(obliq) * math.sin(app_long))
    y = math.tan(obliq / 2) ** 2
    l0 = math.radians(mean_long)
    eq_time = 4 * math.degrees(y * math.sin(2 * l0) - 2 * ecc * math.sin(mean_anom)
                               + 4 * ecc * y * math.sin(mean_anom) * math.cos(2 * l0)
                               - 0.5 * y * y * math.sin(4 * l0) - 1.25 * ecc * ecc * math.sin(2 * mean_anom))
    utc = when.astimezone(timezone.utc)
    minutes = utc.hour * 60 + utc.minute + utc.second / 60 + utc.microsecond / 6e7
    true_solar = (minutes + eq_time + 4 * lon) % 1440
    hour_angle = math.radians(true_solar / 4 - 180)
    phi = math.radians(lat)
    cos_zenith = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(hour_angle)
    zenith = math.acos(max(-1., min(1., cos_zenith)))
    azimuth = math.degrees(math.atan2(math.sin(hour_angle),
                                      math.cos(hour_angle) * math.sin(phi) - math.tan(decl) * math.cos(phi))) + 180
    altitude = 90 - math.degrees(zenith)
    return azimuth % 360, altitude + refraction(altitude)


def refraction(altitude: float) -> float:
    """Атмосферная рефракция NOAA в градусах для геометрической высоты."""
    if altitude > 85:
        return 0.
    t = math.tan(math.radians(altitude))
    if altitude > 5:
        seconds = 58.1 / t - 0.07 / t ** 3 + 0.000086 / t ** 5
    elif altitude > -0.575:
        seconds = 1735 + altitude * (-518.2 + altitude * (103.4 + altitude * (-12.79 + altitude * 0.711)))
    else:
        seconds = -20.772 / t
    return seconds / 3600


def sunset_track(day: date, lat: float, lon: float, max_altitude=6., step_minutes=2) -> list[dict]:
    """Последний участок дневного пути солнца: от max_altitude до захода.

    Ищем вечер в окне 11:00–21:00 UTC: для долгот 25–55° в.д. это заведомо
    покрывает заход в любой сезон. Для других регионов окно нужно сдвинуть.
    """
    if not 25 <= lon <= 55:
        raise ValueError('Окно поиска заката рассчитано на часовые пояса UTC+2…+4')
    start = datetime(day.year, day.month, day.day, 11, tzinfo=timezone.utc)
    track, previous = [], None
    for i in range(0, 600, step_minutes):
        moment = start + timedelta(minutes=i)
        azimuth, altitude = sun_position(moment, lat, lon)
        if previous is not None and previous > altitude and SUNSET_ALTITUDE < altitude <= max_altitude:
            track.append({'utc': moment.isoformat(), 'azimuth': round(azimuth, 2), 'altitude': round(altitude, 3)})
        if previous is not None and altitude < SUNSET_ALTITUDE < previous:
            break
        previous = altitude
    return track


def monthly_sunset_tracks(lat: float, lon: float, year=2026) -> dict[int, list[dict]]:
    """15-е число каждого месяца — представитель месяца (азимут за месяц меняется ≤ 10°)."""
    return {month: sunset_track(date(year, month, 15), lat, lon) for month in range(1, 13)}
