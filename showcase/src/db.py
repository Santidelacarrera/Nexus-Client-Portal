"""Acceso a PostgreSQL 16 con SQLAlchemy 2.0 asíncrono + asyncpg.

* Solo consultas parametrizadas (Core/ORM; asyncpg usa prepared statements): no hay SQL construido con strings.
* RLS: cada transacción fija `app.session_id` con set_config(..., is_local=true) y la base de datos decide qué filas
  puede ver o escribir el rol `showcase_app`. Si la aplicación se equivocara, la base de datos seguiría negando.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, Text, cast, select, text, update
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.config import Settings


class Base(DeclarativeBase):
    pass


class VisitorSession(Base):
    __tablename__ = "visitor_sessions"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("visitor_sessions.id"))
    consent_key: Mapped[str] = mapped_column(Text)
    granted: Mapped[bool] = mapped_column()
    policy_version: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContactMessage(Base):
    __tablename__ = "contact_messages"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    consent_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retain_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionInvalid(Exception):
    """La sesión no existe o no es la del contexto (RLS/clave foránea lo rechazó)."""


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _bind_session(s: AsyncSession, sid: uuid.UUID) -> None:
    await s.execute(text("SELECT set_config('app.session_id', :sid, true)"), {"sid": str(sid)})


async def create_visitor_session(sm: async_sessionmaker[AsyncSession], sid: uuid.UUID, settings: Settings) -> None:
    async with sm.begin() as s:
        await _bind_session(s, sid)
        s.add(VisitorSession(id=sid, created_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.visitor_session_hours)))


async def session_exists(sm: async_sessionmaker[AsyncSession], sid: uuid.UUID) -> bool:
    async with sm.begin() as s:
        await _bind_session(s, sid)
        return (await s.execute(select(VisitorSession.id).where(VisitorSession.id == sid))).first() is not None


async def record_contact(sm: async_sessionmaker[AsyncSession], sid: uuid.UUID, *, name: str, email: str, message: str, policy_version: str) -> tuple[uuid.UUID, datetime]:
    """Una sola transacción: evidencia de consentimiento + mensaje. Si algo falla, no queda nada."""
    consent_id, message_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(timezone.utc)
    try:
        async with sm.begin() as s:
            await _bind_session(s, sid)
            s.add(ConsentRecord(id=consent_id, session_id=sid, consent_key="consentimiento_ley_21719", granted=True, policy_version=policy_version, recorded_at=now))
            await s.flush()  # la FK compuesta exige que el consentimiento exista antes que el mensaje
            s.add(ContactMessage(id=message_id, session_id=sid, consent_id=consent_id, name=name, email=email, message=message, status="nuevo", created_at=now, retain_until=now + timedelta(days=365)))
    except (IntegrityError, DBAPIError) as exc:
        raise SessionInvalid from exc
    return message_id, now


async def list_messages(sm: async_sessionmaker[AsyncSession], limit: int = 100) -> list[tuple[ContactMessage, ConsentRecord]]:
    """Solo con el rol `showcase_staff` (su política RLS permite leer todo)."""
    async with sm.begin() as s:
        rows = await s.execute(
            select(ContactMessage, ConsentRecord)
            .join(ConsentRecord, ConsentRecord.id == ContactMessage.consent_id)
            .order_by(ContactMessage.created_at.desc())
            .limit(limit)
        )
        return [(m, c) for m, c in rows.all()]


async def set_status_by_ref(sm: async_sessionmaker[AsyncSession], ref_hex: str, status: str) -> bool:
    """La referencia pública NX-XXXXXXXX son los 8 primeros hex del id. Solo cambia si coincide exactamente UNA fila."""
    async with sm.begin() as s:
        ids = (await s.execute(select(ContactMessage.id).where(cast(ContactMessage.id, Text).like(ref_hex.lower() + "%")))).scalars().all()
        if len(ids) != 1:
            return False
        await s.execute(update(ContactMessage).where(ContactMessage.id == ids[0]).values(status=status))
        return True
