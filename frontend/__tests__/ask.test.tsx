import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AskPanel } from "@/components/AskPanel";
import { ConsensusStatus } from "@/components/ConsensusStatus";
import { reasonText } from "@/lib/consensus";
import type { AnswerReview, Verdict } from "@/lib/types";

const v = (agent: Verdict["agent"], vote: Verdict["vote"] = "approve", findings: Verdict["findings"] = []): Verdict => ({ agent, vote, score: vote === "approve" ? 1 : 0.2, findings, rationale: vote === "approve" ? "fine" : "nope" });
const base: AnswerReview = {
  contract: "answer-review.v1", requestId: "abcdef1234567890", tenantId: "t", question: "¿Cuánto?", outcome: "RELEASED", answer: "Siete años [1].", reasons: [],
  votes: [v("hallucination_critic"), v("tenant_security_auditor"), v("coherence_validator")],
  sources: [{ index: 1, score: 0.9, docId: "politica.md", source: "politica.md", section: "Retención", page: 3, start: 10, end: 80, text: "Se conservan 7 años." }],
  retrieval: { status: "ok", fragments: 1, latencyMs: 10 }, timings: { totalMs: 30, retrievalMs: 10, panelMs: 5 }, escalation: false,
};

describe("ConsensusStatus", () => {
  it("shows unanimous approval with the three members", () => {
    render(<ConsensusStatus review={base} />);
    expect(screen.getByTestId("outcome")).toHaveTextContent("Released");
    for (const id of ["hallucination_critic", "tenant_security_auditor", "coherence_validator"]) expect(screen.getByTestId(`vote-${id}`)).toHaveTextContent("approve");
    expect(screen.queryByTestId("reasons")).not.toBeInTheDocument();
  });

  it("explains a block, flags escalation and marks a non-responding member", () => {
    const review: AnswerReview = {
      ...base, outcome: "BLOCKED", answer: null, escalation: true, votes: [v("hallucination_critic", "reject", [{ code: "numeric_mismatch", severity: "high", detail: "5 vs 7" }]), v("tenant_security_auditor")],
      reasons: [{ code: "agent_rejected", agent: "hallucination_critic", severity: "high", detail: "x" }, { code: "agent_fault:timeout", agent: "coherence_validator", severity: "critical", detail: "y" }],
    };
    render(<ConsensusStatus review={review} />);
    expect(screen.getByTestId("outcome")).toHaveTextContent("Blocked");
    expect(screen.getByText(/needs human review/)).toBeInTheDocument();
    expect(screen.getByTestId("vote-coherence_validator")).toHaveTextContent("no response");
    expect(screen.getByTestId("vote-hallucination_critic")).toHaveTextContent("numeric_mismatch");
    expect(screen.getByTestId("reasons")).toHaveTextContent("failed to respond");
  });

  it("security veto says that no content is shown", () => {
    render(<ConsensusStatus review={{ ...base, outcome: "BLOCKED", answer: null, votes: [], sources: [], reasons: [{ code: "tenant_security_veto", agent: "tenant_security_auditor", severity: "critical", detail: "d" }] }} />);
    expect(screen.getByText(/no content is shown/i)).toBeInTheDocument();
  });

  it("never hides an unknown reason code", () => expect(reasonText("brand_new_code")).toBe("brand_new_code"));
});

describe("AskPanel", () => {
  const respond = (status: number, body?: unknown) => (global.fetch = jest.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body }) as unknown as typeof fetch);
  const ask = async (q = "¿Cuánto tiempo?") => {
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: q } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /ask/i })); });
  };

  it("posts only the question (never a tenant) and renders answer + authorised sources", async () => {
    const fetchMock = respond(200, { runId: "r1", review: base });
    render(<AskPanel initialHistory={[]} />);
    await ask();
    expect(fetchMock).toHaveBeenCalledWith("/api/backend/ask", { method: "POST", body: JSON.stringify({ question: "¿Cuánto tiempo?" }) });
    expect(await screen.findByTestId("answer")).toHaveTextContent("Siete años");
    expect(screen.getByTestId("sources")).toHaveTextContent("p.3");
    expect(screen.getByTestId("ask-history")).toHaveTextContent("released");
  });

  it("does not render an answer for a blocked verdict, even if one slipped into the payload", async () => {
    respond(200, { runId: "r2", review: { ...base, outcome: "BLOCKED", answer: "FILTRADO", votes: [], sources: [], reasons: [{ code: "no_context", agent: null, severity: "medium", detail: "d" }] } });
    render(<AskPanel initialHistory={[]} />);
    await ask();
    await screen.findByTestId("consensus-status");
    expect(screen.queryByTestId("answer")).not.toBeInTheDocument();
    expect(screen.queryByText("FILTRADO")).not.toBeInTheDocument();
  });

  it.each([[503, /unavailable/], [502, /invalid/], [429, /too fast/]])("maps HTTP %i to a calm message", async (status, re) => {
    respond(status as number, { detail: "x" });
    render(<AskPanel initialHistory={[]} />);
    await ask();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(re as RegExp));
    expect(screen.queryByTestId("consensus-status")).not.toBeInTheDocument();
  });
});
