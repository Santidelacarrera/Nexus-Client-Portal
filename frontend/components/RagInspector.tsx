"use client";
import { CheckCircle2, FileText, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTelemetry } from "@/lib/store";
import type { RagQuery, RagSummary } from "@/lib/types";
import { TimeAgo } from "./TimeAgo";
import { Badge } from "./ui/Badge";
import { Gauge } from "./ui/Gauge";
import { Panel } from "./ui/Panel";

const THRESHOLD = 0.95;

export function NliBar({ value }: { value: number }) {
  const ok = value >= THRESHOLD;
  return (
    <div className="relative h-1.5 rounded bg-edge" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={value} aria-label="NLI entailment">
      <div className={`h-full rounded ${ok ? "bg-mint" : "bg-warn"}`} style={{ width: `${value * 100}%` }} />
      <span className="absolute -top-0.5 h-2.5 w-px bg-slate-200" style={{ left: `${THRESHOLD * 100}%` }} />
    </div>
  );
}

export function RagInspector({ summary, initial }: { summary: RagSummary; initial: RagQuery[] }) {
  const [extra, setExtra] = useState<RagQuery[]>([]);
  const [filter, setFilter] = useState<"all" | "review">("all");
  const [selId, setSelId] = useState<string | null>(null);

  // Live RAG checks arrive as light feed items; fetch the full record (with sources) on demand.
  useEffect(() => {
    let last: string | undefined;
    return useTelemetry.subscribe((s) => {
      const top = s.feed[0];
      if (top?.kind === "rag" && top.key !== last) {
        last = top.key;
        fetch(`/api/backend/rag/queries/${top.key.slice(2)}`)
          .then((r) => (r.ok ? r.json() : null))
          .then((q: RagQuery | null) => q && setExtra((e) => [q, ...e].slice(0, 30)))
          .catch(() => {});
      }
    });
  }, []);

  const queries = useMemo(() => {
    const seen = new Set(initial.map((q) => q.id));
    return [...extra.filter((q) => !seen.has(q.id)), ...initial].filter((q) => filter === "all" || q.verdict === "review");
  }, [initial, extra, filter]);
  const selected = queries.find((q) => q.id === selId) ?? queries[0];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Mean NLI entailment index" className="flex items-center justify-center"><Gauge value={summary.avg_nli} threshold={THRESHOLD} label={`zero-hallucination ≥ ${THRESHOLD}`} /></Panel>
        <Panel title="Verification distribution (last 200)" className="lg:col-span-2">
          <div className="h-[150px]" role="img" aria-label="Distribution of NLI scores">
            <ResponsiveContainer>
              <BarChart data={summary.distribution}>
                <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="bucket" tick={{ fill: "#64748b", fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="#1f2937" />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} stroke="#1f2937" width={30} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid rgba(6,182,212,.35)", fontFamily: "JetBrains Mono", fontSize: 11 }} cursor={{ fill: "rgba(6,182,212,.08)" }} />
                <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                  {summary.distribution.map((d) => <Cell key={d.bucket} fill={d.bucket.startsWith("0.95") || d.bucket.startsWith("≥") ? "#10b981" : "#f59e0b"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <Panel
          title={`Queries · ${summary.verified_pct}% verified`}
          className="xl:col-span-2"
          action={<button className="btn btn-ghost !px-2 !py-1" onClick={() => setFilter(filter === "all" ? "review" : "all")} aria-pressed={filter === "review"}>{filter === "all" ? "needs review" : "show all"}</button>}
        >
          <ul className="max-h-[560px] space-y-1.5 overflow-y-auto pr-1" data-testid="rag-list">
            {queries.map((q) => (
              <li key={q.id}>
                <button onClick={() => setSelId(q.id)} aria-current={selected?.id === q.id} className={`w-full rounded border px-3 py-2 text-left transition ${selected?.id === q.id ? "border-cyan/50 bg-cyan/10" : "border-white/5 bg-void/50 hover:border-white/20"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className={`metric text-xs ${q.verdict === "verified" ? "text-mint" : "text-warn"}`}>{q.nli_score.toFixed(3)}</span>
                    <TimeAgo iso={q.ts} className="font-mono text-[10px] text-slate-600" />
                  </div>
                  <div className="mt-1 line-clamp-2 text-sm text-slate-300">{q.question}</div>
                </button>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Traceability inspector" className="xl:col-span-3">
          {selected ? (
            <div className="space-y-4" data-testid="rag-detail">
              <div className="flex flex-wrap items-center gap-2">
                {selected.verdict === "verified" ? <Badge tone="mint"><CheckCircle2 className="h-3 w-3" /> verified</Badge> : <Badge tone="warn"><TriangleAlert className="h-3 w-3" /> human review</Badge>}
                <Badge tone="slate">{selected.model}</Badge>
                <Badge tone="slate">{selected.latency_ms} ms</Badge>
              </div>
              <div>
                <div className="panel-title">Question</div>
                <p className="mt-1 text-slate-200">{selected.question}</p>
              </div>
              <div>
                <div className="panel-title">Answer</div>
                <p className="mt-1 text-slate-300">{selected.answer}</p>
                <div className="mt-2"><NliBar value={selected.nli_score} /></div>
                <div className="mt-1 font-mono text-[11px] text-slate-500">NLI {selected.nli_score.toFixed(3)} · threshold {THRESHOLD}</div>
              </div>
              <div>
                <div className="panel-title mb-2">Source coordinates</div>
                <ul className="space-y-2">
                  {selected.sources.map((s) => (
                    <li key={s.id} className="rounded border border-white/5 bg-void/60 p-3">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs">
                        <FileText className="h-3.5 w-3.5 text-cyan-glow" />
                        <span className="text-slate-200">{s.document}</span>
                        <span className="text-cyan-glow">p.{s.page}</span>
                        <span className="text-slate-400">L{s.line_start}–{s.line_end}</span>
                        <span className="ml-auto text-slate-500">sim {s.similarity.toFixed(3)}</span>
                      </div>
                      <blockquote className="mt-2 border-l-2 border-cyan/40 pl-3 font-mono text-xs text-slate-400">{s.snippet}</blockquote>
                      <div className="mt-2"><NliBar value={s.entailment} /></div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : <p className="font-mono text-xs text-slate-500">No queries.</p>}
        </Panel>
      </div>
    </div>
  );
}
