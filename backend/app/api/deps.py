from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import Principal, client_ip
from app.db.session import tenant_session


def get_principal(request: Request) -> Principal:
    p = getattr(request.state, "principal", None)
    if p is None:  # AuthMiddleware must have run; fail closed otherwise
        raise HTTPException(status_code=401, detail="Not authenticated")
    return p


def get_db(principal: Principal = Depends(get_principal)) -> Iterator[Session]:
    """Tenant-bound session: the tenant comes only from the verified JWT claim."""
    db = tenant_session(principal.tenant_id)
    try:
        yield db
    finally:
        db.close()


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    def dep(p: Principal = Depends(get_principal)) -> Principal:
        if p.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return p

    return dep


def ip_of(request: Request) -> str:
    return client_ip(request)
