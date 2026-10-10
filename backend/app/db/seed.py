"""Demo data Seeder:  python -m app.db.seed   (idempotent)."""
from __future__ import annotations

import logging
import random
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import Tenant, User
from app.db.session import get_engine, system_session
from app.services import generators as g
from app.services.audit import append_audit

log = logging.getLogger("nexus.seed")

TENANTS = [
    ("Acme Fintech", "acme-fintech", "fintech", [("ciso@acme-fintech.example", "Dana Whitfield", "owner"), ("analyst@acme-fintech.example", "Luis Ortega", "analyst"), ("viewer@acme-fintech.example", "Priya Nair", "viewer")]),
    ("Helix Health", "helix-health", "health", [("ciso@helix-health.example", "Marta Keller", "owner"), ("analyst@helix-health.example", "Tomás Rivera", "analyst")]),
]


def seed(days: int = 30) -> str:
    s = get_settings()
    if s.is_production and not s.seed_demo_password:
        raise RuntimeError("Refusing to seed demo data in production without SEED_DEMO_PASSWORD")
    password = s.seed_demo_password or secrets.token_urlsafe(14)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    with system_session() as db:
        for name, slug, domain, users in TENANTS:
            if db.scalars(select(Tenant).where(Tenant.slug == slug)).first():
                log.info("Tenant %s already seeded", slug)
                continue
            rng = random.Random(slug)  # deterministic demo data
            tenant = Tenant(name=name, slug=slug)
            db.add(tenant)
            db.flush()
            tid = tenant.id
            pw_hash = hash_password(password)
            for email, full, role in users:
                db.add(User(tenant_id=tid, email=email, full_name=full, role=role, password_hash=pw_hash))
            db.add_all(g.make_endpoints(rng, tid, domain))
            for _ in range(38):
                db.add(g.make_finding(rng, tid, domain, now - timedelta(hours=rng.randint(1, days * 24))))
            for h in range(days * 24):
                ts = now - timedelta(hours=h)
                for cluster, namespaces in g.CLUSTERS:
                    db.add(g.make_finops_sample(rng, tid, ts, cluster, rng.choice(namespaces)))
            for _ in range(60):
                db.add(g.make_rag_query(rng, tid, domain, now - timedelta(minutes=rng.randint(1, days * 24 * 60))))
            append_audit(db, tid, "tenant.seeded", meta={"source": "seeder"})
            log.info("Seeded tenant %s", slug)
        db.commit()
    return password


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.db.bootstrap import apply_schema
    from sqlalchemy import create_engine

    st = get_settings()
    apply_schema(create_engine(st.database_admin_url) if st.database_admin_url else get_engine())
    pw = seed()
    users = ", ".join(u[0] for t in TENANTS for u in t[3][:2])
    if get_settings().seed_demo_password:
        print(f"\nDemo data ready. Demo users: {users} (password = SEED_DEMO_PASSWORD)\n")
    else:
        print(f"\nDemo users: {users}\nGenerated demo password (shown once): {pw}\n")


if __name__ == "__main__":
    main()
