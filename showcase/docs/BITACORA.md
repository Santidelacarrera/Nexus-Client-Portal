# Bitácora — Nexus Security & AI Lab · vitrina comercial (`showcase/`)

> La nota del proyecto en el vault y `verify_showcase.ps1` (carpeta workspace) no existen en este entorno cloud. Esta bitácora hace de nota; el equivalente del script es `scripts/verify.sh` (bash, ejecutado aquí). Si `verify_showcase.ps1` hace comprobaciones adicionales, hay que correrlo en Windows (ver Pendientes).

## Bitácora de decisiones
| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-10-12 | Quitar RUT y domicilio de configuración, plantillas y páginas (`COMPANY_TAX_ID`/`COMPANY_ADDRESS` eliminadas) | Instrucción del dueño; un test (`test_rut_and_domicilio_never_appear`) y `verify.sh` lo hacen cumplir. Riesgo legal anotado en Pendientes |
| 2026-10-12 | Integrada la rama `claude/sweet-johnson-6sbti2` (commits de santidlc1 del 11-oct: `mailer.py` con BackgroundTasks, 4 proyectos nuevos, diagramas, `contact.js`). Se descartó mi `notify.py` duplicado y se conservó `mailer.py` (más completo: rechaza credenciales sin TLS, tarea en segundo plano) | Dos implementaciones paralelas del mismo aviso; una sola mantiene el código simple. Se le añadió mi corrección de codificación |
| 2026-10-12 | Nombre por defecto «Nexus Security & AI Lab» en vez de «Nexus Security SpA» | «SpA» afirma una sociedad que aún no existe (el responsable es Santiago como persona natural, según el abogado) |
| 2026-10-12 | (descartado por la integración) Aviso por correo con `smtplib` en hilo, mejor esfuerzo | Sin dependencias nuevas ($0); la consulta ya está guardada, un fallo SMTP no debe perderla |
| 2026-10-12 | Cuerpo del correo en `quoted-printable` UTF-8 | Los tests mostraron texto corrupto con servidores sin 8BITMIME |
| 2026-10-12 | Sin datos personales en logs de notificación | Minimización (Ley 21.719); probado con `caplog` |
| 2026-10-12 | Dockerfile: `ARG NODE_IMAGE/PYTHON_IMAGE` y secreto opcional `ca` | Permite construir tras proxies con CA propia y con Docker Hub limitado sin cambiar la imagen final |
| 2026-10-12 | `pip-audit` limpio actualizando fastapi/starlette/pyjwt/jinja2/slowapi (ronda anterior) | Avisos reales; 53 tests siguieron en verde |

| 2026-10-12 | Revisión legal: según el dueño, un abogado revisó las páginas legales y acordó que, por ahora, el responsable/representante es Santiago como persona natural; la empresa se registrará si el proyecto se lanza | Cierra la decisión sobre RUT/domicilio (siguen sin mostrarse). Cuando se registre la empresa, actualizar `COMPANY_LEGAL_NAME` y volver a pedir revisión |

## Evidencia (ejecutada 2026-10-12)
| Comprobación | Resultado |
|---|---|
| `./scripts/verify.sh` (SKIP_SEMGREP=1) | `VERIFICACIÓN COMPLETA: OK` |
| `pytest -q` | ver PR de integración (incluye `test_mailer.py` y RUT/domicilio) |
| `npx jest` | 9 passed |
| `npm run lint` · `bandit --ini .bandit -r src` | sin hallazgos |
| `pip-audit -r requirements.txt` | No known vulnerabilities found |
| `npm audit --omit=dev --audit-level=high` | found 0 vulnerabilities |
| `playwright test` (axe WCAG 2.1 AA, banner, formulario) | 7 passed contra la imagen Docker en marcha |
| `docker build` (imagen `nexus-showcase:nexus-security-ai-lab`) | construida; corre como uid 10001 |
| Formulario en la imagen (navegador real + PostgreSQL + SMTP simulado) | «Recibimos tu consulta… NX-F5021C0F»; fila en BD con consentimiento `consentimiento_ley_21719` y política; correo recibido con Reply-To y referencia |
| RUT/domicilio en 8 páginas servidas por el contenedor | 0 apariciones |

## Pendientes para Santiago
1. **Semgrep `p/owasp-top-ten` no pudo ejecutarse** (proxy bloquea `semgrep.dev`). Correr `make security` o `verify.sh` sin `SKIP_SEMGREP`.
2. **`verify_showcase.ps1`** no estaba accesible: ejecutarlo en Windows y comparar con `scripts/verify.sh`.
3. ~~Revisión por abogado~~ — **hecha según el dueño** (2026-10-12; no hay constancia escrita en el repo: guardar el correo/dictamen del abogado). Al registrar la empresa, actualizar los datos y las páginas.
4. Completar `COMPANY_LEGAL_NAME` y `PRIVACY_CONTACT_EMAIL` reales en el `.env` de producción.
5. **SMTP real**: elegir proveedor sin costo, definir `SMTP_*`, `SMTP_FROM`, `ADMIN_EMAIL` y probar un envío real (aquí solo hubo SMTP simulado). Revisar SPF/DKIM del dominio.
6. **Despliegue** (no lo hice, fuera de mis límites): dominio, TLS, `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `ALLOWED_HOSTS`, `TRUSTED_PROXY` solo tras un proxy confiable; HSTS se activa en producción.
7. Redis (`RATELIMIT_STORAGE_URI`) si hay más de un proceso/réplica.
8. Cron diario para `SELECT purge_expired_contact_messages();` y respaldo cifrado de PostgreSQL; contraseñas de los roles `showcase_app`/`showcase_staff` con `scripts/db_roles.sh`.
9. Un humano debe decidir el estado `aprobado_santiago` / `aprobado_sistema`.

## Riesgos conocidos
- Rate limit en memoria por proceso (ver 7). Las cifras de los límites están fijas en el código.
- El correo transporta datos personales al buzón interno: ese buzón debe estar cubierto por la política de privacidad y la retención de 12 meses.
- `npm audit` completo marca vulnerabilidades en herramientas de desarrollo (jest 29, tailwind 3); no se distribuyen.
- Contraste de foco/bordes verificado por axe y cálculo, no por revisión visual humana con lectores de pantalla.
