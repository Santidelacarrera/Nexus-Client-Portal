import { NextResponse } from "next/server";
import { API, SESSION_COOKIE, sameOrigin, sessionToken } from "@/lib/server";

export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Bad origin" }, { status: 403 });
  const token = sessionToken();
  if (token) await fetch(`${API}/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }).catch(() => {});
  const out = NextResponse.json({ ok: true });
  out.cookies.delete(SESSION_COOKIE);
  return out;
}
