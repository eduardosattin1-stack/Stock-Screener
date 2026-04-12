"use client";
import { Radio } from "lucide-react";

export default function Signals() {
  return (
    <div style={{ minHeight: "100vh", padding: "20px 24px", maxWidth: 1280, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20, paddingBottom: 12, borderBottom: "1px solid #f3f4f6" }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: "#1a1a1a", letterSpacing: "0.02em", fontFamily: "var(--font-mono)" }}>
          SIGNALS<span style={{ color: "#9ca3af", fontWeight: 400 }}>/history</span>
        </span>
      </div>

      <div style={{
        background: "#ffffff", borderRadius: 8, border: "1px solid #e5e7eb",
        boxShadow: "0 1px 3px rgba(0,0,0,0.06)", padding: "80px 20px", textAlign: "center",
      }}>
        <Radio size={36} color="#e5e7eb" />
        <div style={{ fontSize: 14, color: "#6b7280", fontFamily: "var(--font-mono)", marginTop: 16, fontWeight: 600 }}>
          Signal History Coming Soon
        </div>
        <div style={{ fontSize: 11, color: "#9ca3af", fontFamily: "var(--font-mono)", marginTop: 8, maxWidth: 400, margin: "8px auto 0", lineHeight: 1.6 }}>
          Track how the screener's BUY/SELL calls performed over time. See historical accuracy, average returns, and per-stock signal evolution.
        </div>
        <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 24 }}>
          {["Signal scorecard", "Return attribution", "Hit rate over time"].map(f => (
            <span key={f} style={{
              fontSize: 10, padding: "5px 12px", borderRadius: 20,
              fontFamily: "var(--font-mono)", color: "#2d7a4f",
              background: "#e8f5ee", border: "1px solid #b8dcc8",
            }}>{f}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
