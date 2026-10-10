import { RagInspector } from "@/components/RagInspector";
import { backend } from "@/lib/server";
import type { RagQuery, RagSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function AiRagPage() {
  const [summary, queries] = await Promise.all([backend<RagSummary>("/rag/summary"), backend<RagQuery[]>("/rag/queries?limit=60")]);
  return (
    <>
      <h1 className="font-mono text-lg font-bold uppercase tracking-[0.2em] text-slate-100">ContextRAG Engine · Quality Inspector</h1>
      <RagInspector summary={summary} initial={queries} />
    </>
  );
}
