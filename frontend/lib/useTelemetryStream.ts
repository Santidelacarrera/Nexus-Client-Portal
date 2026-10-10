"use client";
import { useEffect } from "react";
import { useTelemetry } from "./store";
import type { TelemetryEvent } from "./types";

/** Opens /ws/telemetry using a fresh single-use ticket; reconnects with capped backoff. */
export function useTelemetryStream() {
  const { setConnection, ingest } = useTelemetry();
  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout>;
    let attempt = 0;
    let stopped = false;

    async function connect() {
      setConnection("connecting");
      try {
        const res = await fetch("/api/ws-ticket", { method: "POST" });
        if (res.status === 401) {
          window.location.href = "/login?expired=1";
          return;
        }
        if (!res.ok) throw new Error("ticket");
        const { ticket, url } = await res.json();
        ws = new WebSocket(`${url}?ticket=${encodeURIComponent(ticket)}`);
        ws.onopen = () => {
          attempt = 0;
          setConnection("live");
        };
        ws.onmessage = (m) => {
          try {
            ingest(JSON.parse(m.data) as TelemetryEvent);
          } catch {}
        };
        ws.onclose = retry;
        ws.onerror = () => ws?.close();
      } catch {
        retry();
      }
    }
    function retry() {
      if (stopped) return;
      setConnection("offline");
      timer = setTimeout(connect, Math.min(15000, 1000 * 2 ** attempt++));
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [setConnection, ingest]);
}
