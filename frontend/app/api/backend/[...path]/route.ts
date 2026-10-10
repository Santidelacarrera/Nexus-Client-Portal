import { NextResponse } from "next/server";
import { API, sameOrigin, sessionToken } from "@/lib/server";

// Only these backend areas are reachable from the browser through the BFF.
const ALLOWED = [/^overview$/, /^security\//, /^finops\//, /^rag\//, /^reports(\/|$)/, /^audit(\/|$)/];

async function handle(req: Request, { params }: { params: { path: string[] } }) {
  const path = params.path.join("/");
  if (!ALLOWED.some((r) => r.test(path))) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  if (req.method !== "GET" && !sameOrigin(req)) return NextResponse.json({ detail: "Bad origin" }, { status: 403 });
  const token = sessionToken();
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });

  const url = new URL(req.url);
  const upstream = await fetch(`${API}/${path}${url.search}`, {
    method: req.method,
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  const headers = new Headers();
  for (const h of ["content-type", "content-disposition"]) {
    const v = upstream.headers.get(h);
    if (v) headers.set(h, v);
  }
  headers.set("Cache-Control", "no-store");
  return new NextResponse(upstream.body, { status: upstream.status, headers });
}

export const GET = handle;
export const POST = handle;
