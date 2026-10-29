"""Таблицы разделены по ответственности; payload хранит проверенный Pydantic DTO.

JSON сохраняет полный контракт свидетельств. Индексируемые поля вынесены
в колонки. Версии схемы и миграции находятся в migrations/.
"""
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class HotelRow(Base):
    __tablename__ = 'hotels'
    id: Mapped[str] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class RoomRow(Base):
    __tablename__ = 'rooms'
    id: Mapped[str] = mapped_column(primary_key=True)
    hotel_id: Mapped[str] = mapped_column(ForeignKey('hotels.id'), index=True)
    number: Mapped[str]
    floor: Mapped[int | None]


class SourceRow(Base):
    __tablename__ = 'sources'
    id: Mapped[str] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class FeatureDefinitionRow(Base):
    __tablename__ = 'feature_definitions'
    key: Mapped[str] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ObservationRow(Base):
    __tablename__ = 'observations'
    id: Mapped[str] = mapped_column(primary_key=True)
    hotel_id: Mapped[str] = mapped_column(ForeignKey('hotels.id'), index=True)
    subject_id: Mapped[str] = mapped_column(index=True)
    feature_key: Mapped[str] = mapped_column(index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class EvidenceRow(Base):
    __tablename__ = 'evidence'
    observation_id: Mapped[str] = mapped_column(ForeignKey('observations.id'), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('sources.id'))
    payload: Mapped[dict] = mapped_column(JSON)


class ConflictRow(Base):
    __tablename__ = 'conflicts'
    id: Mapped[str] = mapped_column(primary_key=True)
    hotel_id: Mapped[str] = mapped_column(ForeignKey('hotels.id'), index=True)
    subject_id: Mapped[str]
    feature_key: Mapped[str]
    left_id: Mapped[str] = mapped_column(ForeignKey('observations.id'))
    right_id: Mapped[str] = mapped_column(ForeignKey('observations.id'))
    created_at: Mapped[str]
    policy: Mapped[str] = mapped_column(default='withhold_and_ask_hotelier')


class ConflictResolutionRow(Base):
    __tablename__ = 'conflict_resolutions'
    conflict_id: Mapped[str] = mapped_column(ForeignKey('conflicts.id'), primary_key=True)
    selected_observation_id: Mapped[str] = mapped_column(ForeignKey('observations.id'))
    reason: Mapped[str]
    resolved_at: Mapped[str]
    operator_id: Mapped[str]


class QuestionRow(Base):
    __tablename__ = 'hotelier_questions'
    __table_args__ = (UniqueConstraint('hotel_id','feature_key'),)
    id: Mapped[str] = mapped_column(primary_key=True)
    hotel_id: Mapped[str] = mapped_column(ForeignKey('hotels.id'), index=True)
    feature_key: Mapped[str]
    text: Mapped[str]
    status: Mapped[str] = mapped_column(default='open')
    created_at: Mapped[str]
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[str]


class AnswerRow(Base):
    __tablename__ = 'hotelier_answers'
    id: Mapped[str] = mapped_column(primary_key=True)
    question_id: Mapped[str] = mapped_column(ForeignKey('hotelier_questions.id'))
    text: Mapped[str]
    extraction: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default='pending')
    simulated: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[str]


class EnvironmentReportRow(Base):
    """История региональных измерений и сценариев; не смешивается с фактами номера."""
    __tablename__ = 'environment_reports'
    id: Mapped[str] = mapped_column(primary_key=True)
    hotel_id: Mapped[str] = mapped_column(ForeignKey('hotels.id'), index=True)
    kind: Mapped[str] = mapped_column(index=True)
    collected_at: Mapped[str] = mapped_column(index=True)
    payload: Mapped[dict] = mapped_column(JSON)
