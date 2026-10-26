"""Сохраняем историю и выдаём последний отчёт с явной свежестью.

Ранжирование пока не читает эти отчёты: учебный шум и внешняя станция не должны
незаметно становиться «подтверждёнными свойствами» отеля.
"""
from datetime import datetime, timezone
import hashlib
import json
from sqlalchemy import select
from app.storage.models import EnvironmentReportRow


def save_report(repo, report):
    repo.hotel(report['hotel_id'])
    if report['kind'] not in ('noise', 'air_quality'):
        raise ValueError('Неизвестный тип отчёта')
    report_id = hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False,
                                        allow_nan=False).encode()).hexdigest()
    if repo.session.get(EnvironmentReportRow, report_id):
        return report_id
    repo.session.add(EnvironmentReportRow(id=report_id, hotel_id=report['hotel_id'],
        kind=report['kind'], collected_at=report['collected_at'], payload=report))
    repo.session.flush()
    return report_id


def latest_reports(repo, hotel_id, now=None):
    repo.hotel(hotel_id)
    now = now or datetime.now(timezone.utc)
    result = {}
    for kind, ttl_hours in (('air_quality', 6), ('noise', 24*30)):
        row = repo.session.scalar(select(EnvironmentReportRow).where(
            EnvironmentReportRow.hotel_id == hotel_id, EnvironmentReportRow.kind == kind
        ).order_by(EnvironmentReportRow.collected_at.desc()).limit(1))
        if row is None:
            result[kind] = dict(kind=kind, hotel_id=hotel_id, status='not_collected')
            continue
        report = dict(row.payload)
        collected = datetime.fromisoformat(report['collected_at'])
        age = (now - collected).total_seconds()/3600
        report['report_id'] = row.id
        report['cache_stale'] = age < 0 or age > ttl_hours
        report['cache_ttl_hours'] = ttl_hours
        result[kind] = report
    return result
