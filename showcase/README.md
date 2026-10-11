# Nexus Showcase — vitrina comercial

Sitio comercial de Nexus Security & AI Lab: presenta tres proyectos propios (con diagramas de arquitectura, **sin exponer código interno**) y recibe consultas con consentimiento auditable (Ley 21.719 / RGPD). FastAPI + Jinja2 + Tailwind, PostgreSQL 16, coste de licencias: $0.

## Puesta en marcha

```bash
cp .env.example .env            # completa valores; nada se hardcodea
python -m venv .venv && . .venv/bin/activate
make install && make build
psql "$ADMIN_URL" -f schema.sql  # idempotente
APP_DB_PASSWORD=… STAFF_DB_PASSWORD=… ADMIN_URL=… make db-roles
python scripts/hash_password.py  # genera STAFF_PASSWORD_HASH (Argon2id)
make run                         # usa --no-server-header: no se anuncia el servidor
```

## Estructura

| Ruta | Contenido |
|---|---|
| `schema.sql` | Tablas, roles `showcase_app`/`showcase_staff`, RLS **ENABLE + FORCE** en todas las tablas, triggers de consentimiento y retención |
| `src/main.py` | `create_app`: slowapi, cabeceras `secure` + CSP estricta, TrustedHost |
| `src/config.py` | `pydantic-settings`; sin secretos por defecto |
| `src/security/` | Argon2id, JWT HS256 en cookies `HttpOnly`/`Secure`/`SameSite=Strict`, nh3, CSRF |
| `src/schemas.py` | DTOs Pydantic v2: entradas `extra=forbid`, salidas en lista blanca |
| `content/projects.json` | Proyectos y diagramas (validados al arrancar) |
| `src/templates`, `src/static` | Frontend, páginas legales, banner de cookies |
| `tests/` | pytest contra PostgreSQL real, Jest, Playwright + axe |

## Garantías (y dónde se prueban)

- **Aislamiento en la base de datos**: la API pública solo inserta; no puede leer mensajes. El consentimiento es *append-only* y un mensaje no puede existir sin consentimiento de su misma sesión (`tests/test_rls.py`).
- **Consentimiento**: `consentimiento_ley_21719` solo vale con `true` literal; se guarda con marca de tiempo, versión de política e id de sesión (`tests/test_contact.py`).
- **Minimización**: solo nombre, correo y mensaje; campos extra devuelven 422.
- **Banner de cookies**: nada opcional se carga sin aceptación explícita (`tests/js/consent.test.js`); no hay peticiones a terceros (`tests/e2e/a11y.spec.js`).
- **WCAG 2.1 AA**: estructura y contraste calculados en `tests/test_pages.py`; auditoría axe en `tests/e2e/a11y.spec.js`.

## Cómo ejecutar las pruebas

```bash
export TEST_ADMIN_DSN=postgresql://admin:pw@localhost/postgres   # rol con CREATEDB/CREATEROLE
make test            # pytest + jest
make run &           # y luego, con SHOWCASE_URL apuntando al sitio:
npm run test:a11y
```

## Lo que NO está resuelto (leer antes de publicar)

1. **Las páginas legales son borradores.** Muestran «Sujeto a revisión legal» y marcadores «pendiente de completar». Un abogado debe revisarlas y se deben rellenar `COMPANY_*` y `PRIVACY_CONTACT_EMAIL` en `.env`. No se inventó ningún dato de empresa.
2. **Sin testimonios ni reseñas**: no existen, y no se simulan. Los proyectos figuran como «Prototipo funcional».
3. **Fuentes y DOMPurify auto-alojados** (Fontsource, licencia OFL; DOMPurify vendorizado) en vez del CDN de Google: así no se filtra la IP del visitante antes del consentimiento.
4. **Diagramas SVG generados en servidor** en lugar de Mermaid: pasan la CSP (sin scripts en línea) y llevan título, descripción y alternativa en lista.
5. **`eslint-plugin-jsx-a11y`** está configurado, pero este sitio no usa JSX, así que no analiza nada hoy; la accesibilidad se verifica con axe y `tests/test_pages.py`.
6. **Semgrep `p/owasp-top-ten` no se pudo ejecutar** en el entorno de desarrollo (el registro `semgrep.dev` estaba bloqueado). Ejecútalo en CI/local: `make security`.
7. **`npm audit` completo** informa vulnerabilidades en herramientas de *desarrollo* (jest 29, tailwind 3, cadena de babel); no se distribuyen. Las dependencias de producción (`--omit=dev`) están en 0.
8. **Dockerfile no probado**; el rate limit usa memoria (por proceso): con varios workers define `RATELIMIT_STORAGE_URI` (Redis).
9. **Contraste del anillo de foco y bordes**: verificado por cálculo (≥3:1), no por auditoría visual humana.
