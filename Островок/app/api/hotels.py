from fastapi import APIRouter, Depends, Request
from app.api.dependencies import repository
from app.features.registry import get_registry
from app.features.service import resolve_feature

router = APIRouter(prefix='/api',tags=['hotels'])


@router.get('/hotels')
def hotels(repo=Depends(repository)):
    return repo.hotels()


@router.get('/hotels/{hotel_id}')
def hotel(hotel_id:str,repo=Depends(repository)):
    return {'hotel':repo.hotel(hotel_id),'observations':repo.observations(hotel_id),
            'conflicts':repo.conflicts(hotel_id)}


@router.get('/hotels/{hotel_id}/evidence')
def evidence(hotel_id:str,repo=Depends(repository)):
    repo.hotel(hotel_id)
    observations = repo.observations(hotel_id)
    subjects = sorted({(x.subject_id,x.feature_key) for x in observations})
    return {'observations':observations,'conflicts':repo.conflicts(hotel_id),
            'current_real':[resolve_feature(observations,s,k) for s,k in subjects],
            'current_demo':[resolve_feature(observations,s,k,True) for s,k in subjects]}


@router.get('/features')
def features():
    return get_registry().definitions


@router.get('/demo-queries')
def examples(request:Request):
    from app.ml.query_parser import FixtureQueryParser
    return [r['text'] for r in FixtureQueryParser().examples]
