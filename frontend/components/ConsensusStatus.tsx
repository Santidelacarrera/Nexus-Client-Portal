import { CheckCircle2, OctagonX, ShieldAlert, UserRoundCheck } from "lucide-react";
import { AGENTS, AGENT_ORDER, reasonText } from "@/lib/consensus";
import type { AnswerReview, Verdict } from "@/lib/types";
import { Badge, SeverityBadge } from "./ui/Badge";

function VoteCard({ agent, verdict, faulted }: { agent: keyof typeof AGENTS; verdict?: Verdict; faulted: boolean }) {
  const meta = AGENTS[agent];
  const tone = !verdict ? "warn" : verdict.vote === "approve" ? "mint" : "crit";
  return (
    <li className={`rounded-md border p-3 ${!verdict ? "border-warn/40 bg-warn/5" : verdict.vote === "approve" ? "border-mint/30 bg-mint/5" : "border-crit/40 bg-crit/5"}`} data-testid={`vote-${agent}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-slate-100">{meta.name}</span>
        <Badge tone={tone}>{verdict ? verdict.vote : faulted ? "no response" : "absent"}</Badge>
      </div>
      <p className="mt-1 text-xs text-slate-500">{meta.role}</p>
      {verdict && (
        <>
          <div className="mt-2 h-1.5 rounded bg-edge" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={verdict.score} aria-label={`${meta.name} score`}>
            <div className={`h-full rounded ${verdict.vote === "approve" ? "bg-mint" : "bg-crit"}`} style={{ width: `${verdict.score * 100}%` }} />
          </div>
          <p className="mt-2 text-sm text-slate-300">{verdict.rationale}</p>
          {verdict.findings.length > 0 && (
            <ul className="mt-2 space-y-1">
              {verdict.findings.map((f, i) => (
                <li key={`${f.code}-${i}`} className="flex items-start gap-2 font-mono text-[11px] text-slate-400">
                  <SeverityBadge severity={f.severity === "info" ? "low" : f.severity} />
                  <span><span className="text-slate-200">{f.code}</span> — {f.detail}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </li>
  );
}

/** The committee's decision: outcome, each member's vote, and — only when blocked — why. Never renders a blocked answer. */
export function ConsensusStatus({ review }: { review: AnswerReview }) {
  const released = review.outcome === "RELEASED";
  const faulted = review.reasons.some((r) => r.code.startsWith("agent_fault:"));
  const vetoed = review.reasons.some((r) => r.code === "tenant_security_veto" || r.code === "tenant_mismatch");
  return (
    <div className="space-y-4" data-testid="consensus-status">
      <div className={`flex flex-wrap items-center gap-3 rounded-md border p-3 ${released ? "border-mint/40 bg-mint/10" : "border-crit/40 bg-crit/10"}`}>
        {released ? <CheckCircle2 className="h-5 w-5 text-mint" /> : vetoed ? <ShieldAlert className="h-5 w-5 text-crit" /> : <OctagonX className="h-5 w-5 text-crit" />}
        <div className="flex-1">
          <div className="font-mono text-sm font-bold uppercase tracking-widest text-slate-100" data-testid="outcome">{released ? "Released — unanimous approval" : "Blocked — answer withheld"}</div>
          <div className="font-mono text-[11px] text-slate-400">
            {released ? "All three committee members approved." : vetoed ? "Security veto: no content is shown." : "The committee did not reach unanimous approval."}
          </div>
        </div>
        {review.escalation && <Badge tone="warn"><UserRoundCheck className="h-3 w-3" /> needs human review</Badge>}
      </div>

      <ul className="grid gap-3 md:grid-cols-3">
        {AGENT_ORDER.map((id) => (
          <VoteCard key={id} agent={id} verdict={review.votes.find((v) => v.agent === id)} faulted={faulted} />
        ))}
      </ul>

      {!released && review.reasons.length > 0 && (
        <section aria-label="Why it was blocked">
          <h3 className="panel-title mb-2">Why it was blocked</h3>
          <ul className="space-y-1.5" data-testid="reasons">
            {review.reasons.map((r, i) => (
              <li key={`${r.code}-${i}`} className="flex items-start gap-2 rounded border border-white/5 bg-void/50 px-3 py-2">
                <SeverityBadge severity={r.severity === "info" ? "low" : r.severity} />
                <div className="text-sm text-slate-300">{reasonText(r.code)}<span className="ml-2 font-mono text-[11px] text-slate-600">{r.code}{r.agent ? ` · ${AGENTS[r.agent].name}` : ""}</span></div>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="font-mono text-[10px] text-slate-600">
        retrieval {review.timings.retrievalMs.toFixed(0)} ms · committee {review.timings.panelMs.toFixed(0)} ms · total {review.timings.totalMs.toFixed(0)} ms · request {review.requestId.slice(0, 8)}
      </p>
    </div>
  );
}
