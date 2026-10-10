import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#090d16",
        panel: "#111827",
        edge: "#1f2937",
        cyan: { DEFAULT: "#06b6d4", glow: "#22d3ee" },
        mint: "#10b981",
        warn: "#f59e0b",
        crit: "#f43f5e",
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', "ui-monospace", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        neon: "0 0 0 1px rgba(6,182,212,.35), 0 0 24px -6px rgba(6,182,212,.45)",
        mint: "0 0 0 1px rgba(16,185,129,.35), 0 0 24px -6px rgba(16,185,129,.4)",
      },
      keyframes: {
        scan: { "0%": { transform: "translateY(-100%)" }, "100%": { transform: "translateY(100%)" } },
        pulseDot: { "0%,100%": { opacity: "1" }, "50%": { opacity: ".35" } },
        slideIn: { "0%": { opacity: "0", transform: "translateY(-6px)" }, "100%": { opacity: "1", transform: "none" } },
      },
      animation: { scan: "scan 6s linear infinite", pulseDot: "pulseDot 1.6s ease-in-out infinite", slideIn: "slideIn .25s ease-out" },
    },
  },
  plugins: [],
};
export default config;
