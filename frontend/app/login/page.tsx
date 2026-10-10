"use client";
import { Activity, Lock } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";

function LoginForm() {
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(params.get("expired") ? "Session expired. Please sign in again." : null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    const res = await fetch("/api/session/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: fd.get("email"), password: fd.get("password") }),
    });
    if (res.ok) {
      window.location.assign("/overview");
      return;
    }
    setBusy(false);
    setError((await res.json().catch(() => ({ detail: "Sign-in failed" }))).detail);
  }

  return (
    <form onSubmit={submit} className="space-y-4" aria-describedby={error ? "login-error" : undefined}>
      <div>
        <label htmlFor="email" className="panel-title">Identity</label>
        <input id="email" name="email" type="email" autoComplete="username" required className="input mt-1.5" placeholder="you@company.com" />
      </div>
      <div>
        <label htmlFor="password" className="panel-title">Passphrase</label>
        <input id="password" name="password" type="password" autoComplete="current-password" required className="input mt-1.5" placeholder="••••••••••••" />
      </div>
      {error && <p id="login-error" role="alert" className="font-mono text-xs text-crit">{error}</p>}
      <button type="submit" disabled={busy} className="btn w-full !py-3">
        <Lock className="h-3.5 w-3.5" /> {busy ? "Authenticating…" : "Establish session"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="panel w-full max-w-md p-8 shadow-neon">
        <div className="mb-8 flex items-center gap-3">
          <Activity className="h-7 w-7 text-cyan-glow" />
          <div>
            <h1 className="font-mono text-xl font-bold tracking-[0.25em] text-slate-50">NEXUS</h1>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500">Client Portal · Security &amp; AI Lab</p>
          </div>
        </div>
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
        <p className="mt-6 border-t border-white/5 pt-4 font-mono text-[10px] leading-relaxed text-slate-600">
          Access is monitored. Sessions are short-lived, tenant-isolated and every action is written to an append-only audit chain.
        </p>
      </div>
    </main>
  );
}
