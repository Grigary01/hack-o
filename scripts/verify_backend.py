"""Offline-приёмка: Streamlit/AppTest → настоящий HTTP → отдельная SQLite.

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
from streamlit.testing.v1 import AppTest

from frontend.api_client import APIClient


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
    port, ui_port = free_port(), free_port()
    while ui_port == port:
        ui_port = free_port()
    base = f'http://127.0.0.1:{port}'
    env = dict(os.environ, DATABASE_URL='sqlite:///' + str(database), API_URL=base,
               PARSER_MODE='fixture', REPLY_PARSER_MODE='rules', DEMO_MODE='true',
               STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')
    report = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'transport': 'Streamlit AppTest -> actual HTTP -> isolated SQLite',
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
        ui_log = stack.enter_context((directory / 'streamlit.log').open('w'))

        def start_backend():
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env,
                stdout=backend_log, stderr=subprocess.STDOUT)
            stack.callback(stop, process)
            wait_ready(process, base + '/api/health')
            return process

        backend = start_backend()
        streamlit = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run',
            'frontend/app.py', '--server.address', '127.0.0.1', '--server.port', str(ui_port),
            '--server.headless', 'true', '--browser.gatherUsageStats', 'false'],
            cwd=ROOT, env=env, stdout=ui_log, stderr=subprocess.STDOUT)
        stack.callback(stop, streamlit)
        wait_ready(streamlit, f'http://127.0.0.1:{ui_port}/_stcore/health')
        api = APIClient(base)
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
        previous_api_url = os.environ.get('API_URL')
        os.environ['API_URL'] = base
        try:
            ui = AppTest.from_file(ROOT / 'frontend/app.py', default_timeout=30).run()

            def element(kind, label):
                return next(item for item in getattr(ui, kind) if item.label == label)

            def healthy():
                assert not ui.exception, str(ui.exception)
                assert not ui.error, str(ui.error)

            healthy()
            element('selectbox', 'Попробовать сценарий').set_value(QUERY).run()
            element('checkbox', 'Учитывать симулированные ответы отельера').set_value(True)
            element('button', 'Найти отели').click().run()
            healthy()
            assert not ui.session_state['response']['matched']
            element('selectbox', 'Отель').set_value(hotel['id']).run()
            element('selectbox', 'О чём спросить').set_value(KEY).run()
            element('button', 'Сформировать вопрос').click().run()
            qid = ui.session_state['owner_question_id']

            def submit(text):
                element('text_area', 'Ответ своими словами').set_value(text)
                element('button', 'Разобрать ответ').click().run()
                healthy()
                answer = dict(ui.session_state['pending_answer'])
                assert answer['status'] == 'pending'
                return answer

            positive = submit('В номере 501 есть плотные шторы.')
            assert not api.post('/api/search', {'text': QUERY, 'include_simulated': True})['matched']
            element('button', 'Подтвердить разбор').click().run()
            healthy()
            assert len(ui.session_state['response']['matched']) == 1
            confirmation = api.post(f'/api/hotelier/answers/{positive["id"]}/confirm', {'accept': True})
            assert confirmation['idempotent'] and len(confirmation['observation_ids']) == 1
            selected = confirmation['observation_ids'][0]
            assert not api.post('/api/search', {'text': QUERY})['matched']

            submit('В номере 501 нет плотных штор.')
            element('button', 'Подтвердить разбор').click().run()
            healthy()
            assert not ui.session_state['response']['matched']
            question = next(q for q in api.get('/api/hotelier/questions') if q['id'] == qid)
            assert question['status'] == 'open' and 'conflicted' in question['context']['reasons']
            conflict = api.get('/api/hotelier/conflicts?hotel_id=' + hotel['id'] + '&status=open')[0]
            assert element('button', 'Сохранить решение').disabled
            element('radio', 'Какую версию сохранить?').set_value(selected).run()
            assert element('button', 'Сохранить решение').disabled
            reason = 'Приёмка: выбран исходный ответ о номере 501'
            element('text_area', 'Почему выбрана эта версия?').set_value(reason).run()
            element('button', 'Сохранить решение').click().run()
            healthy()
            assert len(ui.session_state['response']['matched']) == 1
            assert any('Подбор обновлён с прежними условиями' in msg.value for msg in ui.success)
            report['ui_flow'] = {'unknown_matches': 0, 'pending_matches': 0,
                'confirmed_matches': 1, 'conflicted_matches': 0, 'resolved_matches': 1,
                'explicit_selection_and_reason_required': True, 'automatic_search_refresh': True}
        finally:
            if previous_api_url is None:
                os.environ.pop('API_URL', None)
            else:
                os.environ['API_URL'] = previous_api_url

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
                      streamlit_health='ok', browser_visual_check='not performed; AppTest checks behavior only',
                      both_ranking_methods='passed', status='passed')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('PASS:', output, flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime/backend_acceptance.json')
    verify(parser.parse_args().output)
