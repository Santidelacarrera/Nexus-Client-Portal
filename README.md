# 🔒 Nexus Client Portal

**Managed Services White-Label Dashboard** — componente de plataforma de *Nexus Security & AI Lab* (Santiago de la Carrera).

Consola B2B multi-tenant donde cada cliente audita en vivo la telemetría de seguridad (`ShadowAPI_Guard`), el ahorro de cloud (`KubeCost_Auto_HPA`), la calidad de su RAG (`ContextRAG_Engine`) y descarga informes ejecutivos **firmados digitalmente** con consenso multi-agente (`MultiAgent_Consensus`), con una pista de auditoría **append-only encadenada por hash**.

| Overview | ShadowAPI Guard | FinOps | ContextRAG |
|---|---|---|---|
| estado de servicios, posture score, consenso, topología (React Flow) | hallazgos BOLA/IDOR, shadow/drift, feed en vivo | ahorro Δ$ (Recharts) en vivo por WebSocket | inspector NLI ≥ 0.95 con coordenadas de fuente |

---

> **Integración RAG + comité de gobernanza:** pregunta → ContextRAG → panel de 3 agentes (fail-closed) → respuesta con fuentes
> autorizadas. Arquitectura, contratos y verificación en [`docs/INTEGRATION.md`](docs/INTEGRATION.md).

## Arranque rápido

```bash
cp .env.example .env            # cambia TODOS los secretos
docker compose --env-file .env -f deploy/docker-compose.yml up --build
```

* Portal: <http://localhost:3000> · API: <http://localhost:8000> (`/docs` solo si `ENVIRONMENT != production`)
* Usuarios demo (contraseña = `SEED_DEMO_PASSWORD`, por defecto la de `.env.example`):
  `ciso@acme-fintech.example` (owner), `analyst@acme-fintech.example`, `viewer@acme-fintech.example`, `ciso@helix-health.example` (otro tenant).
* El primer arranque genera las claves (JWT RS256, firma de informes, AES, HMAC) en el volumen `keys`, aplica esquema + RLS y siembra datos demo.

### Desarrollo local sin Docker

```bash
# backend (SQLite por defecto, sin RLS real; simulador en vivo)
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
SEED_DEMO_PASSWORD='Dev-Password-123!' TELEMETRY_SIMULATOR=1 python -m app.db.seed
TELEMETRY_SIMULATOR=1 uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm ci && BACKEND_URL=http://localhost:8000 PUBLIC_WS_URL=ws://localhost:8000 npm run dev
```

---

## Arquitectura

```
 Browser ──HTTPS──► Next.js 14 (App Router, BFF)            CSP con nonce por request
                    │  cookie httpOnly SameSite=Strict (JWT)  ← el token nunca toca JS
                    │  /api/backend/*  (allow-list + check Origin)
                    ▼
            FastAPI (control plane)  ◄──── HMAC-SHA256 webhooks ──── agentes Nexus
            AuthMiddleware → RateLimit → Headers/CSP
                    │                         │ publish
        SQLAlchemy 2 (sesión por tenant)      ▼
                    │               Redis (Pub/Sub, rate-limit, tickets WS)
                    ▼                         │ subscribe(tenant del JWT)
            PostgreSQL 16 + RLS               ▼
                                     WS /ws/telemetry  ──► navegador (ticket de un solo uso)
```

```
backend/app/
  core/    config · keys · crypto (AES-GCM, RSA-PSS, HMAC) · security (JWT, Argon2id, CSP, rate-limit, auth middleware) · store
  db/      models (RLS) · session (aislamiento por tenant) · bootstrap (DDL RLS/triggers) · seed
  api/routes/  auth · overview · security · finops · rag · reports · audit · webhooks · ws
  services/    reports (firma/cifrado) · audit (cadena hash) · bus (Redis/memoria) · generators · simulator
frontend/  app/(dashboard)/{overview,security,finops,ai-rag,reports} · components/ui · lib · middleware.ts
deploy/    docker-compose.yml · postgres/init-roles.sh
```

---

## Modelo de seguridad (lo que realmente está implementado)

| Control | Implementación | Dónde |
|---|---|---|
| Aislamiento por tenant — **3 capas** | (1) **RLS** `ENABLE`+`FORCE` con política `tenant_id = current_setting('app.tenant_id')` y `WITH CHECK`; fail-closed si no hay tenant. (2) Filtro ORM global (`with_loader_criteria`) en todo SELECT. (3) Guard en `before_flush` contra escrituras cross-tenant. El tenant sale **solo** del claim `tid` del JWT verificado | `db/bootstrap.py`, `db/session.py` |
| El rol de la app **no puede cruzar tenants** | las políticas RLS **no tienen cláusula de bypass**: ni con SQL arbitrario ni forzando variables de sesión el rol `nexus_app` ve otro tenant (test dedicado). El login usa una función `SECURITY DEFINER` (`nexus_auth_user`) que devuelve una sola fila por email exacto; el seeder/simulador usan el rol owner | `db/bootstrap.py`, `api/routes/auth.py` |
| La app **no** es superusuario | rol `nexus_app` `NOSUPERUSER NOBYPASSRLS` (un superusuario saltaría RLS aun con `FORCE`). El esquema lo aplica otro rol (`DATABASE_ADMIN_URL`) | `deploy/postgres/init-roles.sh` |
| JWT **RS256**, vida 15 min | algoritmo fijado (sin `none`/confusión HS256), `iss`/`aud`/`exp`/`jti` obligatorios | `core/security.py` |
| Contraseñas **Argon2id** | + verificación ficticia para usuarios inexistentes (anti-enumeración por tiempo) | `core/security.py` |
| Middleware de autenticación | rechaza todo `/api/*` sin `Authorization: Bearer` válido (401) | `core/security.py` |
| Rate-limit IP + tenant + login | Redis (ventana fija); respaldo en memoria si Redis cae | `core/security.py`, `core/store.py` |
| CSP **sin `unsafe-inline`** | API: `default-src 'none'`. Web: nonce por request + `strict-dynamic`; scripts y hojas de estilo sin inline. Única concesión: `style-src-attr 'unsafe-inline'` (atributos `style` que usan Recharts/React Flow; no ejecutan script) | `middleware.ts`, `core/security.py` |
| Cifrado en reposo | **AES-256-GCM**, clave por tenant derivada con HKDF, AAD = `tenant|report_id` (un blob movido a otro tenant/registro no descifra) | `core/crypto.py` |
| Firma de informes | **RSA-PSS/SHA-256** a nombre de *Santiago de la Carrera — Nexus Security & AI Lab*, JSON canónico; clave pública verificable offline (`GET /reports/public-key`) | `services/reports.py` |
| Auditoría inmutable | cadena `entry_hash = SHA256(prev_hash ‖ entrada)` por tenant + en PostgreSQL trigger que prohíbe `UPDATE/DELETE/TRUNCATE` y `REVOKE` al rol de la app; `GET /audit/verify` detecta manipulación | `services/audit.py`, `db/bootstrap.py` |
| Webhooks de agentes | **HMAC-SHA256** con clave por tenant sobre `timestamp.body`, comparación en tiempo constante, ventana anti-replay de 5 min | `api/routes/webhooks.py` |
| WebSocket | ticket JWT de 30 s con `aud=nexus-ws`, **un solo uso**, comprobación de `Origin`; el canal se deriva del tenant verificado (no hay forma de suscribirse a otro) | `api/routes/ws.py` |
| BFF / CSRF | cookie `httpOnly; SameSite=Strict; Secure` (prod) + verificación `Origin` en mutaciones + allow-list de rutas | `frontend/app/api/*` |
| **MFA TOTP** (RFC 6238) | enrolamiento con QR en `/account`, 8 códigos de recuperación de un solo uso (SHA-256), login en dos pasos con *challenge* JWT de 5 min (`aud=nexus-mfa`, inservible en la API y de un solo uso), protección anti-replay del paso TOTP, secreto cifrado con AES-GCM por tenant, fallos de segundo factor cuentan para el bloqueo por cuenta; deshabilitar exige un código válido. Verificado con los vectores del RFC 6238 | `core/totp.py`, `api/routes/mfa.py` |
| MFA obligatorio por rol | `MFA_REQUIRED_ROLES='["owner"]'`: esos roles reciben un token confinado a `/auth/*` (403 `mfa_enrollment_required` en todo lo demás, incluido el ticket WS) hasta enrolar MFA; el refresh emite un token libre. La UI redirige a `/account` | `core/security.py`, `api/routes/auth.py` |
| Cambio de contraseña | política por longitud (≥12, sin contraseñas comunes ni el nombre del email), verifica la actual (los fallos cuentan para el bloqueo) y **revoca todas las sesiones** del usuario (marca `sessions-valid-after` en Redis; también `POST /auth/logout-all`) | `api/routes/auth.py` |
| Observabilidad | `X-Request-ID` (se descartan ids no seguros), logs de acceso en JSON (`JSON_LOGS`, siempre en producción) con tenant/usuario y sin PII ni cuerpos, métricas Prometheus en `/metrics` (404 salvo `METRICS_TOKEN`, bearer en tiempo constante): requests por ruta *templada*, latencia, eventos de auditoría, WebSockets abiertos | `core/observability.py`, `main.py` |
| Sesión deslizante | `POST /auth/refresh` rota el token (el anterior queda revocado), conserva `auth_time` y respeta un tope absoluto (`SESSION_MAX_HOURS`, 8 h); un cambio de rol o desactivación fuerza reingreso | `api/routes/auth.py` |
| Sesión revocable | `POST /auth/logout` deniega el `jti` del token en Redis hasta su expiración; el middleware lo comprueba en cada request (un token robado deja de servir tras cerrar sesión) | `api/routes/auth.py`, `core/security.py` |
| Anti fuerza bruta | rate-limit por IP **y** bloqueo por identidad (5 fallos/15 min, existan o no, se resetea al acertar) | `api/routes/auth.py` |
| Triage con trazabilidad | `PATCH /security/findings/{id}` (owner/analyst) registra `finding.status_changed` (de→a) en la cadena de auditoría | `api/routes/security.py` |
| Export CSV seguro | `GET /security/findings.csv` neutraliza inyección de fórmulas (`=`,`+`,`-`,`@`) y queda auditado | `api/routes/security.py` |
| RBAC | `owner` / `analyst` / `viewer` (informes: owner+analyst; auditoría: owner) | `api/deps.py` |

### Endurecimiento de despliegue incluido
Contenedores no-root con `cap_drop: ALL` y `no-new-privileges`, frontend con FS de solo lectura, red `data` **interna** (Postgres y Redis inalcanzables desde fuera), Redis con contraseña y sin persistencia.

### Checklist de producción
1. Sustituir **todos** los secretos de `.env`; `SEED_ON_START=false`, `TELEMETRY_SIMULATOR=false`.
2. Poner Envoy/WAF delante con TLS (y mTLS si se requiere), fijar `COOKIE_SECURE=true`, `TRUSTED_PROXIES=true` (solo si el proxy sobrescribe `X-Forwarded-For`), `PUBLIC_WEB_ORIGIN`/`PUBLIC_WS_URL` con `https`/`wss`.
3. Guardar las claves en un gestor de secretos (`JWT_PRIVATE_KEY`, `REPORT_SIGNING_KEY`, `DATA_ENCRYPTION_KEY`, `WEBHOOK_SECRET`) en vez del volumen `keys`; **respaldar `DATA_ENCRYPTION_KEY`**: sin ella los informes cifrados no se recuperan.
4. No publicar el puerto 8000 directamente: enrutar `/api` y `/ws` por el proxy.

### Variables de entorno
Ver [`.env.example`](.env.example) (compose) y [`backend/app/core/config.py`](backend/app/core/config.py) (lista completa; acepta `*_PATH` para secretos en fichero).

---

## API (resumen)

`POST /api/v1/auth/login` · `POST /auth/logout` · `POST /auth/logout-all` · `POST /auth/password` · `POST /auth/refresh` · `POST /auth/mfa/{setup,enable,disable,verify}` · `GET /auth/mfa/status` · `GET /auth/me` · `POST /auth/ws-ticket` · `GET /overview` · `GET /security/{summary,findings,findings.csv,endpoints}` · `PATCH /security/findings/{id}` · `GET /finops/{summary,timeseries}` · `GET /rag/{summary,queries,queries/{id}}` · `GET /reports` · `POST /reports/generate` · `GET /reports/{id}/{download,verify}` · `GET /reports/public-key` (público) · `POST /ask` · `GET /ask`, `/ask/{id}` · `GET /audit`, `/audit/verify` (owner) · `POST /webhooks/agents` (HMAC) · `WS /ws/telemetry?ticket=`

Ingesta desde un agente (ejemplo):
```python
ts = str(int(time.time())); body = json.dumps(payload).encode()
sig = "sha256=" + hmac.new(tenant_webhook_key, ts.encode()+b"."+body, hashlib.sha256).hexdigest()
requests.post(f"{API}/api/v1/webhooks/agents", data=body, headers={"X-Nexus-Tenant": tenant_id, "X-Nexus-Timestamp": ts, "X-Nexus-Signature": sig})
```
(`tenant_webhook_key = HKDF-SHA256(WEBHOOK_SECRET, info=b"webhook:"+tenant_id)`; ver `core/crypto.py`.)

---

## Pruebas

```bash
cd backend  && pytest -q                  # 45 tests (SQLite; +RLS real si hay PostgreSQL) — auth, logout/lockout, aislamiento, RBAC, triage, CSV, firma, cadena de auditoría, webhooks, WS
cd frontend && npm test                   # Jest + Testing Library
cd frontend && E2E_PASSWORD=… npm run test:e2e   # Playwright contra el stack levantado
```

Para validar **RLS real** (CI lo hace con un servicio PostgreSQL): crea los roles `nexus_owner` (superusuario) y `nexus_app` (sin privilegios) y exporta `DATABASE_URL`, `DATABASE_ADMIN_URL`, `TEST_PG_ADMIN_URL`, `TEST_PG_APP_URL`; la suite completa corre entonces sobre PostgreSQL y `test_postgres_rls.py` comprueba lectura/escritura cross-tenant, fail-closed y el trigger append-only. Ver `.github/workflows/ci.yml`.

---

## Alcance y limitaciones (leer antes de vender esto como "producción")

Esto es una implementación completa y probada del núcleo descrito, **pero no todo el texto del brief está construido**:

* **Datos simulados:** los agentes reales (ShadowAPI, KubeCost, ContextRAG) no están conectados. El *Seeder* y el *simulador* generan datos plausibles; la ingesta real entra por el webhook HMAC. El índice NLI es un dato recibido, no se calcula aquí. Las muestras en vivo del simulador se prorratean para no distorsionar el histórico.
* **Sin WebAuthn/Passkeys ni mTLS en la app:** la autenticación es contraseña (Argon2id) + MFA TOTP opcional + JWT RS256. MFA es opcional salvo que configures `MFA_REQUIRED_ROLES`. mTLS debe terminarse en Envoy/WAF (no se incluye config de Envoy ni manifiestos Kubernetes).
* **Sin "Zero-Knowledge"**: el servidor descifra informes para servirlos; el cifrado es en reposo con claves por tenant.
* **Sin gRPC ni ClickHouse**; Las columnas MFA se añadieron al modelo `users`: una base creada con una versión anterior necesita `ALTER TABLE` (no hay Alembic).
* **Credenciales admin en la API:** el simulador demo y el seeder usan el rol owner (`DATABASE_ADMIN_URL`). En producción desactiva ambos (`TELEMETRY_SIMULATOR=false`, `SEED_ON_START=false`); el entrypoint solo necesita la URL admin para aplicar el esquema, y puedes quitarla del servicio tras el primer arranque / ejecutar `app.db.bootstrap` como job aparte.
* **Migraciones:** el esquema se crea con `create_all` + DDL idempotente (`app.db.bootstrap`); no hay Alembic.
* `docker compose up` no pudo ejecutarse en el entorno donde se desarrolló (sin demonio Docker); cada pieza se validó por separado: arranque en modo `production` con claves generadas por `genkeys`, PostgreSQL 16 con roles sin privilegios, Redis, Next.js en build de producción y Playwright (login, navegación, generación/verificación de informe, stream WS en vivo, sin errores de CSP ni de hidratación en consola).
