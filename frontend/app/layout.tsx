import type { Metadata } from "next";
import "./globals.css";

export const dynamic = "force-dynamic"; // per-request CSP nonce requires dynamic rendering

export const metadata: Metadata = {
  title: "Nexus Client Portal",
  description: "Nexus Security & AI Lab — managed services console",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
