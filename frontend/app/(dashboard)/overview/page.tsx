import { Bot, ShieldAlert, Wallet } from "lucide-react";
import { LiveFeed } from "@/components/LiveFeed";
import { Topology } from "@/components/Topology";
import { Badge, SeverityBadge } from "@/components/ui/Badge";
import { Gauge } from "@/components/ui/Gauge";
import { Panel } from "@/components/ui/Panel";
import { SEVERITY_ORDER } from "@/lib/format";
import { backend } from "@/lib/server";
import type { Overview } from "@/lib/types";

export const dynamic = "force-dynamic";
const ICON = { security: ShieldAlert, finops: Wallet, ai: Bot } as const;
const VOTE = { approve: "mint", conditional: "warn", reject: "crit" } as const;

export default async function OverviewPage() {
  const ov = await backend<Overview>("/overview");
  return (
    <>
      <h1 className="font-mono text-lg font-bold uppercase tracking-[0.2em] text-slate-100">Service Overview</h1>
      <div className="grid gap-4 md:grid-cols-3">
        {ov.services.map((s) => {
          const Icon = ICON[s.key as keyof typeof ICON];
          const ok = s.status === "operational";
          return (
            <Panel key={s.key} glow={ok ? undefined : undefined} className={ok ? "" : "!border-warn/40"}>
              <div className="flex items-center justify-between">
                <span className="panel-title">{s.name}</span>
                <Icon className={`h-4 w-4 ${ok ? "text-cyan-glow" : "text-warn"}`} />
              </div>
              <div className="metric mt-3 text-2xl text-slate-50">{s.headline}</div>
              <div className="mt-1 flex items-center justify-between font-mono text-xs text-slate-500">
                <span>{s.detail}</span>
                <Badge tone={ok ? "mint" : "warn"}>{s.status}</Badge>
              </div>
            </Panel>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Security posture" className="flex flex-col items-center">
          <Gauge value={ov.posture_score} max={100} threshold={80} label="posture score" format={(v) => v.toFixed(0)} />
          <ul className="mt-3 flex flex-wrap justify-center gap-2">
            {SEVERITY_ORDER.map((s) => (
              <li key={s} className="flex items-center gap-1.5"><SeverityBadge severity={s} /><span className="metric text-sm">{ov.security.open[s]}</span></li>
            ))}
          </ul>
        </Panel>
        <Panel title="Multi-agent consensus" className="lg:col-span-2">
          <ul className="space-y-2">
            {ov.consensus.map((v) => (
              <li key={v.agent} className="flex items-center justify-between gap-3 rounded border border-white/5 bg-void/50 px-3 py-2">
                <div className="min-w-0">
                  <div className="font-mono text-xs text-slate-200">{v.agent}</div>
                  <div className="truncate font-mono text-[11px] text-slate-500">{v.evidence}</div>
                </div>
                <Badge tone={VOTE[v.vote]}>{v.vote}</Badge>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Panel title="Delivery topology" className="lg:col-span-3">
          <Topology degraded={ov.security.open.critical > 0} />
        </Panel>
        <Panel title="Live telemetry" className="lg:col-span-2">
          <LiveFeed max={6} />
        </Panel>
      </div>
    </>
  );
}
