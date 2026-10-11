import { initBanner } from './banner.js';
import { initContact } from './contact.js';
import { initDialog, initFilters } from './projects.js';
import { createSafeHtml } from './safeHtml.js';
import { initStaff } from './staff.js';

/* DOMPurify solo se descarga si la página tiene vitrina (se importa dinámicamente, del mismo origen). */
initBanner();
initFilters();
initContact();
initStaff();
if (document.getElementById('project-dialog')) {
  import('/static/vendor/purify.es.mjs').then(({ default: DOMPurify }) => initDialog(document, createSafeHtml(DOMPurify)));
}
