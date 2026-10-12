import createDOMPurify from 'dompurify';
import { createSafeHtml } from '../../src/static/js/safeHtml.js';

test('elimina scripts, manejadores de eventos y estilos en línea', () => {
  const el = document.createElement('div');
  createSafeHtml(createDOMPurify(window))(el, '<p style="x:y" onclick="alert(1)">Hola</p><script>alert(2)</script><img src=x onerror=alert(3)>');
  expect(el.innerHTML).not.toMatch(/script|onclick|onerror|style=/i);
  expect(el.textContent).toContain('Hola');
});

test('neutraliza URLs javascript: y formularios', () => {
  const el = document.createElement('div');
  createSafeHtml(createDOMPurify(window))(el, '<a href="javascript:alert(1)">x</a><form action="https://evil.example"><input></form>');
  expect(el.innerHTML).not.toMatch(/javascript:|<form/i);
});
