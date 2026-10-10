import { ReactNode } from "react";

const TONES = { cyan: "text-cyan-glow", mint: "text-mint", warn: "text-warn", crit: "text-crit", slate: "text-slate-100" } as const;

export function StatTile({ label, value, sub, tone = "slate", icon }: { label: string; value: ReactNode; sub?: ReactNode; tone?: keyof typeof TONES; icon?: ReactNode }) {
  return (
    <div className="panel p-4" data-testid="stat-tile">
      <div className="flex items-center justify-between">
        <span className="panel-title">{label}</span>
        <span className="text-slate-600">{icon}</span>
      </div>
      <div className={`metric mt-2 text-2xl ${TONES[tone]}`}>{value}</div>
      {sub && <div className="mt-1 font-mono text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}
