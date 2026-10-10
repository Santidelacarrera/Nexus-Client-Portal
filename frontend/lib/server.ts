import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export const SESSION_COOKIE = "nexus_session";
export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
export const API = `${BACKEND_URL}/api/v1`;

export function sessionToken(): string | undefined {
  return cookies().get(SESSION_COOKIE)?.value;
}

/** Server-side call to the FastAPI control plane with the session's bearer token. */
export async function backend<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionToken();
  if (!token) redirect("/login");
  const res = await fetch(`${API}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) redirect("/login?expired=1");
  if (!res.ok) throw new Error(`Backend ${path} → ${res.status}`);
  return (await res.json()) as T;
}

/** Like backend() but returns null on 403 (role lacks access). */
export async function backendOptional<T>(path: string): Promise<T | null> {
  try {
    return await backend<T>(path);
  } catch (e) {
    if (e instanceof Error && e.message.endsWith("403")) return null;
    throw e;
  }
}

/** CSRF defence for cookie-authenticated mutations: require same-origin. */
export function sameOrigin(req: Request): boolean {
  const origin = req.headers.get("origin");
  if (!origin) return false;
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
