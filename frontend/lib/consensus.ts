import type { AgentId } from "./types";

export const AGENTS: Record<AgentId, { name: string; role: string }> = {
  hallucination_critic: { name: "Hallucination Critic", role: "Every claim must be backed by the retrieved evidence" },
  tenant_security_auditor: { name: "Tenant Security Auditor", role: "Isolation, prompt-injection and sensitive-data veto" },
  coherence_validator: { name: "Coherence Validator", role: "Answers the question, without contradicting itself" },
};
export const AGENT_ORDER: AgentId[] = ["hallucination_critic", "tenant_security_auditor", "coherence_validator"];

/** Human wording for machine reason codes. Unknown codes fall back to the code itself (never hidden). */
const REASONS: Record<string, string> = {
  tenant_security_veto: "The security auditor vetoed the answer.",
  agent_rejected: "A committee member rejected the answer.",
  inconsistent_verdict: "A committee member's verdict contradicted itself.",
  portal_invariant_violation: "The portal refused a verdict that broke the committee rule.",
  no_context: "There is not enough authorised context to answer.",
  tenant_mismatch: "Isolation check failed; all content was discarded.",
  foreign_tenant_reference: "Content referring to another organisation was detected.",
  prompt_injection: "Instructions embedded in a document were detected.",
  secret_leak: "A possible credential or secret was detected.",
  unsupported_claim: "A statement is not supported by the sources.",
  numeric_mismatch: "A figure in the answer does not match the sources.",
  off_topic: "The answer does not address the question.",
  self_contradiction: "The answer contradicts itself.",
  dangling_citation: "The answer cites a source that does not exist.",
  retrieval_unavailable: "The knowledge base could not be reached.",
  retrieval_timeout: "The knowledge base took too long to answer.",
  retrieval_forbidden: "The knowledge base refused the request.",
  retrieval_tenant_not_provisioned: "Your organisation is not provisioned for this service yet.",
};
export const reasonText = (code: string): string => (code.startsWith("agent_fault:") ? "A committee member failed to respond, so the answer was withheld." : REASONS[code] ?? code);
