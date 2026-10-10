"use client";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { FinopsPoint } from "@/lib/types";
import { usd } from "@/lib/format";

const tip = { background: "#0b1220", border: "1px solid rgba(6,182,212,.35)", borderRadius: 6, fontFamily: "JetBrains Mono, monospace", fontSize: 11 };
const tick = { fill: "#64748b", fontSize: 10, fontFamily: "JetBrains Mono, monospace" };

export function CostAreaChart({ data }: { data: FinopsPoint[] }) {
  return (
    <div className="h-[280px]" role="img" aria-label="Daily baseline versus actual infrastructure cost">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
          <defs>
            <linearGradient id="gBase" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#64748b" stopOpacity={0.35} /><stop offset="100%" stopColor="#64748b" stopOpacity={0} /></linearGradient>
            <linearGradient id="gAct" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#10b981" stopOpacity={0.45} /><stop offset="100%" stopColor="#10b981" stopOpacity={0} /></linearGradient>
          </defs>
          <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={tick} tickFormatter={(d: string) => d.slice(5)} stroke="#1f2937" />
          <YAxis tick={tick} tickFormatter={(v: number) => `$${v}`} stroke="#1f2937" width={52} />
          <Tooltip contentStyle={tip} formatter={(v: number) => usd(v, 2)} />
          <Area type="monotone" dataKey="baseline_usd" name="Static baseline" stroke="#64748b" fill="url(#gBase)" strokeWidth={1.5} />
          <Area type="monotone" dataKey="actual_usd" name="With HPA" stroke="#10b981" fill="url(#gAct)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SavingsBars({ data }: { data: FinopsPoint[] }) {
  return (
    <div className="h-[200px]" role="img" aria-label="Daily savings in USD">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ left: 0, right: 8 }}>
          <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" tick={tick} tickFormatter={(d: string) => d.slice(8)} stroke="#1f2937" />
          <YAxis tick={tick} tickFormatter={(v: number) => `$${v}`} stroke="#1f2937" width={52} />
          <Tooltip contentStyle={tip} formatter={(v: number) => usd(v, 2)} cursor={{ fill: "rgba(6,182,212,.08)" }} />
          <Bar dataKey="saved_usd" name="Saved" fill="#06b6d4" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
