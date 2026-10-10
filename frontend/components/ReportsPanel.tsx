"use client";
import { Download, FilePlus2, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { shortHash } from "@/lib/format";
import type { Report } from "@/lib/types";
import { TimeAgo } from "./TimeAgo";
import { Badge } from "./ui/Badge";

type Verify = { valid: boolean; sha256_match: boolean; signature_valid: boolean };

export function ReportsPanel({ reports, canGenerate }: { reports: Report[]; canGenerate: boolean }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Record<string, Verify | "error">>({});
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    const r = await fetch("/api/backend/reports/generate", { method: "POST" });
    setBusy(false);
    if (!r.ok) return setError(r.status === 403 ? "Your role cannot generate reports." : "Generation failed.");
    start(() => router.refresh());
  }

  async function verify(id: string) {
    const r = await fetch(`/api/backend/reports/${id}/verify`);
    const body: Verify | "error" = r.ok ? ((await r.json()) as Verify) : "error";
    setResults((m) => ({ ...m, [id]: body }));
    start(() => router.refresh());
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="font-mono text-xs text-slate-500">Encrypted at rest (AES-256-GCM, per-tenant key) · signed RSA-PSS/SHA-256</p>
        {canGenerate && (
          <button className="btn" onClick={generate} disabled={busy || pending}>
            <FilePlus2 className="h-3.5 w-3.5" /> {busy ? "Signing…" : "Generate report"}
          </button>
        )}
      </div>
      {error && <p role="alert" className="mb-2 font-mono text-xs text-crit">{error}</p>}
      <ul className="space-y-2" data-testid="report-list">
        {reports.map((r) => {
          const v = results[r.id];
          return (
            <li key={r.id} className="rounded-md border border-white/5 bg-void/50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm text-slate-100">{r.title}</div>
                  <div className="font-mono text-[11px] text-slate-500"><TimeAgo iso={r.created_at} /> · consensus {(r.consensus * 100).toFixed(0)}%</div>
                </div>
                <div className="flex items-center gap-2">
                  {v && v !== "error" && <Badge tone={v.valid ? "mint" : "crit"}>{v.valid ? "signature valid" : "TAMPERED"}</Badge>}
                  {v === "error" && <Badge tone="warn">verify failed</Badge>}
                  {canGenerate && <button className="btn btn-ghost !px-2.5 !py-1.5" onClick={() => verify(r.id)}><ShieldCheck className="h-3.5 w-3.5" /> Verify</button>}
                  {canGenerate && <a className="btn !px-2.5 !py-1.5" href={`/api/backend/reports/${r.id}/download`}><Download className="h-3.5 w-3.5" /> Signed JSON</a>}
                </div>
              </div>
              <dl className="mt-2 grid gap-x-6 gap-y-1 font-mono text-[10px] text-slate-600 sm:grid-cols-2">
                <div className="flex gap-2"><dt>sha256</dt><dd className="truncate text-slate-400">{shortHash(r.sha256, 14)}</dd></div>
                <div className="flex gap-2"><dt>key</dt><dd className="truncate text-slate-400">{r.key_id}</dd></div>
                <div className="flex gap-2 sm:col-span-2"><dt>signer</dt><dd className="truncate text-slate-400">{r.signer}</dd></div>
              </dl>
            </li>
          );
        })}
        {!reports.length && <li className="font-mono text-xs text-slate-500">No reports yet.</li>}
      </ul>
    </div>
  );
}
