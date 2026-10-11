/* Panel interno: login Argon2id en el servidor, lista de consultas. Todo texto se inserta con textContent. */
import { el } from './dom.js';

export function initStaff(doc = document, fetchFn = fetch) {
  const loginForm = doc.getElementById('staff-login');
  const panel = doc.getElementById('staff-panel');
  if (!loginForm || !panel) return;
  const status = doc.getElementById('s-status');
  const list = doc.getElementById('staff-list');
  const empty = doc.getElementById('staff-empty');
  let csrf = null;
  const fmt = new Intl.DateTimeFormat('es-CL', { dateStyle: 'medium', timeStyle: 'short' });

  const api = (path, init = {}) => fetchFn(path, { credentials: 'same-origin', ...init, headers: { Accept: 'application/json', ...(init.headers ?? {}) } });

  const render = (messages) => {
    list.replaceChildren();
    empty.hidden = messages.length > 0;
    for (const m of messages) {
      const mark = el('button', { text: m.estado === 'nuevo' ? 'Marcar como leído' : 'Marcar como respondido', className: 'btn btn-quiet !min-h-[40px] !py-1.5', attrs: { type: 'button' } });
      mark.addEventListener('click', async () => {
        const next = m.estado === 'nuevo' ? 'leido' : 'respondido';
        const res = await api(`/api/v1/staff/mensajes/${encodeURIComponent(m.referencia)}/estado?estado=${next}`, { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
        if (res.status === 204) load();
      });
      list.append(
        el('li', { className: 'glass rounded-xl p-5' }, [
          el('p', { text: `${m.referencia} · ${m.estado} · ${fmt.format(new Date(m.recibido_en))}`, className: 'text-xs text-slate-400' }),
          el('p', { text: `${m.nombre} <${m.email}>`, className: 'mt-1 font-semibold text-slate-100' }),
          el('p', { text: m.mensaje, className: 'mt-2 whitespace-pre-wrap leading-relaxed text-slate-300' }),
          el('p', { text: `Consentimiento v${m.consentimiento.version} · conservar hasta ${fmt.format(new Date(m.conservar_hasta))}`, className: 'mt-3 text-xs text-slate-500' }),
          el('div', { className: 'mt-4' }, [mark]),
        ]),
      );
    }
  };
  const load = async () => {
    const res = await api('/api/v1/staff/mensajes');
    if (res.status === 401) { panel.hidden = true; loginForm.hidden = false; return; }
    render(await res.json());
  };

  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    status.textContent = '';
    const data = new FormData(loginForm);
    const res = await api('/api/v1/staff/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: data.get('username'), password: data.get('password') }) });
    if (res.status === 200) {
      csrf = (await res.json()).csrf_token;
      loginForm.reset();
      loginForm.hidden = true;
      panel.hidden = false;
      await load();
    } else {
      status.textContent = res.status === 429 ? 'Demasiados intentos. Espera un minuto.' : 'Credenciales inválidas.';
    }
  });
  doc.getElementById('staff-logout')?.addEventListener('click', async () => {
    await api('/api/v1/staff/logout', { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
    csrf = null;
    panel.hidden = true;
    loginForm.hidden = false;
  });
}
