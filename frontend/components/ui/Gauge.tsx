/** Semi-circular gauge. `threshold` draws a tick (e.g. NLI 0.95). */
export function Gauge({ value, max = 1, threshold, label, format = (v: number) => v.toFixed(3) }: { value: number; max?: number; threshold?: number; label: string; format?: (v: number) => string }) {
  const R = 54;
  const C = Math.PI * R;
  const frac = Math.min(1, Math.max(0, value / max));
  const ok = threshold === undefined || value >= threshold;
  const color = ok ? "#10b981" : "#f59e0b";
  const tick = threshold !== undefined ? Math.PI * (1 - threshold / max) : null;
  return (
    <figure className="flex flex-col items-center" role="img" aria-label={`${label}: ${format(value)}`}>
      <svg viewBox="0 0 140 84" className="w-full max-w-[220px]">
        <path d="M16 70 A54 54 0 0 1 124 70" fill="none" stroke="#1f2937" strokeWidth="10" strokeLinecap="round" />
        <path d="M16 70 A54 54 0 0 1 124 70" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${C * frac} ${C}`} style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
        {tick !== null && (
          <line x1={70 + (R - 9) * Math.cos(tick)} y1={70 - (R - 9) * Math.sin(tick)} x2={70 + (R + 9) * Math.cos(tick)} y2={70 - (R + 9) * Math.sin(tick)} stroke="#e2e8f0" strokeWidth="1.5" />
        )}
        <text x="70" y="64" textAnchor="middle" fill="#f1f5f9" fontFamily="JetBrains Mono, monospace" fontSize="19" fontWeight="700">{format(value)}</text>
      </svg>
      <figcaption className="panel-title -mt-1">{label}</figcaption>
    </figure>
  );
}
