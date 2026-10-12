#!/usr/bin/env bash
# Verificación completa de la vitrina (Nexus Security & AI Lab). Sale con código != 0 si algo falla.
#   TEST_ADMIN_DSN=postgresql://admin:pw@localhost/postgres ./scripts/verify.sh
# Opcionales: SHOWCASE_URL=http://localhost:8000 (activa axe), CHROMIUM_PATH=/ruta/chromium, SKIP_SEMGREP=1
set -uo pipefail
cd "$(dirname "$0")/.."
: "${TEST_ADMIN_DSN:?TEST_ADMIN_DSN requerida (PostgreSQL 16 con un rol con CREATEDB/CREATEROLE)}"
fail=0
step() { printf '\n== %s\n' "$1"; shift; if "$@"; then echo "OK"; else echo "FALLO: $*"; fail=1; fi; }

step "pytest (backend, RLS real, correo con SMTP simulado)" python -m pytest -q
step "jest (consentimiento + DOMPurify)" npx jest
step "eslint (+ eslint-plugin-security)" npm run lint
step "bandit" bandit --ini .bandit -r src -q
step "pip-audit" pip-audit -r requirements.txt
step "npm audit (producción, alto)" npm audit --omit=dev --audit-level=high
if [ -z "${SKIP_SEMGREP:-}" ]; then
  if command -v semgrep >/dev/null; then step "semgrep owasp-top-ten" semgrep --config p/owasp-top-ten --metrics=off --error src
  else echo; echo "== semgrep: NO instalado (omitido; ver README)"; fi
fi
if [ -n "${SHOWCASE_URL:-}" ]; then step "playwright + axe WCAG 2.1 AA" npx playwright test; else echo; echo "== axe: omitido (define SHOWCASE_URL con el sitio en marcha)"; fi

# RUT y domicilio no deben aparecer en NINGUNA plantilla ni página (decisión del dueño)
step "sin RUT/domicilio en plantillas" bash -c '! grep -rniE "\brut\b|domicilio|tax_id|company_address" src/templates src/routes/pages.py'

echo; [ "$fail" -eq 0 ] && echo "VERIFICACIÓN COMPLETA: OK" || echo "VERIFICACIÓN: HAY FALLOS"
exit "$fail"
