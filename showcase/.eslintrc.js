/* ESLint 8 (config clásica). Seguridad: eslint-plugin-security. Accesibilidad: eslint-plugin-jsx-a11y.
 * Nota honesta: las reglas jsx-a11y solo analizan JSX; este sitio usa HTML en plantillas Jinja2, cuya accesibilidad
 * se verifica con axe-core (tests/e2e/a11y.spec.js) y con tests/test_a11y_templates.py. El plugin queda activo por si se añade JSX. */
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true, jest: true },
  parserOptions: { ecmaVersion: 2022, sourceType: 'module' },
  plugins: ['security', 'jsx-a11y'],
  extends: ['eslint:recommended', 'plugin:security/recommended', 'plugin:jsx-a11y/recommended'],
  rules: {
    'no-eval': 'error',
    'no-implied-eval': 'error',
    'no-new-func': 'error',
    'no-script-url': 'error',
    'no-restricted-properties': [
      'error',
      { property: 'innerHTML', message: 'Usa textContent o inserta HTML solo tras DOMPurify (ver safeHtml.js).' },
      { property: 'outerHTML', message: 'No inyectes HTML sin sanear.' },
      { property: 'insertAdjacentHTML', message: 'No inyectes HTML sin sanear.' },
    ],
    'security/detect-object-injection': 'off', // genera ruido con índices de arrays controlados; revisado manualmente
  },
  overrides: [
    // Único lugar autorizado a asignar HTML: el módulo que lo sanea con DOMPurify.
    { files: ['src/static/js/safeHtml.js'], rules: { 'no-restricted-properties': 'off' } },
    { files: ['scripts/**/*.js', 'tests/**/*.js', '*.config.js', '.eslintrc.js'], env: { node: true }, rules: { 'security/detect-non-literal-fs-filename': 'off' } },
    // Las pruebas construyen DOM de ejemplo; no es código de producción.
    { files: ['tests/js/**/*.js'], env: { jest: true }, rules: { 'no-restricted-properties': 'off' } },
  ],
};
