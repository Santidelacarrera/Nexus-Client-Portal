"use client";
import { FileText, Send } from "lucide-react";
import { FormEvent, useState } from "react";
import { timeAgo } from "@/lib/format";
import type { AskResult, AskRunSummary } from "@/lib/types";
import { ConsensusStatus } from "./ConsensusStatus";
import { Badge } from "./ui/Badge";
import { Panel } from "./ui/Panel";

const ERRORS: Record<number, string> = {
  429: "You are asking too fast. Try again in a minute.",
  502: "The answer service returned something invalid and was ignored for your safety.",
  503: "The answer service is unavailable right now. Nothing was answered.",
};

export function AskPanel({ initialHistory }: { initialHistory: AskRunSummary[] }) {
  const [result, setResult] = useState<AskResult | null>(null);
  const [history, setHistory] = useState(initialHistory);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const question = String(new FormData(e.currentTarget).get("question") ?? "").trim();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await fetch("/api/backend/ask", { method: "POST", body: JSON.stringify({ question }) });
      if (!r.ok) {
        setError(ERRORS[r.status] ?? (r.status === 422 ? "Please enter a question of 3 to 1000 characters." : "Something went wrong."));
        return;
      }
      const data = (await r.json()) as AskResult;
      setResult(data);
      setHistory((h) => [{ runId: data.runId, createdAt: new Date().toISOString(), question: data.review.question, outcome: data.review.outcome, reasonCodes: data.review.reasons.map((x) => x.code), escalation: data.review.escalation }, ...h].slice(0, 25));
    } finally {
      setBusy(false);
    }
  }

  async function open(id: string) {
    setError(null);
    const r = await fetch(`/api/backend/ask/${id}`);
    if (r.ok) setResult((await r.json()) as AskResult);
    else setError("That run is no longer available.");
  }

  const review = result?.review;
  return (
    <div className="grid gap-5 xl:grid-cols-3">
      <div className="space-y-5 xl:col-span-2">
        <Panel title="Ask your knowledge base">
          <form onSubmit={submit} className="space-y-3">
            <label htmlFor="question" className="sr-only">Question</label>
            <textarea id="question" name="question" required minLength={3} maxLength={1000} rows={3} className="input resize-y" placeholder="e.g. How long are audit logs retained?" />
            <div className="flex items-center justify-between gap-3">
              <p className="font-mono text-[11px] text-slate-500">Answers are released only with unanimous approval of three independent reviewers.</p>
              <button className="btn" type="submit" disabled={busy}><Send className="h-3.5 w-3.5" /> {busy ? "Reviewing…" : "Ask"}</button>
            </div>
          </form>
          {error && <p role="alert" className="mt-3 font-mono text-xs text-crit">{error}</p>}
        </Panel>

        {review && (
          <>
            <Panel title="Committee decision"><ConsensusStatus review={review} /></Panel>
            {review.outcome === "RELEASED" && review.answer && (
              <Panel title="Answer" glow="mint">
                <p className="text-slate-100" data-testid="answer">{review.answer}</p>
              </Panel>
            )}
            {review.sources.length > 0 && (
              <Panel title={`Authorised sources (${review.sources.length})`}>
                <ul className="space-y-2" data-testid="sources">
                  {review.sources.map((s) => (
                    <li key={`${s.docId}-${s.index}`} className="rounded border border-white/5 bg-void/60 p-3">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs">
                        <FileText className="h-3.5 w-3.5 text-cyan-glow" />
                        <span className="text-slate-200">{s.source || s.docId}</span>
                        {s.section && <span className="text-slate-500">§ {s.section}</span>}
                        {s.page !== null && <span className="text-cyan-glow">p.{s.page}</span>}
                        <span className="text-slate-400">chars {s.start}–{s.end}</span>
                        <span className="ml-auto text-slate-500">[{s.index}] relevance {s.score.toFixed(3)}</span>
                      </div>
                      <blockquote className="mt-2 border-l-2 border-cyan/40 pl-3 font-mono text-xs text-slate-400">{s.text}</blockquote>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
          </>
        )}
      </div>

      <Panel title="My recent questions" className="h-fit">
        <ul className="space-y-1.5" data-testid="ask-history">
          {history.map((h) => (
            <li key={h.runId}>
              <button onClick={() => h.outcome !== "ERROR" && open(h.runId)} disabled={h.outcome === "ERROR"} className="w-full rounded border border-white/5 bg-void/50 px-3 py-2 text-left transition hover:border-white/20 disabled:cursor-default disabled:opacity-60">
                <div className="flex items-center justify-between gap-2">
                  <Badge tone={h.outcome === "RELEASED" ? "mint" : h.outcome === "BLOCKED" ? "crit" : "warn"}>{h.outcome.toLowerCase()}</Badge>
                  <time className="font-mono text-[10px] text-slate-600" dateTime={h.createdAt} suppressHydrationWarning>{timeAgo(h.createdAt)}</time>
                </div>
                <div className="mt-1 line-clamp-2 text-sm text-slate-300">{h.question}</div>
              </button>
            </li>
          ))}
          {!history.length && <li className="font-mono text-xs text-slate-500">Nothing asked yet.</li>}
        </ul>
      </Panel>
    </div>
  );
}
