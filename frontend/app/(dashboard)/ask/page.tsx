import { AskPanel } from "@/components/AskPanel";
import { backend } from "@/lib/server";
import type { AskRunSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function AskPage() {
  const history = await backend<AskRunSummary[]>("/ask");
  return (
    <>
      <h1 className="font-mono text-lg font-bold uppercase tracking-[0.2em] text-slate-100">Ask · Governance Committee</h1>
      <AskPanel initialHistory={history} />
    </>
  );
}
