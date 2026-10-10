"""Engine + tenant-scoped sessions.

Defense in depth for tenant isolation:
1. PostgreSQL RLS: each transaction starts with ``set_config('app.tenant_id', …, true)``.
2. ORM criteria: every SELECT on a ``TenantScoped`` entity is filtered by the session tenant.
3. Write guard: flushing an object that belongs to another tenant raises ``CrossTenantError``.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.core.config import get_settings
from app.db.models import TenantScoped


class TenantContextError(RuntimeError):
    """Query attempted without a tenant context."""


class CrossTenantError(RuntimeError):
    """Write attempted against another tenant's data."""


_engine: Engine | None = None
_system_engine: Engine | None = None


def _make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        kw: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url.endswith("://"):
            kw["poolclass"] = StaticPool
        return create_engine(url, **kw)
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _make_engine(get_settings().database_url)
    return _engine


def get_system_engine() -> Engine:
    """Owner-role engine for cross-tenant maintenance (seed, demo simulator). Falls back to the app
    engine when no admin URL is configured (SQLite dev/test, where there is no RLS)."""
    global _system_engine
    s = get_settings()
    if not s.database_admin_url:
        return get_engine()
    if _system_engine is None:
        _system_engine = _make_engine(s.database_admin_url)
    return _system_engine


def set_engine(engine: Engine | None) -> None:
    global _engine, _system_engine
    _engine, _system_engine = engine, None


def tenant_session(tenant_id: str) -> Session:
    if not tenant_id:
        raise TenantContextError("tenant_id required")
    return Session(get_engine(), expire_on_commit=False, info={"tenant_id": tenant_id, "system": False})


def system_session() -> Session:
    """Cross-tenant session (owner role) for seeding and the demo simulator ONLY — never request paths."""
    return Session(get_system_engine(), expire_on_commit=False, info={"tenant_id": None, "system": True})


@event.listens_for(Session, "after_begin")
def _apply_rls_context(session: Session, transaction, connection) -> None:  # noqa: ANN001
    if connection.dialect.name != "postgresql":
        return
    tid = session.info.get("tenant_id") or ""
    connection.exec_driver_sql("SELECT set_config('app.tenant_id', %s, true)", (tid,))


@event.listens_for(Session, "do_orm_execute")
def _scope_selects(state: ORMExecuteState) -> None:
    s = state.session
    if "system" not in s.info or s.info["system"] or not state.is_select:
        return
    if state.is_column_load or state.is_relationship_load:
        return
    tid = s.info.get("tenant_id")
    if not tid:
        raise TenantContextError("query without tenant context")
    state.statement = state.statement.options(
        with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == tid, include_aliases=True)
    )


@event.listens_for(Session, "before_flush")
def _guard_writes(session: Session, flush_context, instances) -> None:  # noqa: ANN001
    if session.info.get("system", True) or "system" not in session.info:
        return
    tid = session.info.get("tenant_id")
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if not isinstance(obj, TenantScoped):
            continue
        if obj in session.new and obj.tenant_id is None:
            obj.tenant_id = tid
        if obj.tenant_id != tid:
            raise CrossTenantError(f"write to tenant {obj.tenant_id!r} from tenant {tid!r} blocked")
