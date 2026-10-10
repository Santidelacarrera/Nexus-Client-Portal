import { CostAreaChart, SavingsBars } from "@/components/FinopsCharts";
import { LiveFeed } from "@/components/LiveFeed";
import { LiveSavings } from "@/components/LiveSavings";
import { Panel } from "@/components/ui/Panel";
import { usd } from "@/lib/format";
import { backend } from "@/lib/server";
import type { FinopsPoint, FinopsSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function FinopsPage() {
  const [sum, series] = await Promise.all([backend<FinopsSummary>("/finops/summary"), backend<FinopsPoint[]>("/finops/timeseries")]);
  const max = Math.max(...sum.top_namespaces.map((n) => n.saved_usd), 1);
  return (
    <>
      <h1 className="font-mono text-lg font-bold uppercase tracking-[0.2em] text-slate-100">FinOps · KubeCost Auto-HPA</h1>
      <LiveSavings initial={sum} projected={sum.projected_monthly_saving_usd} events={sum.hpa_scale_events} />
      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Daily cost — static baseline vs HPA right-sized" className="xl:col-span-2"><CostAreaChart data={series} /></Panel>
        <Panel title="Live scaling events"><LiveFeed kinds={["finops"]} max={8} /></Panel>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Daily savings"><SavingsBars data={series} /></Panel>
        <Panel title="Top namespaces by savings">
          <ul className="space-y-3">
            {sum.top_namespaces.map((n) => (
              <li key={n.namespace}>
                <div className="flex justify-between font-mono text-xs"><span className="text-slate-300">{n.namespace}</span><span className="text-mint">{usd(n.saved_usd)}</span></div>
                <div className="mt-1 h-1.5 rounded bg-edge"><div className="h-full rounded bg-gradient-to-r from-cyan to-mint" style={{ width: `${(n.saved_usd / max) * 100}%` }} /></div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}
