import { shortHash, timeAgo, usd } from "@/lib/format";

describe("format", () => {
  it("formats USD", () => {
    expect(usd(12345.6)).toBe("$12,346");
    expect(usd(1.5, 2)).toBe("$1.50");
  });
  it("renders relative time", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(timeAgo("2026-01-01T11:59:30Z", now)).toBe("30s ago");
    expect(timeAgo("2026-01-01T11:00:00Z", now)).toBe("1h ago");
    expect(timeAgo("2025-12-30T12:00:00Z", now)).toBe("2d ago");
  });
  it("shortens long hashes only", () => {
    expect(shortHash("abc")).toBe("abc");
    expect(shortHash("a".repeat(64), 6)).toBe("aaaaaa…aaaa");
  });
});
