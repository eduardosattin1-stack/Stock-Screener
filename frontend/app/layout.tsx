import type { Metadata } from "next";
import "./globals.css";
import Nav from "./nav";
import { AuthProvider } from "./AuthProvider";
import { AuthGate } from "./AuthGate";

export const metadata: Metadata = {
  title: "CB Screener v6 — 10-Factor Stock Analysis",
  description: "AI-powered stock screener with 10-factor composite scoring",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <AuthGate>
            <Nav />
            {children}
          </AuthGate>
        </AuthProvider>
      </body>
    </html>
  );
}
