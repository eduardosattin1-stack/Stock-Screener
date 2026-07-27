"use client";
import React, { useState, useEffect } from "react";
import { ChevronRight, RefreshCw } from "lucide-react";
import Link from "next/link";

interface Pick {
  symbol: string;
  conviction: number;
  entry_price?: number;
  entry_date?: string;
  source_methodologies?: string[];
  // Debt-cycle badge fields (2026-07-27): deterministic payback-speed label +
  // whether the phase duration cap trimmed this seat's weight.
  duration_bucket?: string;
  duration_bucket_source?: string;
  cycle_capped?: boolean;
  cycle_cap_note?: string;
  phase_fit?: string;
}

type Quote = { price: number; changesPercentage: number };

// ── Terminal Ledger Rail — shared module grammar (see Watchlist.tsx) ─────────
const GRID = "minmax(0, 1fr) 52px 52px 52px 20px";
const fmtPrice = (p: number | null | undefined) => (p == null ? null : p >= 10000 ? `${(p / 1000).toFixed(1)}k` : p.toFixed(2));
const fmtPct = (pct: number | null | undefined) => (pct == null ? null : `${pct > 0 ? "+" : ""}${Math.abs(pct) >= 100 ? pct.toFixed(0) : pct.toFixed(1)}%`);
const PENDING = <span style={{ color: "var(--text-light)" }}>–.––</span>;

// Compact live tracker for the Speculair Apex Basket + Capitulation Watchlist.
// Designed to sit underneath the Watchlist inside the shared right rail.
export function SpeculairTracker() {
  const [baskets, setBaskets] = useState<any>(null);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [loading, setLoading] = useState(false);
  const [openApex, setOpenApex] = useState(true);
  const [openCap, setOpenCap] = useState(true);
  const [openClosed, setOpenClosed] = useState(false);
  const [trackingEqual, setTrackingEqual] = useState<any>(null);
  const [trackingWeighted, setTrackingWeighted] = useState<any>(null);

  // Load baskets: GCS first, public file fallback (mirrors page.tsx).
  useEffect(() => {
    fetch("/api/gcs/scans/speculair_baskets.json")
      .then((r) => { if (r.ok) return r.json(); throw new Error("gcs"); })
      .then((d) => { if (d) setBaskets(d); })
      .catch(() => {
        fetch("/speculair_baskets.json")
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (d) setBaskets(d); })
          .catch(() => {});
      });
  }, []);

  // Load Apex track record (chained NAV + closed rotations): GCS first, public fallback.
  // Two chains: equal-weight (original) and Director-weighted-by-conviction (promoted
  // once it has genuine live-forward history) — same promotion rule as the Apex Basket
  // card on / (page.tsx) and the Daily Briefing headline, so this "Apex since ..." figure
  // always matches those instead of quietly reporting a different chain.
  useEffect(() => {
    fetch("/api/gcs/scans/speculair_apex_tracking.json")
      .then((r) => { if (r.ok) return r.json(); throw new Error("gcs"); })
      .then((d) => { if (d && d.nav) setTrackingEqual(d); })
      .catch(() => {
        fetch("/speculair_apex_tracking.json")
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (d && d.nav) setTrackingEqual(d); })
          .catch(() => {});
      });
    fetch("/api/gcs/scans/speculair_apex_tracking_weighted.json")
      .then((r) => { if (r.ok) return r.json(); throw new Error("gcs"); })
      .then((d) => { if (d && d.nav) setTrackingWeighted(d); })
      .catch(() => {
        fetch("/speculair_apex_tracking_weighted.json")
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (d && d.nav) setTrackingWeighted(d); })
          .catch(() => {});
      });
  }, []);

  const trackingIsWeighted = !!(trackingWeighted && (trackingWeighted.history || []).length >= 4);
  const tracking = trackingIsWeighted ? trackingWeighted : trackingEqual;

  const apex: Pick[] = baskets?.apex_basket || [];
  const cap: Pick[] = baskets?.capitulation_watchlist || [];
  const symbolsKey = Array.from(new Set([...apex, ...cap].map((p) => p.symbol))).join(",");

  const fetchQuotes = async () => {
    if (!symbolsKey) return;
    setLoading(true);
    try {
      // batch-quote (not quote) — FMP's quote endpoint is single-symbol; a comma list returns []
      const res = await fetch(`/api/fmp?e=batch-quote&symbols=${encodeURIComponent(symbolsKey)}`);
      const data = await res.json();
      if (Array.isArray(data)) {
        const m: Record<string, Quote> = {};
        data.forEach((q: any) => { m[q.symbol] = { price: q.price, changesPercentage: q.changesPercentage ?? q.changePercentage }; });
        setQuotes((prev) => ({ ...prev, ...m }));
      }
    } catch (e) {
      console.error("SpeculairTracker fetch error:", e);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (!symbolsKey) return;
    fetchQuotes();
    const id = setInterval(fetchQuotes, 30000); // 30s, matches Watchlist cadence
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbolsKey]);

  if (!baskets) return null;

  // Conviction chip — number only, theme vars (no hardcoded rgba/#hex).
  const convStyle = (c: number) => ({
    fontSize: 9, padding: "1px 4px", borderRadius: 3, fontFamily: "var(--font-mono)", fontWeight: 700, flexShrink: 0,
    background: c >= 85 ? "var(--green-light)" : c >= 70 ? "var(--amber-light)" : "var(--bg-elevated)",
    color: c >= 85 ? "var(--green)" : c >= 70 ? "var(--amber)" : "var(--text-light)",
  });

  // Apex track-record (paper-traded NAV since basket inception, base 100).
  const navHist: { date: string; nav: number }[] = tracking?.history || [];
  const nav: number | null = tracking?.nav ?? null;
  const sinceInception = nav != null ? nav - 100 : null;
  const closed: any[] = tracking?.closed || [];
  const fmtDay = (s?: string) => (s ? new Date(s + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "");
  const daysSince = tracking?.inception_date && tracking?.last_date
    ? Math.max(0, Math.round((new Date(tracking.last_date + "T00:00:00").getTime() - new Date(tracking.inception_date + "T00:00:00").getTime()) / 86400000))
    : null;
  const perfColor = sinceInception == null ? "var(--text-light)" : sinceInception > 0 ? "var(--green)" : sinceInception < 0 ? "var(--red)" : "var(--text-light)";

  // Live P&L% vs entry for one pick (null when either side is missing).
  const livePnl = (p: Pick): number | null => {
    const q = quotes[p.symbol];
    const e = p.entry_price || 0;
    return q?.price != null && e > 0 ? ((q.price / e) - 1) * 100 : null;
  };
  // Collapsed-section aggregate: mean live P&L across rows with data.
  const meanPnl = (rows: Pick[]): number | null => {
    const vals = rows.map(livePnl).filter((v): v is number => v != null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };
  const rotVals = closed.map((c) => c.return_pct).filter((v: any): v is number => typeof v === "number");
  const rotAgg = rotVals.length ? rotVals.reduce((a: number, b: number) => a + b, 0) / rotVals.length : null;

  // NAV sparkline — scale always includes the base (100) so the dashed baseline
  // and above/below-water area fill read at a glance.
  const Sparkline = ({ navs, color }: { navs: number[]; color: string }) => {
    if (!navs || navs.length < 2) return null;
    const w = 88, h = 28, pad = 3;
    const min = Math.min(...navs, 100), max = Math.max(...navs, 100), range = max - min || 1;
    const xy = (v: number, i: number): [number, number] => [
      pad + (i / (navs.length - 1)) * (w - 2 * pad),
      pad + (1 - (v - min) / range) * (h - 2 * pad),
    ];
    const pts = navs.map((v, i) => xy(v, i).map((n) => n.toFixed(1)).join(",")).join(" ");
    const [lx, ly] = xy(navs[navs.length - 1], navs.length - 1);
    const baseY = pad + (1 - (100 - min) / range) * (h - 2 * pad);
    const area = `${pts} ${(w - pad).toFixed(1)},${(h - pad).toFixed(1)} ${pad.toFixed(1)},${(h - pad).toFixed(1)}`;
    const up = navs[navs.length - 1] >= 100;
    return (
      <svg width={w} height={h} style={{ display: "block", flexShrink: 0 }} aria-hidden="true">
        <polygon points={area} fill={up ? "var(--green-light)" : "var(--red-light)"} stroke="none" />
        <line x1={pad} y1={baseY} x2={w - pad} y2={baseY} stroke="var(--border)" strokeDasharray="2 3" strokeWidth={1} />
        <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={lx} cy={ly} r={2} fill={color} />
      </svg>
    );
  };

  // Shared data row (Apex + Beaten-Down): SYMBOL / ENTRY / LAST / P&L / gutter.
  const Row = ({ p }: { p: Pick }) => {
    const q = quotes[p.symbol];
    const last = q?.price;
    const entry = p.entry_price || 0;
    const perf = livePnl(p);
    const color = perf == null ? "var(--text-light)" : perf > 0 ? "var(--green)" : perf < 0 ? "var(--red)" : "var(--text-light)";
    return (
      <div style={{ display: "grid", gridTemplateColumns: GRID, gap: 6, height: 28, alignItems: "center", padding: "0 12px", borderBottom: "1px solid var(--border-subtle)", fontSize: 11, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", transition: "background 0.1s" }}
           onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
        <div style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0 }}>
          <Link href={`/stock/${p.symbol}`} style={{ textDecoration: "none", color: "var(--text)", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.symbol}</Link>
          <span style={convStyle(p.conviction)}>{p.conviction}</span>
          {/* Payback-speed badge (debt-cycle layer): C = cash_now (FCF yield ≥4%),
              P = payback 2-3y, S = story (no FCF yet — capped hardest in DISCIPLINE/FORCING).
              Ring turns red + ✂ when the phase duration cap trimmed this seat. */}
          {p.duration_bucket && (() => {
            const b = p.duration_bucket;
            const letter = b === "cash_now" ? "C" : b === "payback_2_3y" ? "P" : "S";
            const bc = b === "cash_now" ? "var(--green)" : b === "payback_2_3y" ? "var(--amber)" : "var(--red)";
            const tip = `Payback speed: ${b}${p.duration_bucket_source === "director_override" ? " (director override)" : ""}${p.phase_fit ? ` · Cycle fit: ${p.phase_fit}` : ""}${p.cycle_capped ? ` · TRIMMED by the phase duration cap: ${p.cycle_cap_note || ""}` : ""}`;
            return (
              <span title={tip} style={{ fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 700, minWidth: 12, height: 12, lineHeight: "12px", textAlign: "center", borderRadius: 3, color: bc, background: "color-mix(in srgb, currentColor 12%, transparent)", border: `1px solid ${p.cycle_capped ? "var(--red)" : `color-mix(in srgb, ${bc} 40%, transparent)`}`, cursor: "help", flexShrink: 0, padding: "0 2px" }}>
                {letter}{p.cycle_capped ? "✂" : ""}
              </span>
            );
          })()}
        </div>
        <div style={{ textAlign: "right", color: "var(--text-light)" }}>{entry > 0 ? fmtPrice(entry) : PENDING}</div>
        <div style={{ textAlign: "right", color: "var(--text-secondary)" }}>{last != null ? fmtPrice(last) : PENDING}</div>
        <div style={{ textAlign: "right", color, fontWeight: 700 }}>{perf == null ? PENDING : fmtPct(perf)}</div>
        <span />
      </div>
    );
  };

  // Level-2 collapsible section header.
  const SectionHeader = ({ open, onClick, title, count, accent, agg }: { open: boolean; onClick: () => void; title: string; count: number; accent: string; agg?: number | null }) => (
    <button onClick={onClick} style={{ width: "100%", height: 26, display: "flex", alignItems: "center", gap: 6, padding: "0 12px", background: "none", border: "none", borderBottom: "1px solid var(--border-subtle)", cursor: "pointer", textAlign: "left" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
      <ChevronRight size={12} color="var(--text-light)" style={{ flexShrink: 0, transform: open ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 120ms ease" }} />
      <span style={{ width: 6, height: 6, borderRadius: 2, background: accent, flexShrink: 0 }} />
      <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</span>
      <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>{count}</span>
        {!open && agg != null && (
          <span style={{ fontSize: 10, fontWeight: 700, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", color: agg > 0 ? "var(--green)" : agg < 0 ? "var(--red)" : "var(--text-light)" }}>{fmtPct(agg)}</span>
        )}
      </span>
      <span style={{ width: 20, flexShrink: 0 }} />
    </button>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", fontFamily: "var(--font-sans)" }}>
      {/* Level-1 module band */}
      <div style={{ height: 28, boxSizing: "border-box", display: "flex", alignItems: "center", gap: 8, padding: "0 12px", background: "var(--bg)", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
        <span style={{ width: 2, height: 10, borderRadius: 1, background: "var(--green)", flexShrink: 0 }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-secondary)" }}>
          Specul<span style={{ color: "var(--lavender)" }}>AI</span>r
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-light)" }}>{apex.length + cap.length}</span>
        <button onClick={fetchQuotes} title="Refresh"
          style={{ marginLeft: "auto", width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", background: "none", border: "none", cursor: "pointer", borderRadius: 4, color: "var(--text-light)" }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; e.currentTarget.style.color = "var(--text)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-light)"; }}>
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Apex NAV — the rail's one hero element, framed as an inset stat card */}
      {tracking && sinceInception != null && (
        <div style={{ margin: "8px 12px", padding: "8px 10px", background: "var(--bg)", border: "1px solid var(--border-subtle)", borderRadius: 6, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-light)" }}>
              Apex · since {fmtDay(tracking.inception_date)}{daysSince != null ? ` · ${daysSince}d` : ""}
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "var(--font-mono)", letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums", color: perfColor }}>
              {sinceInception > 0 ? "+" : ""}{sinceInception.toFixed(1)}%
            </div>
            <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)", marginTop: 2 }}>
              NAV {(nav ?? 0).toFixed(1)}{closed.length ? ` · ${closed.length} rotated` : ""}
            </div>
          </div>
          <Sparkline navs={navHist.map((h) => h.nav)} color={perfColor} />
        </div>
      )}

      {/* Column sub-header — covers both live sections below */}
      <div style={{ display: "grid", gridTemplateColumns: GRID, gap: 6, height: 20, alignItems: "center", padding: "0 12px", background: "var(--bg)", fontSize: 9, fontWeight: 600, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--border-subtle)", fontFamily: "var(--font-mono)" }}>
        <div>Symbol</div>
        <div style={{ textAlign: "right" }}>Entry</div>
        <div style={{ textAlign: "right" }}>Last</div>
        <div style={{ textAlign: "right" }}>P&amp;L</div>
        <div></div>
      </div>

      {/* Apex Basket */}
      <SectionHeader open={openApex} onClick={() => setOpenApex(!openApex)} title="Apex Basket" count={apex.length} accent="var(--green)" agg={meanPnl(apex)} />
      {openApex && (apex.length > 0
        ? apex.map((p) => <Row key={p.symbol} p={p} />)
        : <div style={{ padding: "14px 12px", fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>No Apex positions.</div>)}

      {/* Beaten-Down (capitulation) watchlist — adjacent to Apex so the shared sub-header covers both */}
      <SectionHeader open={openCap} onClick={() => setOpenCap(!openCap)} title="Beaten-Down" count={cap.length} accent="var(--amber)" agg={meanPnl(cap)} />
      {openCap && (cap.length > 0
        ? cap.map((p) => <Row key={p.symbol} p={p} />)
        : <div style={{ padding: "14px 12px", fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>No Capitulation setups.</div>)}

      {/* Rotated out — realized returns logged when a name leaves the basket */}
      {tracking && (
        <>
          <SectionHeader open={openClosed} onClick={() => setOpenClosed(!openClosed)} title="Rotated out" count={closed.length} accent="var(--text-light)" agg={rotAgg} />
          {openClosed && (closed.length > 0
            ? [...closed].reverse().map((c, i) => {
                const ret = typeof c.return_pct === "number" ? c.return_pct : null;
                const rc = ret == null ? "var(--text-light)" : ret > 0 ? "var(--green)" : ret < 0 ? "var(--red)" : "var(--text-light)";
                return (
                  <div key={`${c.symbol}-${c.exit_date}-${i}`} style={{ display: "grid", gridTemplateColumns: GRID, gap: 6, height: 28, alignItems: "center", padding: "0 12px", borderBottom: "1px solid var(--border-subtle)", fontSize: 11, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", transition: "background 0.1s" }}
                       onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                    <div style={{ gridColumn: "1 / span 3", display: "flex", alignItems: "center", gap: 5, minWidth: 0 }}>
                      <Link href={`/stock/${c.symbol}`} style={{ textDecoration: "none", color: "var(--text)", fontWeight: 700 }}>{c.symbol}</Link>
                      <span style={{ fontSize: 9, color: "var(--text-light)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{fmtDay(c.entry_date)}→{fmtDay(c.exit_date)}</span>
                    </div>
                    <div style={{ textAlign: "right", color: rc, fontWeight: 700 }}>{ret == null ? PENDING : fmtPct(ret)}</div>
                    <span />
                  </div>
                );
              })
            : <div style={{ padding: "14px 12px", fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>No rotations yet — realized returns appear here as picks leave the basket.</div>)}
        </>
      )}

      {/* Footer */}
      <div style={{ padding: "6px 12px 8px", fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>
        {trackingIsWeighted ? "Director-weighted" : "Equal-weight"} NAV chain · 30s quotes{baskets.generated_at ? ` · gen ${new Date(baskets.generated_at).toLocaleDateString()}` : ""}
      </div>
    </div>
  );
}
