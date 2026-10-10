import { MfaPanel } from "@/components/MfaPanel";
import { Panel } from "@/components/ui/Panel";
import { backend } from "@/lib/server";

export const dynamic = "force-dynamic";

export default async function AccountPage() {
  const [me, mfa] = await Promise.all([
    backend<{ email: string; full_name: string; role: string }>("/auth/me"),
    backend<{ enabled: boolean; recovery_codes_left: number }>("/auth/mfa/status"),
  ]);
  return (
    <>
      <h1 className="font-mono text-lg font-bold uppercase tracking-[0.2em] text-slate-100">Account &amp; MFA</h1>
      <Panel title="Identity">
        <dl className="grid gap-2 font-mono text-sm sm:grid-cols-3">
          <div><dt className="panel-title">Name</dt><dd className="mt-1 text-slate-200">{me.full_name}</dd></div>
          <div><dt className="panel-title">Email</dt><dd className="mt-1 text-slate-200">{me.email}</dd></div>
          <div><dt className="panel-title">Role</dt><dd className="mt-1 text-slate-200">{me.role}</dd></div>
        </dl>
      </Panel>
      <Panel title="Multi-factor authentication"><MfaPanel initialEnabled={mfa.enabled} recoveryLeft={mfa.recovery_codes_left} /></Panel>
    </>
  );
}
