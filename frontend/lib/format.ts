export const usd = (n: number, digits = 0) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits, minimumFractionDigits: digits }).format(n);

export const pct = (n: number, digits = 1) => `${n.toFixed(digits)}%`;

export function timeAgo(iso: string, now: number = Date.now()): string {
  const s = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const shortHash = (h: string, n = 10) => (h.length > n * 2 ? `${h.slice(0, n)}…${h.slice(-4)}` : h);

export const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;
