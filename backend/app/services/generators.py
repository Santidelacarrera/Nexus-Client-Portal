"""Realistic data generators shared by the Seeder and the live telemetry simulator."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.db.models import ApiEndpoint, ApiFinding, FinOpsSample, RagQuery, RagSource

DOMAINS = {
    "fintech": {
        "resources": ["accounts", "payments", "cards", "beneficiaries", "statements", "loans", "kyc/documents"],
        "docs": ["PCI-DSS-Controls-v4.pdf", "Payments-Runbook.md", "KYC-Policy-2025.pdf", "Treasury-SOP.pdf", "Fraud-Playbook.docx"],
        "questions": [
            ("What is the maximum daily limit for international wire transfers?", "The daily limit for international wires is USD 250,000 per beneficiary, subject to step-up authentication above USD 50,000."),
            ("Which controls apply when storing PAN data?", "PAN must be rendered unreadable with strong cryptography (AES-256) and access restricted by need-to-know, per PCI-DSS 3.5."),
            ("How long must KYC documents be retained after account closure?", "KYC records are retained for five years after account closure, then securely destroyed."),
            ("What triggers a manual review of a card-not-present transaction?", "A risk score above 0.82 or a mismatch between billing country and device geolocation triggers manual review."),
            ("Who approves emergency changes to the payment gateway?", "The on-call Head of Platform and the CISO delegate jointly approve emergency changes, recorded in the CAB log."),
        ],
    },
    "health": {
        "resources": ["patients", "encounters", "prescriptions", "lab-results", "appointments", "claims", "imaging"],
        "docs": ["HIPAA-Security-Rule-Map.pdf", "Clinical-Data-Retention.pdf", "Incident-Response-Plan.md", "Telehealth-Protocol-v3.pdf", "Formulary-2025.xlsx"],
        "questions": [
            ("What is the retention period for imaging studies?", "Imaging studies are retained for ten years for adults and until age 28 for pediatric patients."),
            ("Which roles may access full prescription history?", "Only licensed prescribers and pharmacists with an active treatment relationship may view full history."),
            ("How are PHI breaches escalated?", "Suspected PHI breaches are escalated to the Privacy Officer within one hour and reported under the 60-day notification rule."),
            ("What encryption applies to telehealth video sessions?", "Sessions use DTLS-SRTP with per-session keys; recordings are encrypted at rest with AES-256-GCM."),
            ("When can a claim be auto-adjudicated?", "Claims under USD 1,500 with valid eligibility and no prior-authorisation flag are auto-adjudicated."),
        ],
    },
}

CLUSTERS = [("prod-eks-us-east-1", ["checkout", "ledger", "gateway", "risk-engine"]), ("prod-gke-eu-west-1", ["identity", "reporting", "ingest", "notifier"])]
MODELS = ["nexus-rag-large-2026", "nexus-rag-fast-2026"]

FINDING_TEMPLATES = [
    ("BOLA", "high", "GET", "/api/v2/{r}/{{id}}", "Broken Object Level Authorization on {r}", "Authenticated user can read {r} owned by other principals by iterating the object identifier."),
    ("BOLA", "critical", "PUT", "/api/v1/{r}/{{id}}", "Cross-owner modification on {r}", "Write operation does not verify ownership; object ids are sequential and guessable."),
    ("IDOR", "high", "GET", "/api/v1/{r}/{{id}}/export", "IDOR in {r} export", "Export endpoint accepts a client-supplied id and returns another account's data."),
    ("IDOR", "medium", "DELETE", "/api/v1/{r}/{{id}}", "IDOR allows deletion of foreign {r}", "Deletion succeeds with a valid session for an unrelated tenant object."),
    ("Shadow API", "high", "POST", "/internal/{r}/bulk", "Undocumented bulk endpoint on {r}", "Traffic observed on an endpoint absent from the OpenAPI contract and the API gateway inventory."),
    ("Shadow API", "medium", "GET", "/v0/{r}/debug", "Legacy debug route exposed for {r}", "Deprecated v0 route still reachable from the public ingress."),
    ("Endpoint Drift", "medium", "PATCH", "/api/v3/{r}/{{id}}", "Schema drift on {r}", "Production responses contain 6 fields not present in the published schema."),
    ("Endpoint Drift", "low", "GET", "/api/v2/{r}", "Undeclared query parameter on {r}", "Endpoint honours an undeclared `include` parameter widening the response."),
    ("Excessive Data Exposure", "medium", "GET", "/api/v1/{r}/search", "Over-broad response in {r} search", "Search returns internal fields (risk flags, notes) to unprivileged roles."),
    ("Mass Assignment", "high", "POST", "/api/v2/{r}", "Mass assignment on {r}", "Unfiltered request body binds privileged attributes such as `owner_id`."),
]
SEV_CVSS = {"critical": (9.0, 9.9), "high": (7.0, 8.9), "medium": (4.0, 6.9), "low": (1.0, 3.9)}


def make_finding(rng: random.Random, tenant_id: str, domain: str, ts: datetime, *, status: str | None = None) -> ApiFinding:
    cat, sev, method, path, title, desc = rng.choice(FINDING_TEMPLATES)
    r = rng.choice(DOMAINS[domain]["resources"])
    lo, hi = SEV_CVSS[sev]
    age_days = (datetime.now(ts.tzinfo) - ts).days if ts.tzinfo else 0
    st = status or rng.choices(["open", "mitigating", "resolved"], [0.5, 0.2, 0.3] if age_days < 20 else [0.2, 0.1, 0.7])[0]
    return ApiFinding(
        tenant_id=tenant_id, category=cat, severity=sev, status=st, method=method,
        endpoint=path.format(r=r), title=title.format(r=r), description=desc.format(r=r),
        evidence={
            "request_id": f"req_{rng.getrandbits(48):012x}",
            "probe": "id-swap" if cat in ("BOLA", "IDOR") else "traffic-diff",
            "http_status": rng.choice([200, 200, 201, 204]),
            "sample_size": rng.randint(12, 480),
        },
        cvss=round(rng.uniform(lo, hi), 1), detected_at=ts,
    )


def make_endpoints(rng: random.Random, tenant_id: str, domain: str) -> list[ApiEndpoint]:
    out: list[ApiEndpoint] = []
    now = datetime.now().astimezone()
    for r in DOMAINS[domain]["resources"]:
        for method, suffix in (("GET", "/{id}"), ("POST", ""), ("PUT", "/{id}")):
            out.append(ApiEndpoint(tenant_id=tenant_id, method=method, path=f"/api/v2/{r}{suffix}", status="documented",
                                   calls_24h=rng.randint(800, 90000), last_seen=now - timedelta(seconds=rng.randint(1, 600))))
    for r in rng.sample(DOMAINS[domain]["resources"], 3):
        out.append(ApiEndpoint(tenant_id=tenant_id, method="POST", path=f"/internal/{r}/bulk", status="shadow", calls_24h=rng.randint(20, 900), last_seen=now - timedelta(minutes=rng.randint(1, 90))))
    for r in rng.sample(DOMAINS[domain]["resources"], 2):
        out.append(ApiEndpoint(tenant_id=tenant_id, method="GET", path=f"/api/v3/{r}/{{id}}", status="drift", calls_24h=rng.randint(100, 4000), last_seen=now - timedelta(minutes=rng.randint(1, 30))))
    return out


def make_finops_sample(rng: random.Random, tenant_id: str, ts: datetime, cluster: str, namespace: str) -> FinOpsSample:
    base_replicas = rng.randint(10, 22)
    # Diurnal load: business hours need more replicas; HPA scales the rest down.
    load = 0.45 + 0.4 * max(0.0, 1 - abs(ts.hour - 14) / 9) + rng.uniform(-0.05, 0.05)
    after = max(2, round(base_replicas * min(1.0, load)))
    unit = rng.uniform(0.17, 0.23)  # USD per replica-hour
    return FinOpsSample(
        tenant_id=tenant_id, ts=ts, cluster=cluster, namespace=namespace,
        baseline_cost=round(base_replicas * unit, 4), actual_cost=round(after * unit, 4),
        replicas_before=base_replicas, replicas_after=after,
    )


def make_rag_query(rng: random.Random, tenant_id: str, domain: str, ts: datetime, *, low_confidence: bool | None = None) -> RagQuery:
    d = DOMAINS[domain]
    question, answer = rng.choice(d["questions"])
    weak = rng.random() < 0.12 if low_confidence is None else low_confidence
    nli = round(rng.uniform(0.78, 0.944) if weak else rng.uniform(0.951, 0.999), 3)
    q = RagQuery(
        tenant_id=tenant_id, ts=ts, question=question, answer=answer, nli_score=nli,
        verdict="review" if nli < 0.95 else "verified", latency_ms=rng.randint(380, 2100), model=rng.choice(MODELS),
    )
    for i in range(rng.randint(2, 4)):
        start = rng.randint(1, 180)
        ent = round(nli + rng.uniform(-0.03, 0.02), 3) if i == 0 else round(rng.uniform(max(0.5, nli - 0.12), min(1.0, nli + 0.02)), 3)
        q.sources.append(RagSource(
            tenant_id=tenant_id, document=rng.choice(d["docs"]), page=rng.randint(1, 64),
            line_start=start, line_end=start + rng.randint(2, 9),
            snippet=answer.split(",")[0][:140] + "…", similarity=round(rng.uniform(0.82, 0.985), 3),
            entailment=max(0.0, min(1.0, ent)),
        ))
    return q
