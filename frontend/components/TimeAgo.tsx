"use client";
import { timeAgo } from "@/lib/format";

/** Relative time that tolerates the server/client clock difference during hydration. */
export function TimeAgo({ iso, className }: { iso: string; className?: string }) {
  return (
    <time dateTime={iso} className={className} suppressHydrationWarning>
      {timeAgo(iso)}
    </time>
  );
}
