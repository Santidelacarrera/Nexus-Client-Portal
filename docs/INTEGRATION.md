# Integración de punta a punta: Portal ⇄ MultiAgent_Consensus ⇄ ContextRAG_Engine

Estado: **implementado y verificado** contra los tres servicios reales (ver [Verificación](#9-verificación)).
Los parches para los repos hermanos están en [`integration/patches/`](../integration/patches/).

## 1. Hallazgos al leer los repos reales (corrigen el brief)

| Brief | Realidad en el código | Decisión |
|---|---|---|
| ContextRAG "debe exponer `POST /api/v1/retrieve`" | **Ya existe** (`contextrag/api/retrieval.py`): clave API ligada a tenant, `tenant_id` del cuerpo debe coincidir (403 si no), auditoría dentro de la transacción RLS, **falla cerrada** (503) si no puede auditar | No se reescribe; se consume tal cual |
| GUC de RLS `app.current_tenant` | El código usa **`app.tenant`** (`contextrag/db.py`, `audit.py`) y tiene tests reales de RLS | Se mantiene `app.tenant`; cambiarlo rompería lo ya probado |
| Auditoría con "particionamiento mensual" | Cierto para `answer_audit`, **no** para `retrieval_audit` (la del endpoint) | Parche `0002`: `retrieval_audit` particionada por mes, mismo patrón que `answer_audit` |
| Consensus = "capa de agentes" genérica | Es un orquestador **TypeScript/NestJS** de debates de **PRs** (Red Team/Arquitecto/FinOps), acoplado a diffs | Módulo **independiente** `answer_gate` (parche `0001`); el debate de PRs no se toca |
| Autenticación | ContextRAG: `X-API-Key` por tenant. Consensus: una API key compartida | El portal firma una **aserción HMAC** (tenant + hash del cuerpo + jti); Consensus elige la clave de ContextRAG del tenant *autenticado* |

> Dato operativo: Consensus y ContextRAG leen **`DATABASE_URL`/`REDIS_URL`**. Si arrancas todo desde una misma shell con las
> variables del portal, Consensus intentará conectar a la BD del portal. `scripts/e2e/run_stack.sh` aísla el entorno de cada servicio.

## 2. Arquitectura

```
 Browser ──cookie httpOnly──► Next.js (BFF) ──Bearer RS256──► Portal API (FastAPI)  ── PostgreSQL + RLS (nexus_app)
                                                                 │  POST /api/v1/ask {question}            consensus_runs (cifrado AES-GCM por tenant)
                                                                 │  tenant = claim `tid` del JWT           audit_logs (cadena hash, solo-insertar)
                                                                 ▼
                      X-Nexus-Assertion = HMAC(tenant, user, request-id, sha256(cuerpo), jti, exp ≤ 60 s)
                                                                 ▼
                                MultiAgent_Consensus · answer gate  (NestJS)  POST /v1/answer-gate/reviews
                                  1. verifica aserción (firma, aud, exp, cuerpo, jti de un solo uso)
                                  2. recupera ──► ContextRAG POST /api/v1/retrieve   X-API-Key = clave reader del tenant
                                                       │ filtra por tenant (Qdrant + BM25) y audita en tx con `app.tenant` (RLS, rol contextrag_app)
                                  3. panel en paralelo (timeout c/u):  Hallucination Critic · Tenant Security Auditor (VETO) · Coherence Validator
                                  4. protocolo FAIL-CLOSED ─► RELEASED | BLOCKED   (contrato answer-review.v1)
                                                                 ▼
                                Portal: valida el contrato ESTRICTO, re-verifica tenant/eco/invariante del comité, persiste cifrado, audita
```

Responsabilidades: **ContextRAG** recupera y audita (nunca decide qué se muestra). **Consensus** decide si el borrador es liberable.
**Portal** autentica al usuario, fija el tenant, no confía en nada de abajo, y presenta.

## 3. Contratos (`contracts/answer-review.v1.schema.json`)

* Fuente de verdad: `backend/app/contracts/answer_review.py` (Pydantic **estricto**: sin campos extra, sin coerciones `"yes"→true`).
  El esquema JSON se regenera con `python -m app.contracts.answer_review ../contracts/answer-review.v1.schema.json` y un test
  falla si el archivo se desincroniza.
* **Entrada del usuario** (`AskRequest`): solo `question` y `topK`. **No hay campo de tenant**; si llega, 422.
* **Salida** (`AnswerReview`): `outcome`, `answer` (solo `RELEASED`), `reasons[]` (códigos máquina), `votes[]`, `sources[]`
  (coordenadas: doc, sección, página, offsets, score), `retrieval`, `timings`, `escalation`.
* Un cambio incompatible ⇒ `answer-review.v2`: el portal rechaza (502) lo que no sea exactamente v1.

## 4. Aislamiento multi-tenant: una comprobación independiente por capa

| Capa | Mecanismo | Si falla |
|---|---|---|
| Browser → BFF | Cookie `httpOnly; SameSite=Strict`, check de `Origin`, allow-list de rutas | 401/403 |
| Portal API | Tenant **solo** del claim `tid` del JWT RS256; body con tenant ⇒ 422; sesión por tenant (RLS + filtro ORM + guard de escritura) | 401/422 |
| Portal → Consensus | Aserción HMAC con `bsha` (la pregunta no se puede cambiar) y `jti` único; Consensus rechaza campos extra en el cuerpo | 401/400 |
| Consensus → ContextRAG | Clave API **del tenant autenticado**; `tenant_id` del cuerpo = tenant de la clave (ContextRAG exige coincidencia) | 403 → `retrieval_forbidden` |
| ContextRAG | Filtro de tenant dentro de la consulta (Qdrant + BM25) + transacción con `set_config('app.tenant', …)` | 503 (no audita ⇒ no sirve) |
| PostgreSQL | RLS `tenant = current_setting('app.tenant', true)` con `WITH CHECK`; rol `contextrag_app` sin superuser/BYPASSRLS/propietario; auditoría solo-insertar | sin filas / `InsufficientPrivilege` |
| Respuesta (Consensus) | Eco `tenantId` debe coincidir ⇒ si no, **se descarta todo el contenido**; el auditor busca ids/alias de OTROS tenants en fragmentos, metadatos y borrador (canarios) | `BLOCKED` + veto |
| Respuesta (Portal) | `tenantId`, `requestId` y `question` deben coincidir; si el eco no es del tenant ⇒ `ContractViolation` (502 + evento de auditoría `ask.contract_violation`) | 502 |
| Historial | `consensus_runs` con RLS + el usuario solo ve sus ejecuciones; contenido cifrado con clave HKDF por tenant (AAD = id de ejecución) | 404 |

## 5. Protocolo de consenso (fail-closed)

1. **Quórum total**: los 3 agentes con veredicto válido; fallo/timeout/forma inválida/suplantación/ausencia ⇒ `BLOCKED`.
2. **Veto de seguridad**: el Auditor de Tenant rechaza ⇒ `BLOCKED`, **sin respuesta ni fuentes**, sin escalado.
3. `approve` con hallazgos `high|critical` ⇒ incoherente ⇒ `BLOCKED`.
4. **Unanimidad** para liberar. Desacuerdo puro ⇒ `BLOCKED` + `escalation: true` (humano).
5. **Defensa en profundidad en el portal** (`enforce_invariants`): un `RELEASED` solo se acepta si los 3 agentes (sin duplicados) aprobaron,
   sin hallazgos bloqueantes, con texto y sin motivos de bloqueo; si no, se **degrada** a `BLOCKED` (`portal_invariant_violation`). Un
   `BLOCKED` con `answer` presente se **sanea**. Nunca se *mejora* un veredicto.

Fallos previos al panel (todos `BLOCKED`, sin contenido): `retrieval_unavailable|timeout|forbidden|tenant_not_provisioned`, `no_context`, `tenant_mismatch`.
Fallos del portal hacia Consensus: 503 `consensus_unavailable` (red, timeout, 4xx/5xx), 502 `consensus_contract_violation`.

## 6. Pasos para ensamblar (orden recomendado)

1. **ContextRAG** — aplicar `0002` (partición mensual de `retrieval_audit`). Crear una clave **reader** por tenant
   (`python -m contextrag keygen --id consensus-<slug> --tenant <tenantId> --role reader --add-to keys.json`) y una **admin** para ingesta.
   Usar el **`tenants.id` del portal** como identificador de tenant en todas las capas (sin tabla de traducción).
2. **Consensus** — aplicar `0001`; configurar `PORTAL_ASSERTION_SECRET` (≥ 32), `RAG_URL`, `RAG_TENANT_KEYS_FILE` (tenant → clave reader)
   y `GATE_TENANT_ALIASES_FILE`. Sin secreto, el gate responde 503.
3. **Portal** — `CONSENSUS_URL` y `CONSENSUS_ASSERTION_SECRET` (el mismo secreto). Sin ellos `/ask` responde 503 `consensus_not_configured`.
4. **Secretos**: el secreto HMAC y las claves por tenant van en un gestor de secretos; rotar el secreto = desplegar ambos extremos.
5. **Verificar**: `scripts/e2e/run_stack.sh start && python scripts/e2e/verify_flow.py`.

## 7. Cómo ejecutarlo localmente (stack real)

```bash
# requisitos: PostgreSQL 16 y Redis locales; un rol owner de PG; venv del portal; venv de ContextRAG; checkout de Consensus con el parche 0001
export PORTAL_PY=…/portal-venv/bin/python RAG_PY=…/rag-venv/bin/python \
       CONSENSUS_DIR=…/MultiAgent_Consensus PG_ADMIN=postgresql://owner:pw@localhost
scripts/e2e/run_stack.sh start          # BD, roles sin privilegios, claves por tenant, ingesta demo (incluye docs hostiles), 3 servicios
python scripts/e2e/verify_flow.py       # 28 comprobaciones de punta a punta
cd frontend && E2E_ASK=1 npx playwright test -g "ask:"   # UI contra el stack
scripts/e2e/run_stack.sh stop
```

## 8. Qué es de producción y qué es "stack offline"

* **Agentes del comité**: heurísticos deterministas (solapamiento léxico, cifras, patrones). Cumplen el protocolo y son testeables, pero
  **no son un juez NLI/LLM**. El punto de extensión es `GateAgent`; el protocolo valida igual la salida de un agente basado en LLM.
* **ContextRAG offline** (el de `run_stack.sh`): embeddings por hashing, índice en memoria, borrador *extractivo*. Para producción usar
  `EMBEDDER=bge RERANKER=cross-encoder NLI=deberta` y Qdrant (README de ContextRAG). El borrador del endpoint `retrieve` **no está verificado**
  (`draft_verified: false`); la barrera es el comité.
* **Aserción HMAC simétrica**: portal y Consensus comparten secreto. Alternativa asimétrica (RS256 con clave pública en Consensus) si no se confía
  en que el gate no pueda *firmar* como portal. `ReplayCache` es en memoria (1 réplica); con varias, Redis `SET NX EX`.
* Consensus no persiste el resultado del gate (lo hace el portal). `retrieval_audit` guarda `query` en claro (comportamiento existente de ContextRAG).
* No hay streaming ni cancelación; timeouts: portal 20 s, recuperación 8 s, agente 5 s.

## 9. Verificación

| Pieza | Resultado |
|---|---|
| Consensus (jest) | 57 tests nuevos (agentes, matriz de fallos del protocolo, servicio, HTTP+aserciones); **187/187** en el repo, typecheck limpio |
| ContextRAG (pytest, PG real propio del repo) | **247 pasan**, 2 skip; +3 tests de partición; ruff limpio |
| Portal backend (pytest) | **81** con PostgreSQL real y RLS (78 + 3 en SQLite); 25 tests nuevos de `/ask` (invariantes, deriva de contrato, aislamiento, cifrado, fallos upstream, rate limit) |
| Portal frontend | 20 tests Jest (+9 nuevos), lint y typecheck limpios; Playwright `ask:` pasa contra el stack real |
| **Stack real de 3 servicios** (`verify_flow.py`) | **28/28**: liberación unánime por tenant; aislamiento cruzado; veto por inyección y por fuga de otro tenant; sin contexto; 401/403 al saltarse capas; RLS con el rol `contextrag_app`; cadena de auditoría íntegra |
| Interoperabilidad | La aserción firmada en **Python** es verificada por **TypeScript** (canonical JSON idéntico) en el stack real |
