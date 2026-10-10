import { ReactNode } from "react";

export function Panel({ title, action, children, className = "", glow }: { title?: string; action?: ReactNode; children: ReactNode; className?: string; glow?: "cyan" | "mint" }) {
  return (
    <section className={`panel p-4 ${glow === "cyan" ? "shadow-neon" : glow === "mint" ? "shadow-mint" : ""} ${className}`}>
      {(title || action) && (
        <header className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="panel-title">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
