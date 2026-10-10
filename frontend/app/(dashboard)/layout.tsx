import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { backend } from "@/lib/server";
import type { Overview } from "@/lib/types";

interface Me { full_name: string; role: string }

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [me, ov] = await Promise.all([backend<Me>("/auth/me"), backend<Overview>("/overview")]);
  return (
    <div className="min-h-screen md:pl-60">
      <Sidebar />
      <TopBar tenant={ov.tenant.name} user={me.full_name} role={me.role} />
      <main className="mx-auto max-w-[1400px] space-y-5 p-4 md:p-8">{children}</main>
    </div>
  );
}
