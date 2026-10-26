"""Онлайн-обращение происходит только по отдельной кнопке POST, никогда в поиске."""
from fastapi import APIRouter, Depends, Request
from app.api.dependencies import repository
from app.environment.air_quality import OpenAQProvider
from app.environment.service import latest_reports, save_report

router = APIRouter(prefix='/api/hotels', tags=['environment'])


@router.get('/{hotel_id}/environment')
def environment(hotel_id: str, repo=Depends(repository)):
    return latest_reports(repo, hotel_id)


@router.post('/{hotel_id}/environment/air-quality/refresh')
def refresh_air(hotel_id: str, request: Request, repo=Depends(repository)):
    hotel = repo.hotel(hotel_id)
    provider = OpenAQProvider(request.app.state.config.openaq_api_key)
    report = provider.collect(hotel)
    save_report(repo, report)
    return report
