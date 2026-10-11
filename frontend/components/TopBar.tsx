"use client";
import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useTelemetry } from "@/lib/store";
import { useTelemetryStream } from "@/lib/useTelemetryStream";
import { StatusDot } from "./ui/Badge";

export function TopBar({ tenant, user, role }: { tenant: string; user: string; role: string }) {
  useTelemetryStream();
  const connection = useTelemetry((s) => s.connection);
  const router = useRouter();

  // Keep the 15-minute token fresh while the console is open; the server caps total session age.
  useEffect(() => {
    const t = setInterval(async () => {
      const r = await fetch("/api/session/refresh", { method: "POST" }).catch(() => null);
      if (r && r.status === 401) window.location.assign("/login?expired=1");
    }, 7 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  async function logout() {
    await fetch("/api/session/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-white/[0.06] bg-void/80 px-4 backdrop-blur-md md:px-8">
      <div className="min-w-0">
        <div className="truncate font-mono text-sm font-medium text-slate-100">{tenant}</div>
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500">{role} · {user}</div>
      </div>
      <div className="flex items-center gap-5">
        <StatusDot ok={connection === "live"} label={connection === "live" ? "stream live" : connection} />
        <button onClick={logout} className="btn btn-ghost" aria-label="Sign out">
          <LogOut className="h-3.5 w-3.5" /> Exit
        </button>
      </div>
    </header>
  );
}
