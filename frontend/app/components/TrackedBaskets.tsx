"use client";
import React, { useState } from "react";
import { ChevronRight, X } from "lucide-react";
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

// ── Terminal Ledger Rail — shared module grammar (see Watchlist.tsx) ─────────
const GRID = "minmax(0, 1fr) 52px 52px 52px 20px";
const fmtPrice = (p: number | null | undefined) => (p == null ? null : p >= 10000 ? `${(p / 1000).toFixed(1)}k` : p.toFixed(2));

// Sidebar mirror of the in-page "Paper Portfolio Cabinet" — so clicking TRACK on a
// methodology basket actually surfaces it in the persistent right rail (same spot
// the Apex Basket lives in SpeculairTracker), instead of only appearing inline in
// the Methodologies tab with no visible feedback.
export function TrackedBaskets({ baskets, onUntrack }: { baskets: TrackedBasketEntry[]; onUntrack: (path: string) => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [hoveredPath, setHoveredPath] = useState<string | null>(null);

  if (!baskets.length) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", fontFamily: "var(--font-sans)" }}>
      {/* Level-1 module band */}
      <div style={{ height: 28, boxSizing: "border-box", display: "flex", alignItems: "center", gap: 8, padding: "0 12px", background: "var(--bg)", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
        <span style={{ width: 2, height: 10, borderRadius: 1, background: "var(--amber)", flexShrink: 0 }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-secondary)" }}>Tracked Baskets</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-light)" }}>{baskets.length}</span>
      </div>

      {baskets.map((b) => {
        const isOpen = open[b.path] ?? false;
        const ytdColor = b.ytdReturn == null ? "var(--text-light)" : b.ytdReturn >= 0 ? "var(--green)" : "var(--red)";
        return (
          <div key={b.path}>
            {/* Level-2 basket row — toggle + untrack stay SIBLING buttons (never nested) */}
            <div onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; setHoveredPath(b.path); }} onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; setHoveredPath(null); }}
              style={{ display: "flex", alignItems: "center", height: 26, borderBottom: "1px solid var(--border-subtle)", transition: "background 0.1s" }}>
              <button
                onClick={() => setOpen((prev) => ({ ...prev, [b.path]: !isOpen }))}
                style={{ flex: 1, minWidth: 0, height: "100%", display: "flex", alignItems: "center", gap: 6, padding: "0 6px 0 12px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
              >
                <ChevronRight size={12} color="var(--text-light)" style={{ flexShrink: 0, transform: isOpen ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 120ms ease" }} />
                <span style={{ width: 6, height: 6, borderRadius: 2, background: "var(--amber)", flexShrink: 0 }} />
                <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{b.name}</span>
                <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", color: ytdColor, flexShrink: 0 }}>
                  {b.ytdReturn == null ? "—" : `${b.ytdReturn >= 0 ? "+" : ""}${(b.ytdReturn * 100).toFixed(1)}%`}
                </span>
              </button>
              <button onClick={() => onUntrack(b.path)} title={`Untrack ${b.name}`} aria-label={`Untrack ${b.name}`}
                style={{ width: 20, height: 20, marginRight: 12, display: "flex", alignItems: "center", justifyContent: "center", background: "none", border: "none", borderRadius: 4, cursor: "pointer", color: "var(--text-light)", padding: 0, flexShrink: 0, opacity: hoveredPath === b.path ? 1 : 0, pointerEvents: hoveredPath === b.path ? "auto" : "none", transition: "opacity 120ms ease" }}
                onMouseEnter={(e) => { e.currentTarget.style.color = "var(--red)"; e.currentTarget.style.background = "var(--red-light)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-light)"; e.currentTarget.style.background = "transparent"; }}>
                <X size={12} />
              </button>
            </div>
            {isOpen && (
              <div style={{ animation: "fadeIn 120ms ease" }}>
                {b.holdings.length > 0 ? (
                  <>
                    {/* Holdings column sub-header — indented under the Level-2 chevron */}
                    <div style={{ display: "grid", gridTemplateColumns: GRID, gap: 6, height: 20, alignItems: "center", padding: "0 12px 0 30px", background: "var(--bg)", fontSize: 9, fontWeight: 600, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--border-subtle)", fontFamily: "var(--font-mono)" }}>
                      <div>Symbol</div>
                      <div></div>
                      <div style={{ textAlign: "right" }}>Entry</div>
                      <div style={{ textAlign: "right" }}>Wt</div>
                      <div></div>
                    </div>
                    {b.holdings.map((h) => (
                      <div key={h.symbol}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                        style={{ display: "grid", gridTemplateColumns: GRID, gap: 6, height: 28, alignItems: "center", padding: "0 12px 0 30px", borderBottom: "1px solid var(--border-subtle)", fontSize: 11, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", transition: "background 0.1s" }}>
                        <div style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          <Link href={`/stock/${h.symbol}`} style={{ textDecoration: "none", color: "var(--text)", fontWeight: 700 }}>{h.symbol}</Link>
                        </div>
                        <div></div>
                        <div style={{ textAlign: "right", color: "var(--text-light)" }}>{h.entry_price ? fmtPrice(h.entry_price) : <span style={{ color: "var(--text-light)" }}>–.––</span>}</div>
                        <div style={{ textAlign: "right", color: "var(--text-secondary)" }}>{h.weight != null ? `${(h.weight * 100).toFixed(0)}%` : "—"}</div>
                        <span />
                      </div>
                    ))}
                  </>
                ) : (
                  <div style={{ padding: "10px 12px 10px 30px", fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>No current holdings.</div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
