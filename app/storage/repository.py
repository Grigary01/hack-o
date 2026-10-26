"""Хранение и идемпотентные операции. Транзакцией владеет вызывающий сервис/API."""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from app.schemas.hotel import Hotel, Observation
from app.storage.models import (HotelRow, RoomRow, SourceRow, FeatureDefinitionRow,
    ObservationRow, EvidenceRow, ConflictRow, QuestionRow, AnswerRow)


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
            raise LookupError('Отель не найден')
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
            if (old.subject_id == observation.subject_id and overlap and same_world and
                old.value is not None and observation.value is not None and old.value != observation.value):
                ids = sorted([old.id,observation.id])
                conflict_id = hashlib.sha256('|'.join(ids).encode()).hexdigest()
                self.session.execute(insert(ConflictRow).values(id=conflict_id,hotel_id=observation.hotel_id,
                    subject_id=observation.subject_id,feature_key=observation.feature_key,
                    left_id=ids[0],right_id=ids[1],created_at=now_utc().isoformat(),
                    policy='withhold_and_ask_hotelier').on_conflict_do_nothing())
        self.session.flush()
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

    def conflicts(self, hotel_id=None):
        query = select(ConflictRow)
        if hotel_id:
            query = query.where(ConflictRow.hotel_id==hotel_id)
        return [row_dict(r) for r in self.session.scalars(query)]

    def ensure_question(self, hotel_id, feature_key, text):
        self.hotel(hotel_id)
        qid = hashlib.sha256(f'{hotel_id}|{feature_key}'.encode()).hexdigest()[:24]
        self.session.execute(insert(QuestionRow).values(id=qid,hotel_id=hotel_id,feature_key=feature_key,
            text=text,status='open',created_at=now_utc().isoformat()).on_conflict_do_nothing())
        return self.question(qid)

    def question(self, qid):
        row = self.session.get(QuestionRow,qid)
        if row is None:
            raise LookupError('Вопрос не найден')
        return row

    def answer(self, aid):
        row = self.session.get(AnswerRow,aid)
        if row is None:
            raise LookupError('Ответ не найден')
        return row

    def questions(self):
        return [row_dict(q) for q in self.session.scalars(select(QuestionRow).order_by(QuestionRow.created_at))]
