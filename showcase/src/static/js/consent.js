/* Consentimiento de cookies/almacenamiento: granular, versionado y persistido en localStorage.
 * Regla de oro: NADA opcional se carga antes de una aceptación explícita de su categoría. */
export const STORAGE_KEY = 'nexus_cookie_consent_v1';
export const OPTIONAL_CATEGORIES = ['analytics', 'thirdparty'];

export function currentPolicyVersion(doc = document) {
  const meta = doc.querySelector('meta[name="policy-version"]');
  return meta ? meta.content : '';
}

function storage(win) {
  try {
    return win.localStorage;
  } catch {
    return null; // modo privado estricto o almacenamiento bloqueado: se trata como "sin decisión"
  }
}

/** Decisión vigente o null. Si cambió la versión de la política, la decisión anterior caduca y se vuelve a preguntar. */
export function readConsent(win = window, policy = currentPolicyVersion(win.document)) {
  const store = storage(win);
  if (!store) return null;
  try {
    const raw = store.getItem(STORAGE_KEY);
    if (!raw) return null;
    const c = JSON.parse(raw);
    if (!c || c.v !== 1 || c.policy !== policy || typeof c.categories !== 'object' || c.categories === null) return null;
    return {
      v: 1,
      policy: c.policy,
      ts: c.ts,
      categories: { necessary: true, analytics: c.categories.analytics === true, thirdparty: c.categories.thirdparty === true },
    };
  } catch {
    return null;
  }
}

export function saveConsent(choices, win = window, policy = currentPolicyVersion(win.document)) {
  const record = {
    v: 1,
    policy,
    ts: new Date().toISOString(),
    categories: { necessary: true, analytics: choices.analytics === true, thirdparty: choices.thirdparty === true },
  };
  const store = storage(win);
  if (store) {
    try {
      store.setItem(STORAGE_KEY, JSON.stringify(record));
    } catch {
      /* cuota o bloqueo: la decisión vale solo para esta página */
    }
  }
  win.document.dispatchEvent(new win.CustomEvent('nexus:consent', { detail: record }));
  activateDeferredScripts(win.document, win, record);
  return record;
}

export function isAllowed(category, win = window) {
  if (category === 'necessary') return true;
  const c = readConsent(win);
  return c !== null && c.categories[category] === true;
}

/** Activa los <script type="text/plain" data-consent="..." data-src="..."> cuya categoría fue aceptada.
 * Solo se admiten orígenes propios (la CSP lo exige también). Hoy el sitio no declara ninguno. */
export function activateDeferredScripts(doc = document, win = window, consent = readConsent(win)) {
  const activated = [];
  if (!consent) return activated;
  for (const el of doc.querySelectorAll('script[type="text/plain"][data-consent][data-src]')) {
    if (consent.categories[el.dataset.consent] !== true) continue;
    let url;
    try {
      url = new URL(el.dataset.src, win.location.href);
    } catch {
      continue;
    }
    if (url.origin !== win.location.origin) continue;
    const live = doc.createElement('script');
    live.src = url.href;
    live.async = true;
    el.replaceWith(live);
    activated.push(url.href);
  }
  return activated;
}
