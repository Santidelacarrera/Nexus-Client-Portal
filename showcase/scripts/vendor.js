/* Copia al directorio estático, sin CDN, las tipografías (SIL OFL) y DOMPurify (Apache-2.0 / MPL-2.0).
 * Auto-alojar evita enviar la IP de la persona a terceros antes de que consienta (Google Fonts lo haría). */
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const out = path.join(root, 'src', 'static');
const nm = (...p) => path.join(root, 'node_modules', ...p);

const copies = [
  [nm('@fontsource-variable/space-grotesk/files/space-grotesk-latin-wght-normal.woff2'), path.join(out, 'fonts', 'space-grotesk-latin.woff2')],
  [nm('@fontsource-variable/plus-jakarta-sans/files/plus-jakarta-sans-latin-wght-normal.woff2'), path.join(out, 'fonts', 'plus-jakarta-sans-latin.woff2')],
  [nm('@fontsource-variable/space-grotesk/LICENSE'), path.join(out, 'fonts', 'LICENSE-space-grotesk.txt')],
  [nm('@fontsource-variable/plus-jakarta-sans/LICENSE'), path.join(out, 'fonts', 'LICENSE-plus-jakarta-sans.txt')],
  [nm('dompurify/dist/purify.es.mjs'), path.join(out, 'vendor', 'purify.es.mjs')],
  [nm('dompurify/LICENSE'), path.join(out, 'vendor', 'LICENSE-dompurify.txt')],
];

for (const [from, to] of copies) {
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
  console.log('vendored', path.relative(root, to));
}
