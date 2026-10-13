/* Formulario de contacto: sesión anónima + CSRF, validación accesible y consentimiento explícito (Ley 21.719). */
const FIELDS = { name: 'c-name', email: 'c-email', message: 'c-message', consentimiento_ley_21719: 'c-consent' };
const MESSAGES = {
  name: 'Escribe tu nombre (mínimo 2 letras).',
  email: 'Escribe un correo válido, por ejemplo nombre@empresa.com.',
  message: 'Cuéntanos qué necesitas en al menos 10 caracteres.',
  consentimiento_ley_21719: 'Para enviar tu consulta debes aceptar el uso de tus datos. Es la única forma de que podamos responderte.',
};
const STATUS_CLASS = {
  info: 'text-sm text-slate-300',
  success: 'text-sm font-medium text-emerald-300 rounded-lg border border-emerald-400/40 bg-emerald-400/10 px-3 py-2',
  error: 'text-sm font-medium text-rose-300 rounded-lg border border-rose-400/40 bg-rose-400/10 px-3 py-2',
};
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validate(values) {
  const errors = {};
  if (values.name.trim().length < 2) errors.name = MESSAGES.name;
  if (!EMAIL.test(values.email.trim())) errors.email = MESSAGES.email;
  if (values.message.trim().length < 10) errors.message = MESSAGES.message;
  if (!values.consent) errors.consentimiento_ley_21719 = MESSAGES.consentimiento_ley_21719;
  return errors;
}

export function initContact(doc = document, fetchFn = fetch) {
  const form = doc.getElementById('contact-form');
  if (!form) return;
  const status = doc.getElementById('c-status');
  const submit = doc.getElementById('c-submit');
  const counter = doc.getElementById('c-count');
  let csrf = null;

  /* Un solo canal de mensajes: éxito (verde, role=status) o error (rojo, role=alert) para que lectores de pantalla lo anuncien. */
  const setStatus = (message, kind = 'info') => {
    status.textContent = message;
    status.className = STATUS_CLASS[kind];
    status.dataset.kind = kind;
    status.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  };

  const ensureSession = async (force = false) => {
    if (csrf && !force) return csrf;
    const res = await fetchFn('/api/v1/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!res.ok) throw Object.assign(new Error('session'), { status: res.status });
    csrf = (await res.json()).csrf_token;
    return csrf;
  };
  const post = async (payload, token) => fetchFn('/api/v1/contacto', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF-Token': token },
    body: JSON.stringify(payload),
  });
  const showError = (key, message) => {
    const input = doc.getElementById(FIELDS[key]);
    const out = doc.getElementById(`${FIELDS[key]}-err`);
    if (!input || !out) return;
    out.textContent = message;
    out.hidden = false;
    input.setAttribute('aria-invalid', 'true');
  };
  const clearErrors = () => {
    for (const id of Object.values(FIELDS)) {
      doc.getElementById(id)?.removeAttribute('aria-invalid');
      const out = doc.getElementById(`${id}-err`);
      if (out) { out.textContent = ''; out.hidden = true; }
    }
  };
  const focusFirstInvalid = () => doc.querySelector('#contact-form [aria-invalid="true"]')?.focus();

  form.addEventListener('focusin', () => { ensureSession().catch(() => {}); }, { once: true });
  form.querySelector('#c-message')?.addEventListener('input', (e) => { if (counter) counter.textContent = String(e.target.value.length); });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearErrors();
    setStatus('');
    const data = new FormData(form);
    const values = { name: String(data.get('name') ?? ''), email: String(data.get('email') ?? ''), message: String(data.get('message') ?? ''), consent: data.get('consentimiento_ley_21719') === 'on' };
    const errors = validate(values);
    if (Object.keys(errors).length) {
      for (const [k, m] of Object.entries(errors)) showError(k, m);
      setStatus('Revisa los campos marcados.', 'error');
      focusFirstInvalid();
      return;
    }
    submit.disabled = true;
    setStatus('Enviando…');
    try {
      const payload = { name: values.name, email: values.email, message: values.message, consentimiento_ley_21719: true, website: String(data.get('website') ?? '') };
      let res = await post(payload, await ensureSession());
      if ([401, 403, 409].includes(res.status)) {
        // Sesión ausente o vencida: se renueva una vez de forma transparente y se reintenta.
        res = await post(payload, await ensureSession(true));
      }
      if (res.status === 201) {
        const out = await res.json();
        form.reset();
        if (counter) counter.textContent = '0';
        setStatus(`¡Listo! Recibimos tu consulta. Tu referencia es ${out.referencia}. Te responderemos por correo.`, 'success');
      } else if (res.status === 422) {
        const body = await res.json().catch(() => ({}));
        for (const item of Array.isArray(body.detail) ? body.detail : []) {
          const key = item.loc?.[item.loc.length - 1];
          if (key in FIELDS) showError(key, MESSAGES[key]);
        }
        setStatus('Revisa los campos marcados.', 'error');
        focusFirstInvalid();
      } else if (res.status === 429) {
        setStatus('Alcanzaste el límite de consultas por hora. Inténtalo más tarde.', 'error');
      } else if (res.status === 401 || res.status === 403 || res.status === 409) {
        csrf = null;
        setStatus('Tu sesión expiró. Recarga la página y vuelve a enviar el formulario.', 'error');
      } else if (res.status === 503) {
        setStatus('El servicio no está disponible por ahora. Tu mensaje no se envió: inténtalo de nuevo en unos minutos.', 'error');
      } else {
        setStatus('No pudimos enviar tu consulta. Inténtalo de nuevo en unos minutos.', 'error');
      }
    } catch (err) {
      if (err?.status === 503) setStatus('El servicio no está disponible por ahora. Tu mensaje no se envió: inténtalo de nuevo en unos minutos.', 'error');
      else if (err?.status === 429) setStatus('Alcanzaste el límite de consultas por hora. Inténtalo más tarde.', 'error');
      else setStatus('No pudimos conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.', 'error');
    } finally {
      submit.disabled = false;
    }
  });
}
