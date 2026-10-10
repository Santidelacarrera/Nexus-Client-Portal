"use client";
import { useTelemetry } from "@/lib/store";
import { pct, usd } from "@/lib/format";
import type { Overview } from "@/lib/types";
import { StatTile } from "./ui/StatTile";

/** Hero tiles that update from the WebSocket stream (Δ cost saved) without a refresh. */
export function LiveSavings({ initial, projected, events }: { initial: Overview["finops"]; projected: number; events: number }) {
  const live = useTelemetry((s) => s.finopsTotals);
  const t = live ?? initial;
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatTile label="Δ cost saved · 30d" value={usd(t.saved_usd)} tone="mint" sub={live ? "● live" : "vs static provisioning"} />
      <StatTile label="Saving rate" value={pct(t.saving_pct)} tone="cyan" sub={`${usd(t.actual_usd)} of ${usd(t.baseline_usd)}`} />
      <StatTile label="Projected / month" value={usd(projected)} sub="run-rate extrapolation" />
      <StatTile label="HPA scale events" value={events.toLocaleString("en-US")} sub="replica adjustments" />
    </div>
  );
}
