import { activateDeferredScripts, readConsent, saveConsent } from './consent.js';

/** Banner granular. "Rechazar" y "Aceptar" tienen el mismo peso visual (sin patrones oscuros). */
export function initBanner(doc = document, win = window) {
  const banner = doc.getElementById('cookie-banner');
  if (!banner) return null;
  const choices = banner.querySelector('#cookie-choices');
  const customizeBtn = banner.querySelector('[data-consent-action="customize"]');
  const title = banner.querySelector('#cookie-title');
  let opener = null;

  const setChoicesOpen = (open) => {
    choices.classList.toggle('hidden', !open);
    customizeBtn.setAttribute('aria-expanded', String(open));
  };
  const reflect = () => {
    const c = readConsent(win);
    for (const name of ['analytics', 'thirdparty']) {
      const box = choices.querySelector(`input[name="${name}"]`);
      if (box) box.checked = Boolean(c && c.categories[name]);
    }
  };
  const show = ({ focus = false } = {}) => {
    reflect();
    banner.hidden = false;
    if (focus) {
      title.setAttribute('tabindex', '-1');
      title.focus();
    }
  };
  const hide = () => {
    banner.hidden = true;
    setChoicesOpen(false);
    if (opener) {
      opener.focus();
      opener = null;
    }
  };
  const decide = (picked) => {
    const before = readConsent(win);
    saveConsent(picked, win);
    // Un script ya cargado no se puede "descargar": si se retiró un permiso, se recarga para dejar la página limpia.
    const revoked = before && ['analytics', 'thirdparty'].some((k) => before.categories[k] && !picked[k]);
    hide();
    if (revoked) win.location.reload();
  };

  banner.addEventListener('click', (event) => {
    const action = event.target.closest('[data-consent-action]')?.dataset.consentAction;
    if (action === 'accept') decide({ analytics: true, thirdparty: true });
    else if (action === 'reject') decide({ analytics: false, thirdparty: false });
    else if (action === 'customize') setChoicesOpen(choices.classList.contains('hidden'));
  });
  choices.addEventListener('submit', (event) => {
    event.preventDefault();
    const data = new win.FormData(choices);
    decide({ analytics: data.has('analytics'), thirdparty: data.has('thirdparty') });
  });
  doc.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !banner.hidden && readConsent(win)) hide();
  });
  doc.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-open-cookie-preferences]');
    if (!trigger) return;
    opener = trigger;
    setChoicesOpen(true);
    show({ focus: true });
  });

  if (readConsent(win)) activateDeferredScripts(doc, win);
  else show();
  return { show, hide };
}
