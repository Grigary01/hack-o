from fastapi import APIRouter, Depends, HTTPException, Request
from app.api.dependencies import repository
from app.agent.feature_agent import FeatureAgent
from app.schemas.search import ParseRequest, SearchRequest, SearchResponse
from app.schemas.query import ParsedHotelQuery
from app.ml.ranking import rank_hotels
from app.ml.companions import expand
from app.ml import needs
from app.schemas.errors import ERROR_RESPONSES

router = APIRouter(prefix='/api',tags=['search'], responses=ERROR_RESPONSES)

# Тяжёлые части расчётов (все этажи и сценарии вида, входы, все траектории, все заведения)
# в выдаче поиска не нужны: интерфейс показывает объяснение, источник и маршрут на карте.
# Полные данные остаются в /api/hotels/{id}/evidence. Ответ поиска уменьшается в разы.
HEAVY_DETAILS = {'base', 'scenarios', 'inputs', 'method', 'by_track', 'night_places', 'floors', 'node_ids'}


def slim(observation):
    details = observation.evidence.details
    if not isinstance(details, dict) or not HEAVY_DETAILS & details.keys():
        return observation
    compact = {k: v for k, v in details.items() if k not in HEAVY_DETAILS}
    compact['full_details'] = f'/api/hotels/{observation.hotel_id}/evidence'
    return observation.model_copy(update={'evidence': observation.evidence.model_copy(update={'details': compact})})


@router.post('/parse-query',response_model=ParsedHotelQuery)
def parse_query(payload: ParseRequest,request: Request):
    return request.app.state.parser.parse(payload.text)


@router.post('/search',response_model=SearchResponse)
def search(payload: SearchRequest,request: Request,repo=Depends(repository)):
    parser = request.app.state.parser
    parsed = payload.parsed.model_copy(deep=True) if payload.parsed else parser.parse(payload.text)
    # current_mode(): облачный режим мог разобрать этот запрос правилами (модель недоступна).
    mode = 'structured_input' if payload.parsed else (parser.current_mode() if hasattr(parser, 'current_mode') else parser.mode)
    # Каждая часть запроса — потребность с цитатой; ничего не теряется молча.
    parsed = needs.complete_needs(parsed)
    if parsed.region != 'Adler' or parsed.unknown_or_ambiguous or parsed.clarification_question:
        return SearchResponse(parsed=parsed,parser_mode=mode,status='needs_clarification',
                              ranking_method=payload.ranking_method,balance=payload.balance)
    if payload.include_simulated and not request.app.state.config.demo_mode:
        raise HTTPException(403,'Симуляция доступна только в DEMO_MODE')
    # Расплывчатое («вид из окна») → все варианты или выбранный гостем; без нового разбора текста.
    parsed = needs.resolve_concepts(parsed, payload.choices)
    # Расчётные спутники («вид на море» → вид из окон здания) добавляются до весов:
    # их тоже можно настроить слайдером. Повторный вызов с parsed их не дублирует.
    parsed = expand(parsed)
    preferences = {p.feature_key:p for p in parsed.soft_preferences}
    if set(payload.weights)-preferences.keys():
        raise HTTPException(422,'Вес можно менять только у распознанного мягкого предпочтения')
    for key,weight in payload.weights.items():
        if preferences[key].importance != weight:
            preferences[key].importance = weight
            preferences[key].weight_source = 'explicit'
    parsed = expand(parsed)
    hotels = repo.hotels()
    if not hotels:
        raise HTTPException(503,'База пуста. Выполните python -m scripts.seed_demo')
    agent = FeatureAgent(repo,max_calls=request.app.state.config.max_tool_calls)
    keys = sorted({x.feature_key for x in parsed.hard_constraints} |
                  {x.feature_key for x in parsed.soft_preferences if x.importance>0})
    questions = {}
    for hotel in hotels:
        for key in keys:
            decision = agent.ensure(hotel.id,key,payload.include_simulated)
            result = decision.get('result',{})
            if (decision.get('tool_used')=='hotelier' and result.get('id')
                    and result.get('status') == 'open'):
                questions.setdefault(hotel.id,[]).append(result['id'])
    groups = rank_hotels(parsed,[(h,repo.observations(h.id)) for h in hotels],payload.include_simulated,
                         payload.ranking_method,payload.balance,conflicts=repo.conflict_records())
    for rows in groups.values():
        for item in rows:
            item.pending_hotelier_question_ids = questions.get(item.hotel.id,[])
            for criterion in item.criteria:
                criterion.evidence = [slim(o) for o in criterion.evidence]
    return SearchResponse(parsed=parsed,parser_mode=mode,trace=agent.trace,
                          include_simulated=payload.include_simulated,ranking_method=payload.ranking_method,
                          balance=payload.balance,**groups)
