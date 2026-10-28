from fastapi import APIRouter, Depends, Request
from dataclasses import asdict
from app.api.dependencies import repository
from app.features.registry import get_registry, FeatureDefinition
from app.features.service import resolve_feature
from app.schemas.hotel import Hotel
from app.schemas.hotel_views import HotelDetail, HotelEvidence
from app.schemas.errors import ERROR_RESPONSES

router = APIRouter(prefix='/api',tags=['hotels'], responses=ERROR_RESPONSES)


@router.get('/hotels', response_model=list[Hotel])
def hotels(repo=Depends(repository)):
    return repo.hotels()


@router.get('/hotels/{hotel_id}', response_model=HotelDetail)
def hotel(hotel_id:str,repo=Depends(repository)):
    return {'hotel':repo.hotel(hotel_id),'observations':repo.observations(hotel_id),
            'conflicts':repo.conflicts(hotel_id)}


@router.get('/hotels/{hotel_id}/evidence', response_model=HotelEvidence)
def evidence(hotel_id:str,repo=Depends(repository)):
    repo.hotel(hotel_id)
    observations = repo.observations(hotel_id)
    conflicts = repo.conflict_records(hotel_id)
    subjects = sorted({(x.subject_id,x.feature_key) for x in observations})
    return {'observations':observations,'conflicts':repo.conflicts(hotel_id),
            'current_real':[asdict(resolve_feature(observations,s,k,conflicts=conflicts)) for s,k in subjects],
            'current_demo':[asdict(resolve_feature(observations,s,k,True,conflicts=conflicts)) for s,k in subjects]}


@router.get('/features', response_model=dict[str, FeatureDefinition])
def features():
    return get_registry().definitions


@router.get('/demo-queries', response_model=list[str])
def examples(request:Request):
    from app.ml.query_parser import FixtureQueryParser
    return [r['text'] for r in FixtureQueryParser().examples]
