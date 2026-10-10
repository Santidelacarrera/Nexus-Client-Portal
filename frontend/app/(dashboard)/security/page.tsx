import { FindingsTable } from "@/components/FindingsTable";
import { LiveFeed } from "@/components/LiveFeed";
import { Badge } from "@/components/ui/Badge";
import { Panel } from "@/components/ui/Panel";
import { StatTile } from "@/components/ui/StatTile";
import { SEVERITY_ORDER, timeAgo } from "@/lib/format";
import { backend } from "@/lib/server";
import type { ApiEndpoint, Finding, Overview } from "@/lib/types";

export const dynamic = "force-dynamic";
const TONE = { critical: "crit", high: "warn", medium: "cyan", low: "slate" } as const;
const ST = { documented: "mint", shadow: "crit", drift: "warn" } as const;

export default async function SecurityPage() {
  const [findings, endpoints, ov] = await Promise.all([
    backend<Finding[]>("/security/findings?limit=200"),
    backend<ApiEndpoint[]>("/security/endpoints"),
    backend<Overview>("/overview"),
  ]);
  const flagged = endpoints.filter((e) => e.status !== "documented");
  return (
    <>
      <h1 className="font-mono text-lg font-bold uppercase tracking-[0.2em] text-slate-100">ShadowAPI Guard</h1>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {SEVERITY_ORDER.map((s) => (
          <StatTile key={s} label={`open · ${s}`} value={ov.security.open[s]} tone={TONE[s]} sub={s === "critical" || s === "high" ? "BOLA / IDOR priority" : undefined} />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Findings (BOLA · IDOR · drift)" className="xl:col-span-2"><FindingsTable initial={findings} /></Panel>
        <div className="space-y-4">
          <Panel title="Live detections"><LiveFeed kinds={["finding"]} max={8} /></Panel>
          <Panel title={`Shadow & drifted endpoints (${flagged.length})`}>
            <ul className="space-y-1.5">
              {flagged.map((e) => (
                <li key={e.id} className="flex items-center justify-between gap-2 rounded border border-white/5 bg-void/50 px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate font-mono text-xs text-slate-200"><span className="text-cyan-glow">{e.method}</span> {e.path}</div>
                    <div className="font-mono text-[10px] text-slate-600">{e.calls_24h.toLocaleString()} calls/24h · {timeAgo(e.last_seen)}</div>
                  </div>
                  <Badge tone={ST[e.status]}>{e.status}</Badge>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </>
  );
}
