-- ============================================================================================================
-- Nexus Showcase — esquema PostgreSQL 16 con Row-Level Security FORZADO en todas las tablas.
-- Idempotente: se puede aplicar varias veces:   psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -f schema.sql
-- Debe aplicarlo el PROPIETARIO del esquema; la aplicación se conecta con roles sin privilegios (ver abajo).
--
-- Roles (se crean NOLOGIN; scripts/db_roles.sh les asigna LOGIN + contraseña desde variables de entorno,
-- jamás desde este archivo):
--   showcase_app    → API pública. Solo puede INSERTAR/leer lo de SU sesión. NO puede leer mensajes de contacto.
--   showcase_staff  → panel interno. Solo lectura de todo + cambiar el estado de un mensaje.
-- ============================================================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'showcase_app') THEN
        CREATE ROLE showcase_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'showcase_staff') THEN
        CREATE ROLE showcase_staff NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------------------------------------
-- Tablas
-- ---------------------------------------------------------------------------------------------------------

-- Sesión anónima y estrictamente necesaria: solo existe para poder enlazar la evidencia de consentimiento.
CREATE TABLE IF NOT EXISTS visitor_sessions (
    id          uuid        PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);

-- Evidencia auditable del consentimiento (Ley 21.719 / GDPR art. 7.1). Solo-inserción: una revocación es
-- una fila nueva con granted = false. No guarda IP, user-agent ni datos personales (minimización).
CREATE TABLE IF NOT EXISTS consent_records (
    id             uuid        PRIMARY KEY,
    session_id     uuid        NOT NULL REFERENCES visitor_sessions (id),
    consent_key    text        NOT NULL CHECK (consent_key IN ('consentimiento_ley_21719')),
    granted        boolean     NOT NULL,
    policy_version text        NOT NULL CHECK (length(policy_version) BETWEEN 1 AND 64),
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, id)
);

-- Datos mínimos imprescindibles: nombre, correo y mensaje. Se conservan 12 meses y luego se purgan.
CREATE TABLE IF NOT EXISTS contact_messages (
    id           uuid        PRIMARY KEY,
    session_id   uuid        NOT NULL,
    consent_id   uuid        NOT NULL,
    name         text        NOT NULL CHECK (length(name)    BETWEEN 2  AND 120),
    email        text        NOT NULL CHECK (length(email)   BETWEEN 5  AND 254),
    message      text        NOT NULL CHECK (length(message) BETWEEN 10 AND 2000),
    status       text        NOT NULL DEFAULT 'nuevo' CHECK (status IN ('nuevo', 'leido', 'respondido')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    retain_until timestamptz NOT NULL DEFAULT (now() + interval '12 months'),
    -- el consentimiento debe pertenecer a la MISMA sesión que envía el mensaje
    FOREIGN KEY (session_id, consent_id) REFERENCES consent_records (session_id, id)
);

CREATE INDEX IF NOT EXISTS contact_messages_created_idx ON contact_messages (created_at DESC);
CREATE INDEX IF NOT EXISTS contact_messages_retain_idx  ON contact_messages (retain_until);

-- ---------------------------------------------------------------------------------------------------------
-- Integridad en la propia base de datos
-- ---------------------------------------------------------------------------------------------------------

-- La evidencia de consentimiento no se edita ni se borra.
CREATE OR REPLACE FUNCTION consent_records_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'consent_records es de solo inserción (revoca insertando una fila con granted = false)';
END
$$;

DROP TRIGGER IF EXISTS consent_records_no_mutation ON consent_records;
CREATE TRIGGER consent_records_no_mutation
    BEFORE UPDATE OR DELETE ON consent_records
    FOR EACH ROW EXECUTE FUNCTION consent_records_append_only();

-- No puede existir un mensaje sin un consentimiento OTORGADO y vigente en su propia sesión.
CREATE OR REPLACE FUNCTION contact_messages_require_consent() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    ok boolean;
BEGIN
    SELECT granted INTO ok FROM consent_records
     WHERE id = NEW.consent_id AND session_id = NEW.session_id AND consent_key = 'consentimiento_ley_21719';
    IF ok IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'no hay consentimiento otorgado para este mensaje' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS contact_messages_consent_check ON contact_messages;
CREATE TRIGGER contact_messages_consent_check
    BEFORE INSERT ON contact_messages
    FOR EACH ROW EXECUTE FUNCTION contact_messages_require_consent();

-- Retención: purga de mensajes vencidos. Solo el propietario (o un cron con su rol) la ejecuta.
CREATE OR REPLACE FUNCTION purge_expired_contact_messages() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    n integer;
BEGIN
    DELETE FROM contact_messages WHERE retain_until < now();
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END
$$;
REVOKE ALL ON FUNCTION purge_expired_contact_messages() FROM PUBLIC;

-- Identificador de sesión del contexto actual (lo fija la API por transacción con set_config(..., true)).
CREATE OR REPLACE FUNCTION app_session_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('app.session_id', true), '')::uuid
$$;

-- ---------------------------------------------------------------------------------------------------------
-- Row-Level Security: habilitado y FORZADO (también para el propietario) en TODAS las tablas.
-- Sin política = sin acceso (fail-closed).
-- ---------------------------------------------------------------------------------------------------------
ALTER TABLE visitor_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE visitor_sessions FORCE  ROW LEVEL SECURITY;
ALTER TABLE consent_records  ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_records  FORCE  ROW LEVEL SECURITY;
ALTER TABLE contact_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE contact_messages FORCE  ROW LEVEL SECURITY;

-- visitor_sessions
DROP POLICY IF EXISTS app_select   ON visitor_sessions;
DROP POLICY IF EXISTS app_insert   ON visitor_sessions;
DROP POLICY IF EXISTS staff_select ON visitor_sessions;
CREATE POLICY app_select   ON visitor_sessions FOR SELECT TO showcase_app   USING (id = app_session_id());
CREATE POLICY app_insert   ON visitor_sessions FOR INSERT TO showcase_app   WITH CHECK (id = app_session_id() AND expires_at > now());
CREATE POLICY staff_select ON visitor_sessions FOR SELECT TO showcase_staff USING (true);

-- consent_records
DROP POLICY IF EXISTS app_select   ON consent_records;
DROP POLICY IF EXISTS app_insert   ON consent_records;
DROP POLICY IF EXISTS staff_select ON consent_records;
CREATE POLICY app_select   ON consent_records FOR SELECT TO showcase_app   USING (session_id = app_session_id());
CREATE POLICY app_insert   ON consent_records FOR INSERT TO showcase_app   WITH CHECK (session_id = app_session_id());
CREATE POLICY staff_select ON consent_records FOR SELECT TO showcase_staff USING (true);

-- contact_messages: la API pública solo ESCRIBE (no existe política SELECT para showcase_app).
DROP POLICY IF EXISTS app_insert   ON contact_messages;
DROP POLICY IF EXISTS staff_select ON contact_messages;
DROP POLICY IF EXISTS staff_update ON contact_messages;
CREATE POLICY app_insert   ON contact_messages FOR INSERT TO showcase_app   WITH CHECK (session_id = app_session_id());
CREATE POLICY staff_select ON contact_messages FOR SELECT TO showcase_staff USING (true);
CREATE POLICY staff_update ON contact_messages FOR UPDATE TO showcase_staff USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------------------------------------
-- Privilegios mínimos (RLS decide QUÉ filas; GRANT decide QUÉ operaciones)
-- ---------------------------------------------------------------------------------------------------------
REVOKE ALL ON visitor_sessions, consent_records, contact_messages FROM PUBLIC;
REVOKE ALL ON visitor_sessions, consent_records, contact_messages FROM showcase_app, showcase_staff;

GRANT SELECT, INSERT ON visitor_sessions TO showcase_app;
GRANT SELECT, INSERT ON consent_records  TO showcase_app;
GRANT INSERT         ON contact_messages TO showcase_app;

GRANT SELECT ON visitor_sessions, consent_records, contact_messages TO showcase_staff;
GRANT UPDATE (status) ON contact_messages TO showcase_staff;

GRANT EXECUTE ON FUNCTION app_session_id() TO showcase_app, showcase_staff;
