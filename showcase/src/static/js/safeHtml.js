/* ÚNICO módulo autorizado a asignar HTML al DOM, y siempre tras sanear con DOMPurify (ver .eslintrc.js). */
export const SANITIZE_CONFIG = {
  USE_PROFILES: { html: true, svg: true },
  FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'form', 'link', 'meta', 'base'],
  FORBID_ATTR: ['style', 'srcdoc'],
};

export function createSafeHtml(purify) {
  return function setSafeHtml(element, html) {
    element.innerHTML = purify.sanitize(String(html), SANITIZE_CONFIG);
  };
}
