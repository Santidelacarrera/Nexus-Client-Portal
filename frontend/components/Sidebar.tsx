"use client";
import { Activity, Bot, FileCheck2, Gauge, ShieldAlert, Wallet } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export const NAV = [
  { href: "/overview", label: "Overview", icon: Gauge },
  { href: "/security", label: "ShadowAPI Guard", icon: ShieldAlert },
  { href: "/finops", label: "FinOps · KubeCost", icon: Wallet },
  { href: "/ai-rag", label: "ContextRAG", icon: Bot },
  { href: "/reports", label: "Reports & Audit", icon: FileCheck2 },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-white/[0.06] bg-void/90 backdrop-blur-md md:flex">
      <div className="flex h-16 items-center gap-2.5 border-b border-white/[0.06] px-5">
        <Activity className="h-5 w-5 text-cyan-glow" />
        <div className="leading-tight">
          <div className="font-mono text-sm font-bold tracking-widest text-slate-100">NEXUS</div>
          <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-slate-500">Security &amp; AI Lab</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 p-3" aria-label="Primary">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = path === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`group flex items-center gap-3 rounded-md border px-3 py-2.5 font-mono text-xs uppercase tracking-wider transition duration-150 ${
                active ? "border-cyan/40 bg-cyan/10 text-cyan-glow shadow-neon" : "border-transparent text-slate-400 hover:border-white/10 hover:bg-white/5 hover:text-slate-100"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-white/[0.06] p-4 font-mono text-[10px] leading-relaxed text-slate-600">
        zero-trust session
        <br />
        tenant-isolated · RLS enforced
      </div>
    </aside>
  );
}
