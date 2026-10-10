import { NextResponse } from "next/server";
import { API, SESSION_COOKIE, sameOrigin } from "@/lib/server";

export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Bad origin" }, { status: 403 });
  const body = await req.json().catch(() => null);
  if (!body?.email || !body?.password) return NextResponse.json({ detail: "Missing credentials" }, { status: 422 });

  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Forwarded-For": req.headers.get("x-forwarded-for") ?? "" },
    body: JSON.stringify({ email: body.email, password: body.password }),
    cache: "no-store",
  });
  if (!res.ok) {
    const status = res.status === 429 ? 429 : 401;
    return NextResponse.json({ detail: status === 429 ? "Too many attempts. Try again shortly." : "Invalid credentials" }, { status });
  }
  const data = await res.json();
  if (data.mfa_required) return NextResponse.json({ mfa_required: true, mfa_token: data.mfa_token });
  const out = NextResponse.json({ user: data.user, tenant: data.tenant });
  out.cookies.set(SESSION_COOKIE, data.access_token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production" && process.env.COOKIE_SECURE !== "false",
    path: "/",
    maxAge: data.expires_in,
  });
  return out;
}
