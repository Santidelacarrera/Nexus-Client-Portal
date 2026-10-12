/* Vitrina: filtros por tema (mejora progresiva) y diálogo con el diagrama de cada proyecto. */
export function initFilters(doc = document) {
  const bar = doc.getElementById('project-filters');
  const status = doc.getElementById('filter-status');
  const cards = [...doc.querySelectorAll('[data-project]')];
  if (!bar || cards.length === 0) return;
  bar.hidden = false; // sin JS la barra queda oculta y se ven todos los proyectos

  bar.addEventListener('click', (event) => {
    const button = event.target.closest('[data-filter]');
    if (!button) return;
    const wanted = button.dataset.filter;
    for (const b of bar.querySelectorAll('[data-filter]')) b.setAttribute('aria-pressed', String(b === button));
    let shown = 0;
    for (const card of cards) {
      const match = wanted === 'todos' || card.dataset.categories.split('|').includes(wanted);
      card.hidden = !match;
      if (match) shown += 1;
    }
    if (status) status.textContent = `Mostrando ${shown} de ${cards.length} proyectos`;
  });
}

export function initDialog(doc, setSafeHtml, fetchFn = fetch, win = window) {
  const dialog = doc.getElementById('project-dialog');
  const body = doc.getElementById('dialog-body');
  if (!dialog || !body || typeof dialog.showModal !== 'function') return;

  doc.addEventListener('click', async (event) => {
    const opener = event.target.closest('[data-open-project]');
    if (opener) {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return; // abrir en pestaña nueva
      event.preventDefault();
      try {
        const res = await fetchFn(`/proyectos/${encodeURIComponent(opener.dataset.openProject)}/fragmento`, { headers: { Accept: 'text/html' }, credentials: 'same-origin' });
        if (!res.ok) throw new Error(String(res.status));
        setSafeHtml(body, await res.text());
        dialog.showModal();
      } catch {
        win.location.assign(opener.getAttribute('href')); // la página completa siempre funciona
      }
      return;
    }
    if (event.target === dialog || event.target.closest('[data-close-dialog]')) dialog.close();
  });
}
