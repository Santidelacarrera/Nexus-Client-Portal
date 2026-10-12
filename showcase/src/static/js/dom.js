/* Helpers de DOM seguros: todo texto va por textContent (nunca HTML). */
export function el(tag, { text = '', className = '', attrs = {} } = {}, children = []) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const c of children) node.append(c);
  return node;
}
