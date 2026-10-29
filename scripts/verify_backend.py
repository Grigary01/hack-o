"""Offline-приёмка: настоящий HTTP к uvicorn → отдельная SQLite (сценарий кабинета отельера).

Запуск: python -m scripts.verify_backend --output runtime/backend_acceptance.json
Не использует LLM, не меняет рабочую БД. Логи и тестовая база остаются в runtime/.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]
QUERY = 'Нужен номер с плотными шторами'
KEY = 'blackout_curtains'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


class API:
    """Минимальный HTTP-клиент приёмки: ошибка API — исключение с кодом и телом."""

    def __init__(self, base):
        self.base = base.rstrip('/')

    def request(self, method, path, payload=None):
        response = httpx.request(method, self.base + path, json=payload, timeout=150, trust_env=False)
        if response.is_error:
            raise RuntimeError(f'API {response.status_code} {method} {path}: {response.text[:300]}')
        return response.json()

    def get(self, path):
        return self.request('GET', path)

    def post(self, path, payload):
        return self.request('POST', path, payload)


def wait_ready(process, url):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError('Сервис завершился при запуске; см. логи в runtime/.')
        try:
            response = httpx.get(url, timeout=1, trust_env=False)
            if response.status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(.1)
    raise RuntimeError('Сервис не запустился; см. логи в runtime/.')


def verify(output):
    runtime = ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='backend-acceptance-', dir=runtime))
    database = directory / 'acceptance.db'
    port = free_port()
    base = f'http://127.0.0.1:{port}'
    # Облачные переменные из .env не должны попасть в приёмку: она без LLM.
    env = dict(os.environ, DATABASE_URL='sqlite:///' + str(database), API_URL=base,
               PARSER_MODE='fixture', REPLY_PARSER_MODE='rules', DEMO_MODE='true',
               GROQ_API_KEY='', CLOUD_LLM_BASE_URL='', CLOUD_LLM_MODEL='', HYBRID_LLM='')
    report = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'transport': 'actual HTTP -> uvicorn -> isolated SQLite',
              'real_model_used': False, 'run_directory': str(directory)}
    print('Приёмка:', directory, flush=True)

    def command(*args):
        result = subprocess.run([sys.executable, '-m', *args], cwd=ROOT, env=env,
                                check=True, capture_output=True, text=True)
        return result.stdout

    report['migration'] = json.loads(command('scripts.migrate_db'))
    from app.features.registry import get_registry
    expected_hotels = len(json.loads((ROOT / 'data/demo/hotels.json').read_text()))
    expected_features = len(get_registry().definitions)
    first_seed = command('scripts.seed_demo')
    assert command('scripts.seed_demo') == first_seed

    with ExitStack() as stack:
        backend_log = stack.enter_context((directory / 'backend.log').open('w'))

        def start_backend():
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env,
                stdout=backend_log, stderr=subprocess.STDOUT)
            stack.callback(stop, process)
            wait_ready(process, base + '/api/health')
            return process

        backend = start_backend()
        api = API(base)
        report['health'] = api.get('/api/health')
        assert report['health']['status'] == 'ok' and report['health']['hotels'] == expected_hotels
        examples = api.get('/api/demo-queries')
        initial = api.post('/api/search', {'text': examples[0]})
        report['original_geo_search'] = {group: len(initial[group])
            for group in ('matched', 'needs_verification', 'excluded')}
        assert sum(report['original_geo_search'].values()) == expected_hotels
        assert initial['status'] == 'ok' and initial['matched']
        assert KEY in api.get('/api/features') and QUERY in examples
        hotel = api.get('/api/hotels')[0]

        def simulated_matches():
            return len(api.post('/api/search', {'text': QUERY, 'include_simulated': True})['matched'])

        # Сценарий кабинета: вопрос → ответ → проверка разбора → подтверждение.
        assert simulated_matches() == 0
        qid = api.post('/api/hotelier/questions', {'hotel_id': hotel['id'], 'feature_key': KEY})['id']

        def submit(text):
            answer = api.post(f'/api/hotelier/questions/{qid}/answer', {'text': text})
            assert answer['status'] == 'pending' and answer['extraction']['claims']
            assert api.get(f'/api/hotelier/answers/{answer["id"]}')['status'] == 'pending'
            return answer

        positive = submit('В номере 501 есть плотные шторы.')
        assert simulated_matches() == 0  # до подтверждения факты не используются
        first = api.post(f'/api/hotelier/answers/{positive["id"]}/confirm', {'accept': True})
        assert first['status'] == 'confirmed' and not first['idempotent']
        assert simulated_matches() == 1
        confirmation = api.post(f'/api/hotelier/answers/{positive["id"]}/confirm', {'accept': True})
        assert confirmation['idempotent'] and len(confirmation['observation_ids']) == 1
        selected = confirmation['observation_ids'][0]
        assert not api.post('/api/search', {'text': QUERY})['matched']  # симуляция не в реальном поиске

        # Противоречивый ответ: конфликт, вопрос снова открыт, поиск не берёт ни одну версию.
        negative = submit('В номере 501 нет плотных штор.')
        api.post(f'/api/hotelier/answers/{negative["id"]}/confirm', {'accept': True})
        assert simulated_matches() == 0
        question = next(q for q in api.get('/api/hotelier/questions?hotel_id=' + hotel['id']) if q['id'] == qid)
        assert question['status'] == 'open' and 'conflicted' in question['context']['reasons']
        conflict = api.get('/api/hotelier/conflicts?hotel_id=' + hotel['id'] + '&status=open')[0]
        reason = 'Приёмка: выбран исходный ответ о номере 501'
        decision = api.post(f'/api/hotelier/conflicts/{conflict["id"]}/resolve',
                            {'selected_observation_id': selected, 'reason': reason})
        assert not decision['idempotent'] and decision['current']['value'] is True
        assert simulated_matches() == 1
        report['api_flow'] = {'unknown_matches': 0, 'pending_matches': 0,
            'confirmed_matches': 1, 'conflicted_matches': 0, 'resolved_matches': 1,
            'explicit_selection_and_reason_required': True}

        for method in ('weighted_v1', 'balanced_v2'):
            result = api.post('/api/search', {'text': QUERY, 'include_simulated': True,
                'ranking_method': method, 'balance': .4})
            assert len(result['matched']) == 1
            assert result['matched'][0]['recommended_room_id'] == hotel['id'] + ':room:501'
            assert result['balance'] == .4
        evidence = api.get(f'/api/hotels/{hotel["id"]}/evidence')
        observations = [o for o in evidence['observations'] if o['feature_key'] == KEY]
        assert len(observations) == 2 and {o['value'] for o in observations} == {True, False}
        assert all(o['confidence_level'] == 'low' and o['evidence']['source']['type'] == 'hotelier_simulated'
                   for o in observations)
        report['observations'] = observations
        resolution_path = f'/api/hotelier/conflicts/{conflict["id"]}/resolve'
        report['resolution'] = api.post(resolution_path, {'selected_observation_id': selected, 'reason': reason})
        assert report['resolution']['idempotent']
        error = httpx.post(base + resolution_path, json={
            'selected_observation_id': next(o['id'] for o in observations if o['id'] != selected),
            'reason': 'Несовместимый повтор'})
        assert error.status_code == 409 and error.json()['code'] == 'state_conflict'
        report['incompatible_repeat'] = {'status_code': error.status_code, 'body': error.json()}

        stop(backend)
        # Проверяем повторные миграцию и seed уже заполненной базы, сохраняя историю.
        report['repeat_migration'] = json.loads(command('scripts.migrate_db'))
        command('scripts.seed_demo')
        start_backend()
        assert api.get(f'/api/hotelier/answers/{positive["id"]}')['status'] == 'confirmed'
        persisted = api.get(f'/api/hotels/{hotel["id"]}/evidence')
        assert {o['id'] for o in persisted['observations'] if o['feature_key'] == KEY} == {o['id'] for o in observations}
        question = next(q for q in api.get('/api/hotelier/questions') if q['id'] == qid)
        assert question['status'] == 'answered'
        assert len(api.post('/api/search', {'text': QUERY, 'include_simulated': True})['matched']) == 1
        with sqlite3.connect(database) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            assert db.execute('SELECT COUNT(*) FROM hotels').fetchone()[0] == expected_hotels
            assert db.execute('SELECT COUNT(*) FROM feature_definitions').fetchone()[0] == expected_features
        backup = report['repeat_migration']['backup']
        assert backup and Path(backup).is_file()
        report.update(restart_seed_migration_preserve_history=True, database_integrity='ok',
                      browser_visual_check='not performed here; React UI is checked separately',
                      both_ranking_methods='passed', status='passed')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('PASS:', output, flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime/backend_acceptance.json')
    verify(parser.parse_args().output)
