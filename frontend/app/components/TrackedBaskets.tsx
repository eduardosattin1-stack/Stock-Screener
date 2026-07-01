"use client";
import React, { useState } from "react";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import Link from "next/link";

export interface TrackedBasketHolding {
  symbol: string;
  entry_price?: number;
  entry_date?: string;
  weight?: number;
}
export interface TrackedBasketEntry {
  path: string;
  name: string;
  ytdReturn?: number;
  holdings: TrackedBasketHolding[];
}

// Sidebar mirror of the in-page "Paper Portfolio Cabinet" — so clicking TRACK on a
// methodology basket actually surfaces it in the persistent right rail (same spot
// the Apex Basket lives in SpeculairTracker), instead of only appearing inline in
// the Methodologies tab with no visible feedback.
export function TrackedBaskets({ baskets, onUntrack }: { baskets: TrackedBasketEntry[]; onUntrack: (path: string) => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  if (!baskets.length) return null;

  return (
    <div style={{ borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", fontFamily: "var(--font-sans)" }}>
      <div style={{ padding: "12px 16px 10px", borderBottom: "1px solid var(--border-subtle)", display: "flex", alignItems: "baseline", gap: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 800, color: "var(--text)" }}>Tracked Baskets</span>
        <span style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>{baskets.length}</span>
      </div>

      {baskets.map((b) => {
        const isOpen = open[b.path] ?? false;
        return (
          <div key={b.path}>
            <div style={{ display: "flex", alignItems: "center", borderBottom: "1px solid var(--border-subtle)" }}>
              <button
                onClick={() => setOpen((prev) => ({ ...prev, [b.path]: !isOpen }))}
                style={{ flex: 1, display: "flex", alignItems: "center", gap: 6, padding: "10px 8px 10px 16px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
              >
                {isOpen ? <ChevronDown size={13} color="var(--text-light)" /> : <ChevronRight size={13} color="var(--text-light)" />}
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{b.name}</span>
                <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)", color: b.ytdReturn == null ? "var(--text-muted)" : b.ytdReturn >= 0 ? "var(--green)" : "var(--red)" }}>
                  {b.ytdReturn == null ? "—" : `${b.ytdReturn >= 0 ? "+" : ""}${(b.ytdReturn * 100).toFixed(1)}%`}
                </span>
              </button>
              <button onClick={() => onUntrack(b.path)} title="Stop tracking" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-light)", padding: "8px 12px", display: "flex" }}>
                <X size={12} />
              </button>
            </div>
            {isOpen && (
              b.holdings.length > 0 ? (
                b.holdings.map((h) => (
                  <div key={h.symbol} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) 1fr 1fr", gap: 6, padding: "6px 16px", borderBottom: "1px solid var(--border-subtle)", alignItems: "center", fontSize: 11, fontFamily: "var(--font-mono)" }}>
                    <Link href={`/stock/${h.symbol}`} style={{ textDecoration: "none", color: "var(--text)", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.symbol}</Link>
                    <div style={{ textAlign: "right", color: "var(--text-muted)" }}>{h.entry_price ? h.entry_price.toFixed(2) : "—"}</div>
                    <div style={{ textAlign: "right", color: "var(--text-light)" }}>{h.weight != null ? `${(h.weight * 100).toFixed(0)}%` : "—"}</div>
                  </div>
                ))
              ) : (
                <div style={{ padding: "8px 16px", fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>No current holdings.</div>
              )
            )}
          </div>
        );
      })}
    </div>
  );
}
