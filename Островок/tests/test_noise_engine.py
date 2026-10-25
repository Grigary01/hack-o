"""Опциональный настоящий запуск Java. Данные синтетические, не Адлер.

ADLER_TEST_NM_HOME=/.../NoiseModelling_without_gui-5.0.1
ADLER_TEST_JAVA_HOME=/.../java/Contents/Home pytest -s tests/test_noise_engine.py
"""
import os
import pytest
from app.environment.noise import prepare_scene, run_noisemodelling
from app.geo.geometry import PROJECT, UNPROJECT
from test_environment import HOTEL, synthetic_snapshot


@pytest.mark.skipif(not os.getenv('ADLER_TEST_NM_HOME'), reason='Внешний NoiseModelling не настроен; см. docs/ENVIRONMENT.md')
def test_real_engine_day_night_and_building_shielding(tmp_path):
    snapshot=synthetic_snapshot()
    def run(data):
        report,scene=prepare_scene(HOTEL,data,scenario=True)
        return run_noisemodelling(report,scene,os.environ['ADLER_TEST_NM_HOME'],
                                 os.getenv('ADLER_TEST_JAVA_HOME'),tmp_path)
    original=run(snapshot)
    lookup={(v['receiver_id'],v['period']):v['laeq_db'] for v in original['levels']}
    # В тестовом потоке днём машин ровно в 10 раз больше: +10 дБ по энергии.
    for r in original['receivers']:
        assert lookup[r['pk'],'D']-lookup[r['pk'],'N']==pytest.approx(10,abs=.01)
    x,y=PROJECT(HOTEL.lon,HOTEL.lat)
    coords=[dict(zip(('lon','lat'),UNPROJECT(x+dx,y+dy)))
            for dx,dy in [(-30,-25),(30,-25),(30,-20),(-30,-20),(-30,-25)]]
    snapshot['elements'].append(dict(type='way',id=3,tags={'building':'yes','height':'9'},geometry=coords))
    shielded=run(snapshot)
    protected={(v['receiver_id'],v['period']):v['laeq_db'] for v in shielded['levels']}
    south=[r for r in original['receivers'] if 179 < r['azimuth'] < 181]
    assert south
    reductions=[lookup[r['pk'],'D']-protected[r['pk'],'D'] for r in south]
    assert min(reductions)>1
    print({'scenario':'synthetic only','day_night_difference_db':10,
           'shielding_reduction_db':reductions,'receiver_count':len(original['receivers'])})
