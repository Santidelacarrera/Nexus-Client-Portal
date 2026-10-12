import { STORAGE_KEY, readConsent, saveConsent, isAllowed, activateDeferredScripts } from '../../src/static/js/consent.js';

const POLICY = '2026-10-borrador-1';

beforeEach(() => {
  window.localStorage.clear();
  document.head.innerHTML = `<meta name="policy-version" content="${POLICY}">`;
  document.body.innerHTML = '';
});

test('sin decisión previa no se permite nada opcional', () => {
  expect(readConsent()).toBeNull();
  expect(isAllowed('analytics')).toBe(false);
  expect(isAllowed('thirdparty')).toBe(false);
  expect(isAllowed('necessary')).toBe(true);
});

test('guardar persiste en localStorage con versión y marca de tiempo', () => {
  const rec = saveConsent({ analytics: true });
  const raw = JSON.parse(window.localStorage.getItem(STORAGE_KEY));
  expect(raw.policy).toBe(POLICY);
  expect(Number.isNaN(Date.parse(raw.ts))).toBe(false);
  expect(rec.categories).toEqual({ necessary: true, analytics: true, thirdparty: false });
});

test('solo true estricto concede una categoría', () => {
  saveConsent({ analytics: 'true', thirdparty: 1 });
  expect(isAllowed('analytics')).toBe(false);
  expect(isAllowed('thirdparty')).toBe(false);
});

test('un cambio de versión de la política invalida la decisión anterior', () => {
  saveConsent({ analytics: true });
  document.querySelector('meta[name="policy-version"]').content = 'otra-version';
  expect(readConsent()).toBeNull();
});

test('JSON corrupto o manipulado se trata como sin decisión', () => {
  window.localStorage.setItem(STORAGE_KEY, '{no es json');
  expect(readConsent()).toBeNull();
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ v: 1, policy: POLICY, categories: null }));
  expect(readConsent()).toBeNull();
});

test('los scripts diferidos no se activan sin consentimiento y solo se activan de origen propio', () => {
  document.body.innerHTML = `
    <script type="text/plain" data-consent="analytics" data-src="/static/js/a.js"></script>
    <script type="text/plain" data-consent="analytics" data-src="https://tracker.example/t.js"></script>`;
  expect(activateDeferredScripts(document, window)).toEqual([]);
  saveConsent({ analytics: true });
  const live = [...document.querySelectorAll('script[src]')].map((s) => new URL(s.src).origin);
  expect(live.every((o) => o === window.location.origin)).toBe(true);
  expect(document.querySelectorAll('script[src*="tracker.example"]').length).toBe(0);
});

test('el evento nexus:consent se emite al decidir', () => {
  const seen = jest.fn();
  document.addEventListener('nexus:consent', seen);
  saveConsent({});
  expect(seen).toHaveBeenCalledTimes(1);
});
