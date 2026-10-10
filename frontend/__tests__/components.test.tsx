import { act, fireEvent, render, screen } from "@testing-library/react";
import { FindingsTable } from "@/components/FindingsTable";
import { Gauge } from "@/components/ui/Gauge";
import { useTelemetry } from "@/lib/store";
import type { Finding } from "@/lib/types";

const mk = (id: string, severity: Finding["severity"], status: Finding["status"] = "open"): Finding => ({
  id, severity, status, category: "IDOR", method: "GET", endpoint: `/api/${id}`, title: `title-${id}`, description: "desc",
  evidence: { probe: "id-swap" }, cvss: 7.5, detected_at: new Date().toISOString(), source: "ShadowAPI_Guard",
});

describe("Gauge", () => {
  it("exposes an accessible label with the value", () => {
    render(<Gauge value={0.973} threshold={0.95} label="nli" />);
    expect(screen.getByRole("img", { name: "nli: 0.973" })).toBeInTheDocument();
  });
});

describe("FindingsTable", () => {
  beforeEach(() => useTelemetry.setState({ liveFindings: [] }));

  it("sorts by severity, hides resolved and filters", () => {
    render(<FindingsTable initial={[mk("low1", "low"), mk("crit1", "critical"), mk("done", "high", "resolved")]} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("/api/crit1");
    expect(screen.queryByText("/api/done")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "low" }));
    expect(screen.queryByText("/api/crit1")).not.toBeInTheDocument();
    expect(screen.getByText("/api/low1")).toBeInTheDocument();
  });

  it("merges live findings and reveals evidence on click", () => {
    render(<FindingsTable initial={[mk("a", "low")]} />);
    act(() => useTelemetry.getState().ingest({ type: "finding", data: mk("live", "critical") }));
    fireEvent.click(screen.getByText("/api/live"));
    expect(screen.getByText("title-live")).toBeInTheDocument();
  });
});
