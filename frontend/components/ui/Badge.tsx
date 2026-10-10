import type { Severity } from "@/lib/types";

const SEV: Record<Severity, string> = {
  critical: "border-crit/50 bg-crit/10 text-crit",
  high: "border-warn/50 bg-warn/10 text-warn",
  medium: "border-cyan/40 bg-cyan/10 text-cyan-glow",
  low: "border-slate-500/40 bg-slate-500/10 text-slate-400",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`chip ${SEV[severity]}`}>{severity}</span>;
}

const TONE = {
  mint: "border-mint/40 bg-mint/10 text-mint",
  warn: "border-warn/50 bg-warn/10 text-warn",
  crit: "border-crit/50 bg-crit/10 text-crit",
  cyan: "border-cyan/40 bg-cyan/10 text-cyan-glow",
  slate: "border-slate-500/40 bg-slate-500/10 text-slate-400",
} as const;

export function Badge({ tone = "slate", children }: { tone?: keyof typeof TONE; children: React.ReactNode }) {
  return <span className={`chip ${TONE[tone]}`}>{children}</span>;
}

export function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-slate-400">
      <span className={`h-2 w-2 rounded-full ${ok ? "bg-mint animate-pulseDot shadow-[0_0_8px_#10b981]" : "bg-warn shadow-[0_0_8px_#f59e0b]"}`} />
      {label}
    </span>
  );
}
