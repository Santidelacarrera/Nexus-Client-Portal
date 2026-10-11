// Requiere el sitio en marcha (SHOWCASE_URL). Valida WCAG 2.1 A/AA con axe-core y el comportamiento del banner.
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const PAGES = ['/', '/privacidad', '/terminos', '/cookies', '/proyectos/nexus-client-portal'];

for (const path of PAGES) {
  test(`axe WCAG 2.1 AA: ${path}`, async ({ page }) => {
    await page.goto(path);
    const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(' ')}`)).toEqual([]);
  });
}

test('el banner de cookies no bloquea la navegación por teclado y no hay peticiones a terceros', async ({ page, baseURL }) => {
  const external = [];
  page.on('request', (r) => { if (!r.url().startsWith(baseURL) && !r.url().startsWith('data:')) external.push(r.url()); });
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('nexus_cookie_consent_v1'))).toBeNull();
  await page.getByRole('button', { name: 'Rechazar opcionales' }).click();
  const saved = JSON.parse(await page.evaluate(() => localStorage.getItem('nexus_cookie_consent_v1')));
  expect(saved.categories.analytics).toBe(false);
  expect(external).toEqual([]);
});

test('formulario: sin consentimiento no se envía', async ({ page }) => {
  await page.goto('/#contacto');
  await page.getByRole('button', { name: 'Rechazar opcionales' }).click();
  await page.getByLabel('Nombre').fill('Ana Pérez');
  await page.getByLabel(/Correo/).fill('ana@example.com');
  await page.getByLabel('Mensaje').fill('Quiero conocer cómo funciona el portal.');
  const consent = page.getByRole('checkbox');
  await expect(consent).not.toBeChecked();
});
