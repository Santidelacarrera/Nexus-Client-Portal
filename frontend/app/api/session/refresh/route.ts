import { NextResponse } from "next/server";
import { API, SESSION_COOKIE, sameOrigin, sessionToken } from "@/lib/server";

/** Sliding session: exchange the current token for a fresh one (backend enforces the absolute cap). */
export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Bad origin" }, { status: 403 });
  const token = sessionToken();
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const res = await fetch(`${API}/auth/refresh`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, cache: "no-store" });
  if (!res.ok) {
    const out = NextResponse.json({ detail: "Session expired" }, { status: 401 });
    out.cookies.delete(SESSION_COOKIE);
    return out;
  }
  const data = await res.json();
  const out = NextResponse.json({ ok: true });
  out.cookies.set(SESSION_COOKIE, data.access_token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production" && process.env.COOKIE_SECURE !== "false",
    path: "/",
    maxAge: data.expires_in,
  });
  return out;
}
