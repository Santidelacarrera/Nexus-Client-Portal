import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "nexus_session";
const PUBLIC = ["/login", "/api/session/login"];

/** Per-request nonce CSP (no 'unsafe-inline' for scripts or stylesheets) + coarse auth gate. */
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const isApi = pathname.startsWith("/api/");
  if (!PUBLIC.includes(pathname) && !req.cookies.get(SESSION_COOKIE)) {
    if (isApi) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
    return NextResponse.redirect(new URL("/login", req.url));
  }

  const nonce = btoa(crypto.randomUUID());
  const dev = process.env.NODE_ENV !== "production";
  let wsOrigin = "";
  try {
    wsOrigin = new URL(process.env.PUBLIC_WS_URL ?? "ws://localhost:8000").origin;
  } catch {}
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' ${dev ? "'unsafe-inline'" : `'nonce-${nonce}'`}`,
    // Style *attributes* only (Recharts/React Flow set inline geometry); attributes cannot execute script.
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self' ${wsOrigin}${dev ? " ws://localhost:3000" : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(dev || process.env.COOKIE_SECURE === "false" ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");

  const headers = new Headers(req.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const res = NextResponse.next({ request: { headers } });
  res.headers.set("Content-Security-Policy", csp);
  res.headers.set("Cache-Control", "no-store");
  return res;
}

export const config = {
  matcher: [{ source: "/((?!_next/static|_next/image|favicon.ico).*)" }],
};
