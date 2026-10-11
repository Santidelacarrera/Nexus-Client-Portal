"use client";
import { LogOut } from "lucide-react";
import { FormEvent, useState } from "react";

async function endSession() {
  await fetch("/api/session/logout", { method: "POST" });
  window.location.assign("/login?changed=1");
}

export function SecurityPanel() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function change(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    if (fd.get("new_password") !== fd.get("confirm")) return setError("The new passwords do not match.");
    setBusy(true);
    setError(null);
    const r = await fetch("/api/backend/auth/password", { method: "POST", body: JSON.stringify({ current_password: fd.get("current_password"), new_password: fd.get("new_password") }) });
    if (r.status === 204) return endSession(); // every session (this one included) was revoked server-side
    setBusy(false);
    const body = await r.json().catch(() => ({}));
    setError(r.status === 429 ? "Too many attempts. Try again later." : body.detail ?? "Could not change the password.");
  }

  async function everywhere() {
    const r = await fetch("/api/backend/auth/logout-all", { method: "POST" });
    if (r.status === 204) return endSession();
    setError("Could not sign out everywhere.");
  }

  return (
    <div className="space-y-5">
      <form onSubmit={change} className="grid max-w-xl gap-3">
        <div>
          <label htmlFor="cur" className="panel-title">Current password</label>
          <input id="cur" name="current_password" type="password" autoComplete="current-password" required className="input mt-1.5" />
        </div>
        <div>
          <label htmlFor="new" className="panel-title">New password (12+ characters)</label>
          <input id="new" name="new_password" type="password" autoComplete="new-password" minLength={12} required className="input mt-1.5" />
        </div>
        <div>
          <label htmlFor="conf" className="panel-title">Confirm new password</label>
          <input id="conf" name="confirm" type="password" autoComplete="new-password" minLength={12} required className="input mt-1.5" />
        </div>
        {error && <p role="alert" className="font-mono text-xs text-crit">{error}</p>}
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={busy} className="btn">{busy ? "Updating…" : "Change password"}</button>
          <span className="font-mono text-[11px] text-slate-500">All sessions on every device are ended.</span>
        </div>
      </form>
      <div className="border-t border-white/5 pt-4">
        <button onClick={everywhere} className="btn btn-ghost"><LogOut className="h-3.5 w-3.5" /> Sign out everywhere</button>
      </div>
    </div>
  );
}
