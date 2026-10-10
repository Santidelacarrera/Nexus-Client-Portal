import { ReportsPanel } from "@/components/ReportsPanel";
import { Badge } from "@/components/ui/Badge";
import { Panel } from "@/components/ui/Panel";
import { shortHash, timeAgo } from "@/lib/format";
import { backend, backendOptional } from "@/lib/server";
import type { AuditEntry, Report } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const [me, reports, audit, chain] = await Promise.all([
    backend<{ role: string }>("/auth/me"),
    backend<Report[]>("/reports"),
    backendOptional<AuditEntry[]>("/audit?limit=25"),
    backendOptional<{ valid: boolean; entries: number }>("/audit/verify"),
  ]);
  return (
    <>
      <h1 className="font-mono text-lg font-bold uppercase tracking-[0.2em] text-slate-100">Executive Reports &amp; Audit Trail</h1>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Digitally signed reports"><ReportsPanel reports={reports} canGenerate={me.role !== "viewer"} /></Panel>
        <Panel
          title="Immutable audit trail"
          action={chain && <Badge tone={chain.valid ? "mint" : "crit"}>{chain.valid ? `chain intact · ${chain.entries}` : "chain BROKEN"}</Badge>}
        >
          {audit ? (
            <div className="max-h-[560px] overflow-auto">
              <table className="w-full min-w-[460px]" data-testid="audit-table">
                <thead><tr className="border-b border-white/5"><th className="th">When</th><th className="th">Action</th><th className="th">IP</th><th className="th">Hash</th></tr></thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id} className="border-b border-white/[0.04]">
                      <td className="td font-mono text-xs text-slate-500">{timeAgo(a.ts)}</td>
                      <td className="td font-mono text-xs text-slate-200">{a.action}</td>
                      <td className="td font-mono text-xs text-slate-500">{a.ip ?? "—"}</td>
                      <td className="td font-mono text-[11px] text-cyan-glow">{shortHash(a.entry_hash, 6)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="font-mono text-xs text-slate-500">The audit trail is visible to tenant owners only.</p>
          )}
        </Panel>
      </div>
    </>
  );
}
