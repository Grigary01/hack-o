"""Хранение и идемпотентные операции. Транзакцией владеет вызывающий сервис/API."""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from app.schemas.hotel import Hotel, Observation
from app.schemas.conflicts import Conflict, ConflictResolution, ResolveConflictRequest
from app.schemas.hotelier import QuestionContext
from app.core.errors import StateConflictError, NotFoundError
from app.storage.models import (HotelRow, RoomRow, SourceRow, FeatureDefinitionRow,
    ObservationRow, EvidenceRow, ConflictRow, ConflictResolutionRow, QuestionRow, AnswerRow)


def now_utc():
    return datetime.now(timezone.utc)


def row_dict(row):
    return {c.name:getattr(row,c.name) for c in row.__table__.columns}


class Repository:
    def __init__(self, session):
        self.session = session

    def hotels(self):
        return [Hotel.model_validate(x.payload) for x in self.session.scalars(select(HotelRow).order_by(HotelRow.id))]

    def hotel(self, hotel_id):
        row = self.session.get(HotelRow,hotel_id)
        if row is None:
            raise NotFoundError('Отель не найден')
        return Hotel.model_validate(row.payload)

    def save_hotel(self, hotel):
        self.session.merge(HotelRow(id=hotel.id,payload=hotel.model_dump(mode='json')))
        self.session.flush()

    def save_definitions(self, registry):
        for key,definition in registry.definitions.items():
            self.session.merge(FeatureDefinitionRow(key=key,payload=definition.model_dump(mode='json')))
        self.session.flush()

    def observations(self, hotel_id, feature_key=None):
        query = select(ObservationRow).where(ObservationRow.hotel_id == hotel_id)
        if feature_key:
            query = query.where(ObservationRow.feature_key == feature_key)
        return [Observation.model_validate(x.payload) for x in self.session.scalars(query)]

    def save_observation(self, observation):
        self.hotel(observation.hotel_id)
        if self.session.get(ObservationRow, observation.id):
            return observation.id
        previous = self.observations(observation.hotel_id, observation.feature_key)
        source = observation.evidence.source.model_dump(mode='json')
        source_id = hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
        self.session.execute(insert(SourceRow).values(id=source_id,payload=source).on_conflict_do_nothing())
        self.session.add(ObservationRow(id=observation.id,hotel_id=observation.hotel_id,
            subject_id=observation.subject_id,feature_key=observation.feature_key,
            payload=observation.model_dump(mode='json')))
        self.session.flush()
        self.session.add(EvidenceRow(observation_id=observation.id,source_id=source_id,
                                    payload=observation.evidence.model_dump(mode='json')))
        for old in previous:
            overlap = max(old.observed_at,observation.observed_at) < min(old.expires_at,observation.expires_at)
            # Симулированное сообщение не создаёт конфликт с реальным источником.
            same_world = (old.evidence.source.type == 'hotelier_simulated') == (observation.evidence.source.type == 'hotelier_simulated')
            from app.features.service import supersedes
            refresh = supersedes(observation, old) or supersedes(old, observation)
            # Решение оператора само разрешает конфликт и новых не создаёт.
            refresh = refresh or 'operator_decision' in (old.evidence.source.type, observation.evidence.source.type)
            if (old.subject_id == observation.subject_id and overlap and same_world and not refresh and
                old.value is not None and observation.value is not None and old.value != observation.value):
                ids = sorted([old.id,observation.id])
                conflict_id = hashlib.sha256('|'.join(ids).encode()).hexdigest()
                self.session.execute(insert(ConflictRow).values(id=conflict_id,hotel_id=observation.hotel_id,
                    subject_id=observation.subject_id,feature_key=observation.feature_key,
                    left_id=ids[0],right_id=ids[1],created_at=now_utc().isoformat(),
                    policy='withhold_and_ask_hotelier').on_conflict_do_nothing())
        self.session.flush()
        self.refresh_existing_question(observation.hotel_id, observation.feature_key)
        return observation.id

    def add_review_conflict(self, hotel_id, subject_id, feature_key, left_id, right_id, reason):
        """Расхождение разных источников (отельер против расчёта): значение не скрывается,
        конфликт виден в кабинете с политикой review:<причина>."""
        ids = sorted([left_id, right_id])
        conflict_id = hashlib.sha256(('|'.join(ids) + '|' + reason).encode()).hexdigest()
        self.session.execute(insert(ConflictRow).values(id=conflict_id, hotel_id=hotel_id, subject_id=subject_id,
            feature_key=feature_key, left_id=ids[0], right_id=ids[1], created_at=now_utc().isoformat(),
            policy='review:' + reason).on_conflict_do_nothing())
        self.session.flush()
        return conflict_id

    def conflict_records(self, hotel_id=None, status=None):
        query = select(ConflictRow, ConflictResolutionRow).outerjoin(
            ConflictResolutionRow, ConflictResolutionRow.conflict_id == ConflictRow.id)
        if hotel_id:
            query = query.where(ConflictRow.hotel_id==hotel_id)
        if status == 'open':
            query = query.where(ConflictResolutionRow.conflict_id.is_(None))
        elif status == 'resolved':
            query = query.where(ConflictResolutionRow.conflict_id.is_not(None))
        return [Conflict.model_validate(row_dict(conflict) | {
            'status': 'resolved' if resolution else 'open',
            'resolution': row_dict(resolution) if resolution else None,
        }) for conflict, resolution in self.session.execute(query.order_by(ConflictRow.id))]

    def conflicts(self, hotel_id=None):
        # Старые поля сохраняются; status/resolution добавлены совместимо с UI.
        return [c.model_dump(mode='json') for c in self.conflict_records(hotel_id)]

    def conflict_details(self, hotel_id=None, status=None):
        records = self.conflict_records(hotel_id, status)
        ids = {oid for c in records for oid in (c.left_id, c.right_id)}
        observations = {row.id: row.payload for row in self.session.scalars(
            select(ObservationRow).where(ObservationRow.id.in_(ids)))} if ids else {}
        return [c.model_dump() | {'left_observation': observations[c.left_id],
                                 'right_observation': observations[c.right_id]} for c in records]

    def resolve_conflict(self, conflict_id, selected_observation_id, reason, operator_id='demo_operator'):
        payload = ResolveConflictRequest(selected_observation_id=selected_observation_id, reason=reason)
        conflict = self.session.get(ConflictRow, conflict_id)
        if conflict is None:
            raise NotFoundError('Конфликт не найден')
        selected = self.session.get(ObservationRow, payload.selected_observation_id)
        if selected is None:
            raise NotFoundError('Наблюдение не найдено')
        # review:* — расхождение разных источников (номер против расчёта по зданию):
        # стороны могут относиться к разным субъектам и признакам, но к одному отелю.
        review = conflict.policy.startswith('review:')
        expected = (conflict.hotel_id,) if review else (conflict.hotel_id, conflict.subject_id, conflict.feature_key)
        actual = (selected.hotel_id,) if review else (selected.hotel_id, selected.subject_id, selected.feature_key)
        if selected.id not in (conflict.left_id, conflict.right_id) or actual != expected:
            raise ValueError('Наблюдение не принадлежит этому конфликту, отелю, номеру и характеристике')
        # Проверяем и payload: нельзя применить решение к несовместимому факту.
        fact = Observation.model_validate(selected.payload)
        if (fact.id, fact.hotel_id, fact.subject_id, fact.feature_key) != (
                selected.id, selected.hotel_id, selected.subject_id, selected.feature_key):
            raise ValueError('Свидетельство не соответствует записи наблюдения')
        result = self.session.execute(insert(ConflictResolutionRow).values(
            conflict_id=conflict_id, selected_observation_id=payload.selected_observation_id,
            reason=payload.reason, resolved_at=now_utc().isoformat(), operator_id=operator_id,
        ).on_conflict_do_nothing(index_elements=['conflict_id']))
        self.session.flush()
        resolution = self.session.get(ConflictResolutionRow, conflict_id)
        if (resolution.selected_observation_id, resolution.reason) != (
                payload.selected_observation_id, payload.reason):
            raise StateConflictError('Конфликт уже решён иначе; изменение решения не поддерживается')
        self.refresh_existing_question(conflict.hotel_id, conflict.feature_key)
        return ConflictResolution.model_validate(row_dict(resolution)), result.rowcount == 0

    def conflict(self, conflict_id):
        row = self.session.get(ConflictRow, conflict_id)
        if row is None:
            raise NotFoundError('Конфликт не найден')
        return row_dict(row)

    def conflict_resolution(self, conflict_id):
        row = self.session.get(ConflictResolutionRow, conflict_id)
        return None if row is None else ConflictResolution.model_validate(row_dict(row))

    def observation(self, observation_id):
        row = self.session.get(ObservationRow, observation_id)
        if row is None:
            raise NotFoundError('Свидетельство не найдено')
        return Observation.model_validate(row.payload)

    def ensure_question(self, hotel_id, feature_key, text):
        self.hotel(hotel_id)
        qid = hashlib.sha256(f'{hotel_id}|{feature_key}'.encode()).hexdigest()[:24]
        now = now_utc().isoformat()
        self.session.execute(insert(QuestionRow).values(id=qid,hotel_id=hotel_id,feature_key=feature_key,
            text=text,status='open',created_at=now,updated_at=now,
            context=QuestionContext(reasons=['unknown']).model_dump()).on_conflict_do_nothing())
        from app.hotelier.questions import refresh_question
        return refresh_question(self, self.question(qid))

    def refresh_existing_question(self, hotel_id, feature_key):
        # Геофакты не создают и не открывают вопрос отельеру.
        from app.features.registry import get_registry
        if get_registry().get(feature_key).provider != 'hotelier':
            return None
        question = self.session.scalar(select(QuestionRow).where(
            QuestionRow.hotel_id == hotel_id, QuestionRow.feature_key == feature_key))
        if question is not None:
            from app.hotelier.questions import refresh_question
            return refresh_question(self, question)
        return None

    def question(self, qid):
        row = self.session.get(QuestionRow,qid)
        if row is None:
            raise NotFoundError('Вопрос не найден')
        return row

    def answer(self, aid):
        row = self.session.get(AnswerRow,aid)
        if row is None:
            raise NotFoundError('Ответ не найден')
        return row

    def questions(self, hotel_id=None, status=None):
        from app.hotelier.questions import refresh_question
        query = select(QuestionRow)
        if hotel_id is not None:
            self.hotel(hotel_id)
            query = query.where(QuestionRow.hotel_id == hotel_id)
        rows = list(self.session.scalars(query.order_by(QuestionRow.created_at, QuestionRow.id)))
        # TTL может истечь без записи в БД. Сначала пересчитываем состояние,
        # затем фильтруем: answered-вопрос должен попасть в status=open после TTL.
        for question in rows:
            refresh_question(self, question)
        return [row_dict(q) for q in rows if status is None or q.status == status]
