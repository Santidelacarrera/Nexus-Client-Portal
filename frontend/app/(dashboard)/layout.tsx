import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { backend } from "@/lib/server";
interface Me { full_name: string; role: string; tenant_name: string }

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const me = await backend<Me>("/auth/me");
  return (
    <div className="min-h-screen md:pl-60">
      <Sidebar />
      <TopBar tenant={me.tenant_name} user={me.full_name} role={me.role} />
      <main className="mx-auto max-w-[1400px] space-y-5 p-4 md:p-8">{children}</main>
    </div>
  );
}
