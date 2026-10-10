import { NextResponse } from "next/server";
import { SESSION_COOKIE, sameOrigin } from "@/lib/server";

export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Bad origin" }, { status: 403 });
  const out = NextResponse.json({ ok: true });
  out.cookies.delete(SESSION_COOKIE);
  return out;
}
