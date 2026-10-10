"use client";
import { Fragment, useMemo, useState } from "react";
import { SEVERITY_ORDER } from "@/lib/format";
import { useTelemetry } from "@/lib/store";
import type { Finding, Severity } from "@/lib/types";
import { TimeAgo } from "./TimeAgo";
import { Badge, SeverityBadge } from "./ui/Badge";

const STATUS_TONE = { open: "crit", mitigating: "warn", resolved: "mint" } as const;
const RANK: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export function FindingsTable({ initial }: { initial: Finding[] }) {
  const live = useTelemetry((s) => s.liveFindings);
  const [sev, setSev] = useState<Severity | "all">("all");
  const [hideResolved, setHideResolved] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  const rows = useMemo(() => {
    const seen = new Set(initial.map((f) => f.id));
    const merged = [...live.filter((f) => !seen.has(f.id)), ...initial];
    return merged
      .filter((f) => (sev === "all" || f.severity === sev) && (!hideResolved || f.status !== "resolved"))
      .sort((a, b) => RANK[a.severity] - RANK[b.severity] || +new Date(b.detected_at) - +new Date(a.detected_at))
      .slice(0, 80);
  }, [initial, live, sev, hideResolved]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {(["all", ...SEVERITY_ORDER] as const).map((s) => (
          <button key={s} onClick={() => setSev(s)} aria-pressed={sev === s} className={`btn ${sev === s ? "" : "btn-ghost"} !px-2.5 !py-1`}>{s}</button>
        ))}
        <label className="ml-auto flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-slate-400">
          <input type="checkbox" checked={hideResolved} onChange={(e) => setHideResolved(e.target.checked)} className="accent-cyan-500" /> hide resolved
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px]" data-testid="findings-table">
          <thead><tr className="border-b border-white/5"><th className="th">Sev</th><th className="th">Class</th><th className="th">Endpoint</th><th className="th">CVSS</th><th className="th">Status</th><th className="th">Detected</th></tr></thead>
          <tbody>
            {rows.map((f) => (
              <Fragment key={f.id}>
                <tr onClick={() => setOpen(open === f.id ? null : f.id)} className="cursor-pointer border-b border-white/[0.04] transition hover:bg-cyan/5">
                  <td className="td"><SeverityBadge severity={f.severity} /></td>
                  <td className="td font-mono text-xs text-slate-300">{f.category}</td>
                  <td className="td font-mono text-xs"><span className="text-cyan-glow">{f.method}</span> <span className="text-slate-300">{f.endpoint}</span></td>
                  <td className="td metric text-xs">{f.cvss.toFixed(1)}</td>
                  <td className="td"><Badge tone={STATUS_TONE[f.status]}>{f.status}</Badge></td>
                  <td className="td whitespace-nowrap font-mono text-xs text-slate-500"><TimeAgo iso={f.detected_at} /></td>
                </tr>
                {open === f.id && (
                  <tr className="bg-void/60">
                    <td colSpan={6} className="px-4 py-3">
                      <p className="text-sm text-slate-300">{f.title}</p>
                      <p className="mt-1 text-sm text-slate-500">{f.description}</p>
                      <pre className="mt-2 overflow-x-auto rounded border border-white/5 bg-black/40 p-3 font-mono text-[11px] text-mint">{JSON.stringify(f.evidence, null, 2)}</pre>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {!rows.length && <tr><td colSpan={6} className="td text-center font-mono text-xs text-slate-500">No findings match.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
