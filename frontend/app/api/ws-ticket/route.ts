import { NextResponse } from "next/server";
import { API, sameOrigin, sessionToken } from "@/lib/server";

export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Bad origin" }, { status: 403 });
  const token = sessionToken();
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const res = await fetch(`${API}/auth/ws-ticket`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, cache: "no-store" });
  if (!res.ok) return NextResponse.json({ detail: "Ticket refused" }, { status: res.status });
  const { ticket } = await res.json();
  return NextResponse.json({ ticket, url: `${process.env.PUBLIC_WS_URL ?? "ws://localhost:8000"}/ws/telemetry` });
}
