import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stock Screener — Buffett Value + Technical + Analyst",
  description: "AI-powered stock screener with Warren Buffett value investing methodology",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
