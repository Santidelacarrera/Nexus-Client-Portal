import { NextResponse } from "next/server";
import { API, SESSION_COOKIE, sameOrigin } from "@/lib/server";

/** Second login step: exchange the 5-minute challenge + TOTP/recovery code for a session cookie. */
export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Bad origin" }, { status: 403 });
  const body = await req.json().catch(() => null);
  if (!body?.mfa_token || !body?.code) return NextResponse.json({ detail: "Missing code" }, { status: 422 });
  const res = await fetch(`${API}/auth/mfa/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mfa_token: body.mfa_token, code: String(body.code) }),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = res.status === 429 ? "Too many attempts. Try again later." : res.status === 401 ? (await res.json().catch(() => ({}))).detail ?? "Invalid code" : "Verification failed";
    return NextResponse.json({ detail }, { status: res.status === 429 ? 429 : 401 });
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
