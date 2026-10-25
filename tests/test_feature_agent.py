from dataclasses import replace
import pytest
import yaml
from app.core.config import settings
from app.features.registry import get_registry
from app.agent.feature_agent import FeatureAgent
from app.agent.tool_registry import ToolRegistry,ToolSpec
from app.hotelier.dialogue import parse_hotelier_reply


def test_planner_selects_existing_evidence_and_hotelier(repo):
    h=repo.hotels()[0]
    agent=FeatureAgent(repo)
    assert agent.ensure(h.id,'quietness_proxy')['action']=='read_evidence'
    assert agent.ensure(h.id,'sea_view')['tool_used']=='hotelier'
    agent.ensure(h.id,'sea_view')
    assert len(repo.questions())==1
    assert len(agent.trace)==3


def test_registry_whitelist_budget_and_types():
    tools=ToolRegistry([ToolSpec('known',lambda p:p.hotel_id)],max_calls=1)
    with pytest.raises(ValueError):tools.execute('__import__',{})
    assert tools.execute('known',{'hotel_id':'h','feature_key':'sea_view'})=='h'
    with pytest.raises(TimeoutError):tools.execute('known',{'hotel_id':'h','feature_key':'sea_view'})


def test_missing_geo_feature_is_calculated_and_saved(repo):
    # Синтетический subject существует только в изолированной тестовой DB.
    hotel=repo.hotels()[0].model_copy(update={'id':'test:hotel'})
    repo.save_hotel(hotel)
    decision=FeatureAgent(repo).ensure(hotel.id,'quietness_proxy')
    assert decision['tool_used']=='quietness'
    observation=repo.observations(hotel.id,'quietness_proxy')[0]
    assert observation.value in ('high','medium','low')
    assert observation.evidence.method=='noise_proxy_v1'


def test_yaml_only_room_feature_extension(repo,tmp_path,monkeypatch):
    raw=yaml.safe_load(settings.registry_path.read_text())
    raw['blackout_curtains']={'label':'Плотные шторы','description':'Утверждение отельера',
        'type':'boolean','scope':'room','provider':'hotelier','ttl_days':180,'default_weight':.5,
        'aliases':['плотные шторы'],'question':'В каких номерах есть плотные шторы?'}
    path=tmp_path/'features.yaml';path.write_text(yaml.safe_dump(raw,allow_unicode=True))
    with monkeypatch.context() as scoped:
        scoped.setattr('app.features.registry.settings',replace(settings,registry_path=path))
        get_registry.cache_clear()
        try:
            # Загрузчик должен обращаться к текущему пути конфигурации.
            assert get_registry().get('blackout_curtains').provider=='hotelier'
            h=repo.hotels()[0]
            decision=FeatureAgent(repo).ensure(h.id,'blackout_curtains')
            assert decision['tool_used']=='hotelier'
            extracted=parse_hotelier_reply('blackout_curtains','В номере 501 есть плотные шторы.')
            assert extracted.claims[0].value is True
        finally:
            get_registry.cache_clear()
