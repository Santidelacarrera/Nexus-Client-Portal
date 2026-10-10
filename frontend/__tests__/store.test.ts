import { toFeedItem, useTelemetry } from "@/lib/store";
import type { Finding, TelemetryEvent } from "@/lib/types";

const finding = (id: string, severity: Finding["severity"]): Finding => ({
  id, severity, category: "BOLA", status: "open", method: "GET", endpoint: "/api/v2/accounts/{id}",
  title: "t", description: "d", evidence: {}, cvss: 9.1, detected_at: new Date().toISOString(), source: "ShadowAPI_Guard",
});

describe("telemetry store", () => {
  beforeEach(() => useTelemetry.setState({ feed: [], liveFindings: [], finopsTotals: null, connection: "connecting" }));

  it("maps severities to tones", () => {
    expect(toFeedItem({ type: "finding", data: finding("1", "critical") }, 1)?.tone).toBe("crit");
    expect(toFeedItem({ type: "finding", data: finding("2", "high") }, 2)?.tone).toBe("warn");
    expect(toFeedItem({ type: "heartbeat", data: { ts: "x" } }, 3)).toBeNull();
  });

  it("ingests findings newest-first and caps the feed", () => {
    for (let i = 0; i < 60; i++) useTelemetry.getState().ingest({ type: "finding", data: finding(String(i), "low") });
    const s = useTelemetry.getState();
    expect(s.feed).toHaveLength(40);
    expect(s.liveFindings[0].id).toBe("59");
  });

  it("tracks live FinOps totals", () => {
    const totals = { baseline_usd: 100, actual_usd: 60, saved_usd: 40, saving_pct: 40, samples: 1 };
    const e: TelemetryEvent = { type: "finops", data: { cluster: "c", namespace: "n", saved_usd: 1.2, replicas_before: 10, replicas_after: 6, ts: new Date().toISOString(), totals } };
    useTelemetry.getState().ingest(e);
    expect(useTelemetry.getState().finopsTotals?.saved_usd).toBe(40);
  });
});
