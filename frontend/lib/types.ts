export type Severity = "critical" | "high" | "medium" | "low";

export interface Finding {
  id: string;
  category: string;
  severity: Severity;
  status: "open" | "mitigating" | "resolved";
  method: string;
  endpoint: string;
  title: string;
  description: string;
  evidence: Record<string, unknown>;
  cvss: number;
  detected_at: string;
  source: string;
}

export interface ApiEndpoint {
  id: string;
  method: string;
  path: string;
  status: "documented" | "shadow" | "drift";
  calls_24h: number;
  last_seen: string;
}

export interface RagSource {
  id: string;
  document: string;
  page: number;
  line_start: number;
  line_end: number;
  snippet: string;
  similarity: number;
  entailment: number;
}

export interface RagQuery {
  id: string;
  ts: string;
  question: string;
  answer: string;
  nli_score: number;
  verdict: "verified" | "review";
  latency_ms: number;
  model: string;
  sources: RagSource[];
}

export interface Report {
  id: string;
  title: string;
  period: string;
  created_at: string;
  sha256: string;
  key_id: string;
  signer: string;
  consensus: number;
}

export interface AuditEntry {
  id: number;
  ts: string;
  user_id: string | null;
  action: string;
  resource: string | null;
  ip: string | null;
  prev_hash: string;
  entry_hash: string;
}

export interface Vote {
  agent: string;
  vote: "approve" | "conditional" | "reject";
  evidence: string;
}

export interface Overview {
  tenant: { name: string; plan: string };
  services: { key: string; name: string; status: "operational" | "degraded"; headline: string; detail: string }[];
  security: { open: Record<Severity, number>; resolved: number; mitigating: number };
  finops: { baseline_usd: number; actual_usd: number; saved_usd: number; saving_pct: number; samples: number };
  ai_rag: { queries: number; avg_nli: number; verified_pct: number; threshold: number };
  endpoints: Record<string, number>;
  posture_score: number;
  consensus: Vote[];
}

export type FinopsTotals = Overview["finops"];
export type RagTotals = Overview["ai_rag"];

export interface FinopsSummary extends FinopsTotals {
  projected_monthly_saving_usd: number;
  hpa_scale_events: number;
  by_cluster: { cluster: string; saved_usd: number }[];
  top_namespaces: { namespace: string; saved_usd: number }[];
}

export interface FinopsPoint {
  date: string;
  baseline_usd: number;
  actual_usd: number;
  saved_usd: number;
}

export interface RagSummary extends RagTotals {
  distribution: { bucket: string; count: number }[];
}

export type TelemetryEvent =
  | { type: "hello"; tenant_id: string }
  | { type: "heartbeat"; data: { ts: string } }
  | { type: "finding"; data: Finding }
  | { type: "rag"; data: RagQuery }
  | {
      type: "finops";
      data: { cluster: string; namespace: string; saved_usd: number; replicas_before: number; replicas_after: number; ts: string; totals: Overview["finops"] };
    };
