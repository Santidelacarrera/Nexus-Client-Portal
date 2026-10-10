import { create } from "zustand";
import type { Finding, Overview, TelemetryEvent } from "./types";

export type Connection = "connecting" | "live" | "offline";
const MAX_EVENTS = 40;

export interface FeedItem {
  key: string;
  kind: "finding" | "finops" | "rag";
  title: string;
  detail: string;
  tone: "crit" | "warn" | "mint" | "cyan";
  ts: string;
}

interface TelemetryState {
  connection: Connection;
  feed: FeedItem[];
  liveFindings: Finding[];
  finopsTotals: Overview["finops"] | null;
  setConnection: (c: Connection) => void;
  ingest: (e: TelemetryEvent) => void;
}

const tone = (s: Finding["severity"]): FeedItem["tone"] => (s === "critical" ? "crit" : s === "high" ? "warn" : "cyan");

export function toFeedItem(e: TelemetryEvent, seq: number): FeedItem | null {
  switch (e.type) {
    case "finding":
      return { key: `f-${e.data.id}`, kind: "finding", title: `${e.data.severity.toUpperCase()} · ${e.data.category}`, detail: `${e.data.method} ${e.data.endpoint}`, tone: tone(e.data.severity), ts: e.data.detected_at };
    case "finops":
      return { key: `o-${seq}`, kind: "finops", title: `HPA · ${e.data.namespace}`, detail: `${e.data.replicas_before}→${e.data.replicas_after} replicas · +$${e.data.saved_usd.toFixed(2)}/h`, tone: "mint", ts: e.data.ts };
    case "rag":
      return { key: `r-${e.data.id}`, kind: "rag", title: `RAG · NLI ${e.data.nli_score.toFixed(3)}`, detail: e.data.question, tone: e.data.verdict === "verified" ? "cyan" : "warn", ts: e.data.ts };
    default:
      return null;
  }
}

let seq = 0;
export const useTelemetry = create<TelemetryState>((set) => ({
  connection: "connecting",
  feed: [],
  liveFindings: [],
  finopsTotals: null,
  setConnection: (connection) => set({ connection }),
  ingest: (e) =>
    set((s) => {
      const item = toFeedItem(e, ++seq);
      if (!item) return s;
      return {
        feed: [item, ...s.feed].slice(0, MAX_EVENTS),
        liveFindings: e.type === "finding" ? [e.data, ...s.liveFindings].slice(0, 100) : s.liveFindings,
        finopsTotals: e.type === "finops" ? e.data.totals : s.finopsTotals,
      };
    }),
}));
