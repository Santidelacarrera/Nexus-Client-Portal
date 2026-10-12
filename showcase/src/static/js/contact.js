/* Formulario de contacto: sesión anónima + CSRF, validación accesible y consentimiento explícito (Ley 21.719). */
const FIELDS = { name: 'c-name', email: 'c-email', message: 'c-message', consentimiento_ley_21719: 'c-consent' };
const MESSAGES = {
  name: 'Escribe tu nombre (mínimo 2 letras).',
  email: 'Escribe un correo válido, por ejemplo nombre@empresa.com.',
  message: 'Cuéntanos qué necesitas en al menos 10 caracteres.',
  consentimiento_ley_21719: 'Para enviar tu consulta debes aceptar el uso de tus datos. Es la única forma de que podamos responderte.',
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

  const ensureSession = async () => {
    if (csrf) return csrf;
    const res = await fetchFn('/api/v1/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error('session');
    csrf = (await res.json()).csrf_token;
    return csrf;
  };
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
    status.textContent = '';
    const data = new FormData(form);
    const values = { name: String(data.get('name') ?? ''), email: String(data.get('email') ?? ''), message: String(data.get('message') ?? ''), consent: data.get('consentimiento_ley_21719') === 'on' };
    const errors = validate(values);
    if (Object.keys(errors).length) {
      for (const [k, m] of Object.entries(errors)) showError(k, m);
      status.textContent = 'Revisa los campos marcados.';
      focusFirstInvalid();
      return;
    }
    submit.disabled = true;
    status.textContent = 'Enviando…';
    try {
      const token = await ensureSession();
      const res = await fetchFn('/api/v1/contacto', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF-Token': token },
        body: JSON.stringify({ name: values.name, email: values.email, message: values.message, consentimiento_ley_21719: true, website: String(data.get('website') ?? '') }),
      });
      if (res.status === 201) {
        const out = await res.json();
        form.reset();
        if (counter) counter.textContent = '0';
        status.textContent = `Recibimos tu consulta. Tu referencia es ${out.referencia}. Te responderemos por correo.`;
      } else if (res.status === 422) {
        const body = await res.json();
        for (const item of body.detail ?? []) {
          const key = item.loc?.[item.loc.length - 1];
          if (key in FIELDS) showError(key, MESSAGES[key]);
        }
        status.textContent = 'Revisa los campos marcados.';
        focusFirstInvalid();
      } else if (res.status === 429) {
        status.textContent = 'Enviaste varias consultas seguidas. Espera un momento antes de intentarlo de nuevo.';
      } else if (res.status === 409 || res.status === 401 || res.status === 403) {
        csrf = null;
        status.textContent = 'Tu sesión expiró. Recarga la página y vuelve a enviar el formulario.';
      } else {
        status.textContent = 'No pudimos enviar tu consulta. Inténtalo de nuevo en unos minutos.';
      }
    } catch {
      status.textContent = 'No pudimos conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.';
    } finally {
      submit.disabled = false;
    }
  });
}
