"use client";
import { ShieldCheck } from "lucide-react";
import QRCode from "qrcode";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Badge } from "./ui/Badge";

type Phase = "idle" | "enrolling" | "codes";

async function call<T>(path: string, body?: unknown): Promise<{ ok: boolean; status: number; data?: T }> {
  const r = await fetch(`/api/backend/auth/mfa/${path}`, { method: body === undefined ? "GET" : "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  return { ok: r.ok, status: r.status, data: r.status === 204 ? undefined : ((await r.json().catch(() => undefined)) as T | undefined) };
}

export function MfaPanel({ initialEnabled, recoveryLeft }: { initialEnabled: boolean; recoveryLeft: number }) {
  const router = useRouter();
  const [enabled, setEnabled] = useState(initialEnabled);
  const [phase, setPhase] = useState<Phase>("idle");
  const [setup, setSetup] = useState<{ secret: string; uri: string; qr: string } | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setError(null);
    const r = await call<{ secret: string; uri: string }>("setup", {});
    if (!r.ok || !r.data) return setError("Could not start enrolment.");
    setSetup({ ...r.data, qr: await QRCode.toDataURL(r.data.uri, { margin: 1, width: 192, color: { dark: "#e2e8f0", light: "#0b1220" } }) });
    setPhase("enrolling");
  }

  async function confirm(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code"));
    const r = await call<{ recovery_codes: string[] }>("enable", { code });
    if (!r.ok || !r.data) return setError("That code is not valid. Check your device clock and try again.");
    // Policy-confined sessions get a fresh, unconfined token once MFA is on.
    await fetch("/api/session/refresh", { method: "POST" });
    router.refresh();
    setCodes(r.data.recovery_codes);
    setEnabled(true);
    setSetup(null);
    setPhase("codes");
    setError(null);
  }

  async function disable(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code"));
    const r = await call("disable", { code });
    if (!r.ok) return setError("Invalid code.");
    setEnabled(false);
    setPhase("idle");
    setError(null);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <ShieldCheck className={`h-5 w-5 ${enabled ? "text-mint" : "text-slate-500"}`} />
        <span className="text-sm text-slate-300">Time-based one-time passwords (TOTP, RFC 6238)</span>
        <Badge tone={enabled ? "mint" : "warn"}>{enabled ? "enabled" : "not enabled"}</Badge>
      </div>
      {error && <p role="alert" className="font-mono text-xs text-crit">{error}</p>}

      {phase === "codes" && (
        <div className="rounded border border-warn/40 bg-warn/5 p-4" data-testid="recovery-codes">
          <p className="panel-title text-warn">Recovery codes — shown once</p>
          <p className="mt-1 text-sm text-slate-400">Store these somewhere safe. Each works a single time if you lose your authenticator.</p>
          <ul className="mt-3 grid grid-cols-2 gap-2 font-mono text-sm text-slate-100 sm:grid-cols-4">{codes.map((c) => <li key={c} className="rounded border border-white/10 bg-void/70 px-2 py-1 text-center">{c}</li>)}</ul>
          <button className="btn btn-ghost mt-3" onClick={() => setPhase("idle")}>I saved them</button>
        </div>
      )}

      {!enabled && phase === "idle" && <button className="btn" onClick={start}>Enable MFA</button>}

      {phase === "enrolling" && setup && (
        <div className="grid gap-4 sm:grid-cols-[200px_1fr]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={setup.qr} alt="QR code for your authenticator app" width={192} height={192} className="rounded border border-white/10" />
          <form onSubmit={confirm} className="space-y-3">
            <p className="text-sm text-slate-400">Scan the QR with an authenticator app, or enter the key manually:</p>
            <code className="block break-all rounded border border-white/10 bg-void/70 p-2 font-mono text-xs text-cyan-glow" data-testid="mfa-secret">{setup.secret}</code>
            <label htmlFor="mfa-code" className="panel-title block">6-digit code</label>
            <input id="mfa-code" name="code" inputMode="numeric" pattern="\d{6}" maxLength={6} required className="input max-w-[200px] tracking-[0.3em]" placeholder="123456" />
            <button className="btn" type="submit">Confirm &amp; enable</button>
          </form>
        </div>
      )}

      {enabled && phase === "idle" && (
        <form onSubmit={disable} className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="dis-code" className="panel-title block">Authenticator or recovery code</label>
            <input id="dis-code" name="code" required minLength={6} className="input mt-1.5 max-w-[220px]" placeholder="123456" />
          </div>
          <button className="btn btn-ghost" type="submit">Disable MFA</button>
          <span className="font-mono text-[11px] text-slate-500">{recoveryLeft} recovery codes remaining at load</span>
        </form>
      )}
    </div>
  );
}
