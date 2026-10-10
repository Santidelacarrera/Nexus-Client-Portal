"use client";
import { TimeAgo } from "./TimeAgo";
import { useTelemetry } from "@/lib/store";

const DOT = { crit: "bg-crit", warn: "bg-warn", mint: "bg-mint", cyan: "bg-cyan" } as const;

export function LiveFeed({ kinds, max = 12 }: { kinds?: ("finding" | "finops" | "rag")[]; max?: number }) {
  const feed = useTelemetry((s) => s.feed);
  const items = feed.filter((i) => !kinds || kinds.includes(i.kind)).slice(0, max);
  if (!items.length) return <p className="font-mono text-xs text-slate-500">Awaiting telemetry…</p>;
  return (
    <ul className="space-y-1.5" aria-live="polite" data-testid="live-feed">
      {items.map((i) => (
        <li key={i.key} className="flex animate-slideIn items-start gap-3 rounded border border-white/5 bg-void/50 px-3 py-2">
          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${DOT[i.tone]}`} />
          <div className="min-w-0 flex-1">
            <div className="font-mono text-[11px] uppercase tracking-wider text-slate-300">{i.title}</div>
            <div className="truncate font-mono text-xs text-slate-500">{i.detail}</div>
          </div>
          <TimeAgo iso={i.ts} className="shrink-0 font-mono text-[10px] text-slate-600" />
        </li>
      ))}
    </ul>
  );
}
